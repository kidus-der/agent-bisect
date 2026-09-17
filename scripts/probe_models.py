#!/usr/bin/env python3
"""P0b step 3: probe the agent candidates on 20 airline tasks, per `docs/decisions/0004`.

Four stages, each independently resumable (`--stage`):

- `toolcheck` — does DeepSeek emit *structured* tool calls at all? (≤5 calls)
- `usersim`   — the 2-task sanity check of 0004 §4.1
- `probe`     — 20 airline tasks × each usable agent candidate
- `judge`     — 5 calls per judge with a realistic ~3k-token trace prompt

Resumability is per `(model, task_id)`: a finished task writes
`runs/p0/probe/<model_slug>/<task_id>.json` plus τ²'s own simulation JSON
(redacted) beside it, and a re-run skips anything already on disk. Nothing
is ever recomputed and no finished task is redone.

Infra failures (429/5xx/timeouts, crashes of our code) are recorded on the
row as `error` and are *not* counted as task failures — the row is simply
absent from the checkpoint dir until it succeeds, so a re-run retries it.

Pacing comes from the process-wide limiter in `core.limits`, not from
absorbing 429s: task concurrency is deliberately modest so the bucket, not
the provider, is what throttles us.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_bisect.adapters.tau2_e2e import load_airline_tasks, text_run_config, trial_seed
from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir
from agent_bisect.adapters.tau2_llm import route_tau2_llm, tool_checker_for
from agent_bisect.adapters.tau2_probe import ProbeCollector, TaskProbeResult
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.config import get_settings, redact
from agent_bisect.core.limits import get_limiter_settings, get_shared_limiter
from agent_bisect.core.llm import LiteLLMTransport, LLMClient, LLMClientConfig, LLMRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO_ROOT / "runs" / "p0" / "probe"
JUDGE_PATH = REPO_ROOT / "runs" / "p0" / "judge_latency.json"
TOOLCHECK_PATH = REPO_ROOT / "runs" / "p0" / "toolcheck.json"
LEDGER_PATH = REPO_ROOT / "runs" / "ledger.sqlite"

PHASE = "P0"
P0_CALL_CAP = 4000
DOMAIN = "airline"
N_TASKS = 20
SANITY_TASKS = 2
JUDGE_CALLS = 5
JUDGE_PROMPT_CHARS = 12_000  # ~3k tokens at ~4 chars/token
TOOLCHECK_MAX_CALLS = 5

AGENT_CANDIDATES = (
    "deepseek-ai/deepseek-v4-flash-0731",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
)
USER_SIM_PRIMARY = "nvidia/nemotron-3.5-lightning-30b-a3b"
USER_SIM_FALLBACK = "openai/gpt-oss-20b"
#: The sanity check tests the *user simulator*; the agent just has to work.
SANITY_AGENT = "nvidia/nemotron-3-super-120b-a12b"
JUDGE_CANDIDATES = ("moonshotai/kimi-k3", "nvidia/nemotron-3-ultra-550b-a55b")

TOOLCHECK_TOOL = {
    "type": "function",
    "function": {
        "name": "get_reservation_details",
        "description": "Look up an airline reservation by its 6-character reservation id.",
        "parameters": {
            "type": "object",
            "properties": {"reservation_id": {"type": "string"}},
            "required": ["reservation_id"],
        },
    },
}
TOOLCHECK_PROMPTS = (
    "Look up reservation NM1VX1 for me. Use the tool; do not guess.",
    "Call get_reservation_details with reservation_id ZFA04Y and report what it returns.",
    "I need the details of booking HHX4W2. You must use the available function to fetch them.",
)

_local = threading.local()


def slug(model: str) -> str:
    return model.replace("/", "__")


# ---------------------------------------------------------------------------
# checkpoints
# ---------------------------------------------------------------------------


def checkpoint_path(model: str, task_id: str) -> Path:
    return PROBE_DIR / slug(model) / f"{task_id}.json"


def load_checkpoint(model: str, task_id: str) -> TaskProbeResult | None:
    if task_id.endswith((".error", ".simulation")):
        return None
    path = checkpoint_path(model, task_id)
    if not path.exists():
        return None
    try:
        return TaskProbeResult(**{
            **json.loads(path.read_text()),
            "invalid_reasons": tuple(json.loads(path.read_text())["invalid_reasons"]),
        })
    except (ValueError, TypeError, KeyError) as exc:
        print(f"  ignoring unreadable checkpoint {path}: {exc}")
        return None


def save_checkpoint(result: TaskProbeResult, simulation_json: str | None) -> None:
    """Write a finished task's checkpoint, or an infra failure's error file.

    An attempt that died on infrastructure (429/5xx past our retry budget,
    a timeout, a crash in our code) must NOT land at `<task_id>.json`:
    that path is what `load_checkpoint` treats as "this task is done", so
    the task would never be retried and would be scored as a failure —
    exactly what protocol 0004 §3 forbids. It goes to `<task_id>.error.json`
    instead, which keeps it visible for diagnosis while leaving the task
    outstanding.
    """
    path = checkpoint_path(result.model, result.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asdict(result), "invalid_reasons": list(result.invalid_reasons)}
    if result.error is not None:
        path.with_suffix(".error.json").write_text(
            redact(json.dumps(payload, indent=2, sort_keys=True))
        )
        return
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    # A task that eventually succeeded is no longer a failure to explain.
    path.with_suffix(".error.json").unlink(missing_ok=True)
    if simulation_json is not None:
        path.with_suffix(".simulation.json").write_text(redact(simulation_json))


def load_all(model: str) -> list[TaskProbeResult]:
    directory = PROBE_DIR / slug(model)
    if not directory.exists():
        return []
    rows = [
        load_checkpoint(model, path.stem)
        for path in sorted(directory.glob("*.json"))
        if not path.name.endswith((".simulation.json", ".error.json"))
    ]
    return [row for row in rows if row is not None]


# ---------------------------------------------------------------------------
# running one τ² task
# ---------------------------------------------------------------------------


def load_tasks(limit: int) -> list[Any]:
    return load_airline_tasks(limit)


def _result_from(
    model: str, task_id: str, collector: ProbeCollector, simulation: Any,
    seed: int, wall_time_s: float, error: str | None,
) -> TaskProbeResult:
    reward = None
    termination = "infrastructure_error"
    n_steps = 0
    if simulation is not None:
        reward = simulation.reward_info.reward if simulation.reward_info else None
        termination = str(getattr(simulation.termination_reason, "value", ""))
        n_steps = len(simulation.messages or [])
    return TaskProbeResult(
        model=model,
        task_id=task_id,
        reward=reward,
        passed=reward == 1.0,
        n_steps=n_steps,
        n_agent_calls=collector.n_agent_calls,
        n_user_calls=collector.n_user_calls,
        n_agent_tool_calls=collector.n_tool_calls,
        n_invalid_tool_calls=collector.n_invalid_tool_calls,
        invalid_reasons=collector.invalid_reasons,
        termination_reason=termination,
        calls_used=collector.calls_used,
        wall_time_s=wall_time_s,
        seed=seed,
        mean_agent_latency_ms=collector.mean_agent_latency_ms,
        n_empty_user_messages=collector.n_empty_user_messages,
        error=error,
    )


def run_one_task(
    model: str, task: Any, config: Any, checker: tuple[set[str], Any]
) -> TaskProbeResult:
    """Run one τ² task to completion and return its checkpoint row."""
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.run import run_single_task

    asyncio.set_event_loop(asyncio.new_event_loop())
    collector = ProbeCollector(*checker)
    _local.collector = collector
    seed = trial_seed()
    start = time.monotonic()
    simulation, error = None, None
    try:
        simulation = run_single_task(
            config, task, seed=seed, evaluation_type=EvaluationType.ALL
        )
    except Exception as exc:  # noqa: BLE001 - infra failure, recorded not raised
        # Exception, not BaseException: Ctrl+C must stop the probe rather than
        # be written into a checkpoint as if it were a task-level failure.
        error = redact(f"{type(exc).__name__}: {exc}")[:400]
    finally:
        _local.collector = None
    simulation_json = simulation.model_dump_json(indent=2) if simulation is not None else None
    result = _result_from(
        model, task.id, collector, simulation, seed, time.monotonic() - start, error
    )
    save_checkpoint(result, simulation_json)
    return result


def on_call(request: dict, response: Any, meta: Any) -> None:
    """The bridge's record-before-use hook, routed to the calling thread's task."""
    collector = getattr(_local, "collector", None)
    if collector is not None:
        collector.record(request, response, meta)


def probe_models(
    models: list[str],
    user_model: str,
    tasks: list[Any],
    concurrency: int,
    checker: tuple[set[str], Any],
) -> dict[str, list[TaskProbeResult]]:
    """Run every not-yet-finished (model, task) pair in one pool.

    Interleaving the models matters: they have very different per-call
    latencies (deepseek ~23s, nemotron-super ~0.3s) and separate per-model
    rate buckets, so a pool shared across models keeps every bucket busy
    instead of idling one while another model's slow tasks drain.
    """
    configs = {model: text_run_config(model, user_model) for model in models}
    done: dict[str, list[TaskProbeResult]] = {model: [] for model in models}
    per_model: dict[str, list[Any]] = {model: [] for model in models}
    for model in models:
        for task in tasks:
            existing = load_checkpoint(model, task.id)
            if existing is None:
                per_model[model].append(task)
            else:
                done[model].append(existing)
        print(f"{model}: {len(done[model])} done, "
              f"{len(per_model[model])} to run")
    # Round-robin, not model-major. Submitted in model-major order every slot
    # in the pool goes to the first model, which saturates that one endpoint's
    # queue (its per-call latency then climbs with depth) while the other
    # models' separate rate buckets sit idle.
    pending: list[tuple[str, Any]] = [
        (model, per_model[model][i])
        for i in range(max((len(v) for v in per_model.values()), default=0))
        for model in models
        if i < len(per_model[model])
    ]
    if not pending:
        return done
    print(f"running {len(pending)} (model, task) pairs at concurrency {concurrency}")
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(run_one_task, model, task, configs[model], checker): model
            for model, task in pending
        }
        for future, model in futures.items():
            row = future.result()
            status = row.error or ("pass" if row.passed else f"reward={row.reward}")
            print(f"  {model} task {row.task_id}: {status} "
                  f"({row.n_steps} msgs, {row.calls_used} calls, {row.wall_time_s:.0f}s)",
                  flush=True)
            done[model].append(row)
    return done


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------


def make_client(ledger: BudgetLedger, model: str) -> LLMClient:
    settings = get_settings()
    assert settings.nvidia_api_key is not None
    return LLMClient(
        LiteLLMTransport(),
        ledger,
        api_base=settings.nvidia_base_url,
        api_key=settings.nvidia_api_key.get_secret_value(),
        config=LLMClientConfig(requests_per_minute=get_shared_limiter(model).requests_per_minute),
        limiter=get_shared_limiter(model),
    )


def stage_toolcheck(ledger: BudgetLedger, model: str) -> dict:
    """0004 §4.3: a candidate that cannot emit structured tool calls is unusable as an agent."""
    client = make_client(ledger, model)
    attempts: list[dict] = []
    for prompt in TOOLCHECK_PROMPTS[:TOOLCHECK_MAX_CALLS]:
        request = LLMRequest(
            model=model,
            messages=({"role": "user", "content": prompt},),
            max_tokens=256,
            tools=(TOOLCHECK_TOOL,),
            purpose="toolcheck",
        )
        try:
            response = asyncio.run(client.complete(request, phase=PHASE))
        except Exception as exc:  # noqa: BLE001 - a failed attempt is a datapoint
            attempts.append({"prompt": prompt, "error": redact(str(exc))[:300]})
            continue
        message = (response.raw.get("choices") or [{}])[0].get("message", {})
        attempts.append({
            "prompt": prompt,
            "tool_calls": bool(message.get("tool_calls")),
            "content": (message.get("content") or "")[:300],
        })
        if message.get("tool_calls"):
            break
    usable = any(a.get("tool_calls") for a in attempts)
    payload = {"model": model, "usable_as_agent": usable, "attempts": attempts,
               "tool_choice": "auto", "calls": len(attempts)}
    TOOLCHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOOLCHECK_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"toolcheck {model}: structured tool calls = {usable} ({len(attempts)} calls)")
    return payload


def build_judge_prompt() -> str:
    """A realistic ~3k-token judging prompt built from one recorded probe trajectory."""
    trajectories = sorted(PROBE_DIR.glob("*/*.simulation.json"))
    if not trajectories:
        raise SystemExit("no recorded trajectory yet; run --stage probe first")
    # The protocol asks for a *realistic ~3k-token* prompt. Taking the first
    # file alphabetically gives whichever conversation happened to be shortest
    # (~1.9k tokens on this data); the longest recorded one is the closest
    # single trajectory to the intended size, and the char cap trims from there.
    longest = max(
        trajectories, key=lambda path: len(json.loads(path.read_text()).get("messages") or [])
    )
    messages = json.loads(longest.read_text()).get("messages") or []
    transcript = "\n".join(
        f"{m.get('role')}: {json.dumps(m.get('content'))[:600]}" for m in messages
    )[:JUDGE_PROMPT_CHARS]
    return (
        "You are grading an airline customer-service agent transcript. Identify the single "
        "step at which the agent first went wrong, and answer with that step's index and a "
        "one-sentence reason.\n\n<transcript>\n" + transcript + "\n</transcript>"
    )


def stage_judge(ledger: BudgetLedger) -> dict:
    prompt = build_judge_prompt()
    medians: dict[str, float] = {}
    samples: dict[str, list[float]] = {}
    for model in JUDGE_CANDIDATES:
        client = make_client(ledger, model)
        latencies: list[float] = []
        for _ in range(JUDGE_CALLS):
            start = time.monotonic()
            try:
                asyncio.run(client.complete(
                    LLMRequest(
                        model=model,
                        messages=({"role": "user", "content": prompt},),
                        max_tokens=256,
                        purpose="judge_latency",
                    ),
                    phase=PHASE,
                ))
            except Exception as exc:  # noqa: BLE001 - a failed call still costs latency
                print(f"  judge {model} call failed: {redact(str(exc))[:160]}")
            latencies.append(time.monotonic() - start)
        samples[model] = latencies
        medians[model] = statistics.median(latencies)
        print(f"judge {model}: median {medians[model]:.1f}s over {JUDGE_CALLS} calls "
              f"(prompt {len(prompt)} chars)")
    payload = {"prompt_chars": len(prompt), "median_latency_s": medians, "samples": samples}
    JUDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    JUDGE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def configure_logging() -> None:
    """τ²'s loguru output down to errors; our own retry warnings up to visible."""
    import logging

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="ERROR")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=("all", "toolcheck", "usersim", "probe", "judge"))
    parser.add_argument("--concurrency", type=int, default=None,
                        help="Task pool size. Defaults to limiter.max_concurrency "
                             "from config/limits.toml.")
    parser.add_argument("--tasks", type=int, default=N_TASKS)
    parser.add_argument("--models", nargs="*", default=None,
                        help="Agent candidates to probe (default: the usable ones).")
    parser.add_argument("--user-sim", default=None, help="Override the user simulator model.")
    return parser.parse_args()


def _usable_agents(requested: list[str] | None) -> list[str]:
    if requested:
        return requested
    if TOOLCHECK_PATH.exists():
        check = json.loads(TOOLCHECK_PATH.read_text())
        if not check.get("usable_as_agent"):
            return [m for m in AGENT_CANDIDATES if m != check["model"]]
    return list(AGENT_CANDIDATES)


def _resolve_user_sim(override: str | None) -> str:
    if override:
        return override
    verdict_path = REPO_ROOT / "runs" / "p0" / "usersim.json"
    if verdict_path.exists():
        return json.loads(verdict_path.read_text())["chosen"]
    return USER_SIM_PRIMARY


def run_usersim_stage(ledger: BudgetLedger, tasks: list[Any], checker, concurrency: int) -> str:
    """0004 §4.1: 2 tasks with the primary sim; fall back only if it trips a rule."""
    from agent_bisect.adapters.tau2_probe import user_sim_is_usable

    sanity_model = f"{SANITY_AGENT}#usersim-{slug(USER_SIM_PRIMARY)}"
    config = text_run_config(SANITY_AGENT, USER_SIM_PRIMARY)
    wanted = tasks[:SANITY_TASKS]
    rows = [row for row in (load_checkpoint(sanity_model, t.id) for t in wanted) if row]
    pending = [t for t in wanted if load_checkpoint(sanity_model, t.id) is None]
    if pending:
        # A τ² conversation is serial within itself, so the only way to finish
        # the sanity check promptly is to run its tasks side by side.
        with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(pending)))) as pool:
            futures = [
                pool.submit(run_one_task, sanity_model, task, config, checker)
                for task in pending
            ]
            rows.extend(future.result() for future in futures)
    usable, reason = user_sim_is_usable(rows)
    chosen = USER_SIM_PRIMARY if usable else USER_SIM_FALLBACK
    payload = {"primary": USER_SIM_PRIMARY, "fallback": USER_SIM_FALLBACK,
               "chosen": chosen, "usable": usable, "reason": reason,
               "sanity_agent": SANITY_AGENT,
               "tasks": [r.task_id for r in rows]}
    (REPO_ROOT / "runs" / "p0" / "usersim.json").write_text(json.dumps(payload, indent=2))
    print(f"user simulator: {chosen} — {reason}")
    return chosen


def main() -> None:
    args = parse_args()
    if args.concurrency is None:
        args.concurrency = get_limiter_settings().max_concurrency
    ensure_tau2_data_dir()
    configure_logging()
    settings = get_settings()
    if not settings.has_nvidia_key:
        raise SystemExit("NVIDIA_API_KEY not set; cannot probe.")
    ledger = BudgetLedger(LEDGER_PATH, max_calls=P0_CALL_CAP)

    from tau2.registry import registry

    checker = tool_checker_for(registry.get_env_constructor(DOMAIN)())
    tasks = load_tasks(args.tasks)
    print(f"{len(tasks)} airline tasks: {[t.id for t in tasks]}")

    if args.stage in ("all", "toolcheck"):
        stage_toolcheck(ledger, AGENT_CANDIDATES[0])

    with route_tau2_llm(ledger=ledger, phase=PHASE, on_call=on_call):
        user_sim = _resolve_user_sim(args.user_sim)
        if args.stage in ("all", "usersim"):
            user_sim = run_usersim_stage(ledger, tasks, checker, args.concurrency)
        if args.stage in ("all", "probe"):
            probe_models(
                _usable_agents(args.models), user_sim, tasks, args.concurrency, checker
            )

    if args.stage in ("all", "judge"):
        stage_judge(ledger)

    print(f"ledger totals: {ledger.totals_per_model()} (total {ledger.total_calls()})")


if __name__ == "__main__":
    main()
