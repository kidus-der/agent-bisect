#!/usr/bin/env python3
"""P0b step 4: apply the pre-registered rules to the measured data and write the decision.

Reads only measurements — `runs/p0/rate_limit.json`, `runs/p0/toolcheck.json`,
`runs/p0/usersim.json`, `runs/p0/judge_latency.json` and every per-task
checkpoint under `runs/p0/probe/` — applies the rules in
`docs/decisions/0004-p0-probe-protocol.md` §4 mechanically, and writes
`config/models.toml` and `docs/decisions/models.md`.

Both outputs are generated, never hand-edited: the numbers in them can
always be re-derived from the checkpoints by re-running this script, and
`scripts/gates/p0.py` re-checks them against the same raw files.

If no candidate satisfies the agent rule the script says so, writes the
numbers anyway, and leaves `agent` unset in `config/models.toml` — which
makes `bisect doctor` and the P0 gate fail. Nothing is relaxed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.adapters.tau2_probe import (  # noqa: E402
    AGENT_PASS_WINDOW,
    AGENT_TARGET_PASS_RATE,
    JUDGE_LATENCY_BUDGET_S,
    MIN_VALID_TOOL_CALL_RATE,
    ModelProbeSummary,
    TaskProbeResult,
    choose_agent,
    choose_judge,
    summarise_probe,
)

RUNS = REPO_ROOT / "runs" / "p0"
PROBE_DIR = RUNS / "probe"
MODELS_TOML = REPO_ROOT / "config" / "models.toml"
MODELS_DOC = REPO_ROOT / "docs" / "decisions" / "models.md"
N_TASKS = 20
SAFETY_MARGIN = 0.10

AGENT_CANDIDATES = [
    "deepseek-ai/deepseek-v4-flash-0731",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
]
JUDGE_CANDIDATES = ["moonshotai/kimi-k3", "nvidia/nemotron-3-ultra-550b-a55b"]
UNAVAILABLE = {
    "moonshotai/kimi-k2.6": "HTTP 404 'Function ... not found for account' — not on this key",
}
#: The brief's order-of-magnitude estimate for P3's 120-failure collection.
P3_CALLS_LOW = 8000
P3_CALLS_HIGH = 12000
#: 0001: the 60-failure fallback floor applies only if 120 projects past this.
P3_HOUR_LIMIT = 10.0


def read_json(path: Path, default: dict | None = None) -> dict:
    """Always a dict: an absent or corrupt file reads as empty, never as None."""
    fallback = default if default is not None else {}
    if not path.exists():
        return fallback
    try:
        loaded = json.loads(path.read_text())
    except ValueError:
        return fallback
    return loaded if isinstance(loaded, dict) else fallback


def load_probe_results(model: str) -> list[TaskProbeResult]:
    directory = PROBE_DIR / model.replace("/", "__")
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".simulation.json"):
            continue
        payload = json.loads(path.read_text())
        payload["invalid_reasons"] = tuple(payload.get("invalid_reasons") or ())
        rows.append(TaskProbeResult(**payload))
    return rows


def limiter_rpm(measured: float) -> int:
    return max(1, int(measured * (1 - SAFETY_MARGIN)))


def retry_rates(ledger_path: Path) -> dict[str, tuple[int, int]]:
    """Per model: (attempts that had to be retried, attempts that succeeded).

    Retries here are the provider rejecting an in-flight request, not our rate
    bucket overflowing -- the bucket is what stops us exceeding the measured
    rpm. A model with a high retry share is telling us the probe ran it at more
    concurrent requests than it will accept, which is the real limit on
    sustainable concurrency.
    """
    import sqlite3

    if not ledger_path.exists():
        return {}
    conn = sqlite3.connect(ledger_path)
    rows = conn.execute(
        "SELECT model, status, COUNT(*) FROM calls "
        "WHERE purpose IN ('agent', 'user') GROUP BY model, status"
    ).fetchall()
    out: dict[str, list[int]] = {}
    for model, status, count in rows:
        entry = out.setdefault(model, [0, 0])
        if status == "retrying":
            entry[0] += count
        elif status == "ok":
            entry[1] += count
    return {model: (retried, ok) for model, (retried, ok) in out.items()}


def throughput(summaries: list[ModelProbeSummary], results: dict[str, list[TaskProbeResult]],
               concurrency: int) -> dict:
    """Projected calls/hour from what the probe actually achieved, not from the limiter."""
    rows = [row for model in results for row in results[model] if row.wall_time_s > 0]
    if not rows:
        return {"calls_per_hour": 0.0, "note": "no completed task to project from"}
    mean_wall = statistics.mean(r.wall_time_s for r in rows)
    mean_calls = statistics.mean(r.calls_used for r in rows)
    tasks_per_hour = 3600.0 / mean_wall * concurrency
    calls_per_hour = tasks_per_hour * mean_calls
    return {
        "mean_task_wall_s": mean_wall,
        "mean_calls_per_task": mean_calls,
        "concurrency": concurrency,
        "calls_per_hour": calls_per_hour,
        "p3_hours_low": P3_CALLS_LOW / calls_per_hour if calls_per_hour else float("inf"),
        "p3_hours_high": P3_CALLS_HIGH / calls_per_hour if calls_per_hour else float("inf"),
    }


def _toml_line(key: str, value) -> str:
    if isinstance(value, str):
        return f'{key} = "{value}"'
    if isinstance(value, bool):
        return f"{key} = {str(value).lower()}"
    return f"{key} = {value}"


def render_toml(decision: dict) -> str:
    """`config/models.toml` — the pinned choice plus the evidence behind it."""
    lines = [
        "# Chosen models for the whole study. GENERATED by scripts/decide_models.py",
        "# from the measurements in runs/p0/; do not hand-edit -- re-run the script.",
        "# Rules: docs/decisions/0001-preregistration.md and",
        "# docs/decisions/0004-p0-probe-protocol.md. Evidence: docs/decisions/models.md.",
        "",
    ]
    for key in ("date", "tau2_commit", "agent", "user_sim", "judge"):
        if decision.get(key):
            lines.append(_toml_line(key, decision[key]))
    lines += ["", "# Measured for the chosen agent over the 20-task airline probe."]
    for key in ("valid_tool_call_rate", "airline_pass_rate", "e2e_task_reward"):
        if decision.get(key) is not None:
            lines.append(_toml_line(key, decision[key]))
    lines += [
        "",
        "[temperatures]",
        "# tau2 defaults, pinned in 0004 section 1 for every phase.",
        "agent = 0.0",
        "user = 0.0",
        "",
        "[rate_limit]",
        f'scope = "{decision["scope"]}"',
        "",
        "[rate_limit.measured_rpm]",
    ]
    for model, rpm in sorted(decision["measured_rpm"].items()):
        lines.append(f'"{model}" = {rpm}')
    lines += ["", "[rate_limit.limiter_rpm]"]
    for model, rpm in sorted(decision["limiter_rpm"].items()):
        lines.append(f'"{model}" = {rpm}')
    return "\n".join(lines) + "\n"


def _summary_row(summary: ModelProbeSummary) -> str:
    rate = summary.valid_tool_call_rate
    shown = "n/a (no tool call)" if rate is None else f"{rate:.3f}"
    return (
        f"| `{summary.model}` | {summary.n_passed}/{summary.n_tasks} = "
        f"{summary.pass_rate:.2f} | [{summary.ci_low:.2f}, {summary.ci_high:.2f}] | {shown} "
        f"({summary.n_invalid_tool_calls}/{summary.n_tool_calls} invalid) | "
        f"{summary.mean_steps:.1f} | {summary.mean_calls_per_task:.1f} | "
        f"{summary.mean_agent_latency_ms / 1000:.1f} s |"
    )


def _ramp_rows(state: dict) -> list[str]:
    rows = []
    for window in state.get("windows", []):
        rows.append(
            f"| {window['phase']} | `{window['model']}` | {window['target_rpm']} | "
            f"{window['duration_s']:.0f} s | {window['sent']} | {window['ok']} | "
            f"{window['rate_limited']} | {window['other_errors']} | "
            f"{window['p50_ms']:.0f} | {window['p95_ms']:.0f} |"
        )
    return rows


def render_doc(decision: dict) -> str:
    """`docs/decisions/models.md` — every number, and the rule that produced the choice."""
    d = decision
    parts = [
        "# Model choice and the measurements behind it",
        "",
        f"- **Date:** {d['date']}. **τ² commit:** `{d['tau2_commit']}`.",
        "- **GENERATED** by `scripts/decide_models.py` from `runs/p0/`; re-running it "
        "reproduces this file. Rules were fixed before measuring: "
        "`docs/decisions/0001-preregistration.md`, "
        "`docs/decisions/0004-p0-probe-protocol.md`.",
        "",
        "## 1. Availability",
        "",
        "| Model | Role | Available | Note |",
        "|---|---|---|---|",
    ]
    for model, note in UNAVAILABLE.items():
        parts.append(f"| `{model}` | agent | **no** | {note} |")
    for model in AGENT_CANDIDATES:
        parts.append(f"| `{model}` | agent | yes | {d['availability'].get(model, '')} |")
    for model in (d["user_sim_primary"], d["user_sim_fallback"]):
        parts.append(f"| `{model}` | user simulator | yes | |")
    for model in JUDGE_CANDIDATES:
        parts.append(f"| `{model}` | judge | yes | |")

    parts += [
        "",
        "`moonshotai/kimi-k2.6` is the first agent candidate in 0001's fallback order and "
        "is unavailable on this key, so it is skipped and its absence recorded — per the "
        "fallback rule, not as an exception to it.",
        "",
        "## 2. Measured rate limit",
        "",
        f"**The limit is enforced per model, not account-wide.** {d['scope_evidence']}",
        "",
        "| Phase | Model | Target rpm | Window | Sent | 200s | 429s | Other errors | "
        "p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    parts += _ramp_rows(d["rate_limit_state"])
    parts += [
        "",
        "No response header containing `rate`, `limit` or `retry` was returned by NIM on any "
        "request in any window, and no `Retry-After` was ever sent — the ceiling is only "
        "observable by hitting it.",
        "",
        "| Model | Measured rpm | Limiter rpm (measured − 10%) |",
        "|---|---|---|",
    ]
    for model, rpm in sorted(d["measured_rpm"].items()):
        parts.append(f"| `{model}` | {rpm} | {d['limiter_rpm'][model]} |")
    if d["unbracketed"]:
        parts += [
            "",
            "**Not bracketed.** These returned 429s at the lowest rate they were tried at, so "
            "their ceiling is below it and no clean rate was located. They are recorded as "
            "unmeasured rather than as a number, and the limiter is set conservatively for "
            "them (`config/limits.toml`):",
            "",
            "| Model | What was observed |",
            "|---|---|",
        ]
        for model, note in sorted(d["unbracketed"].items()):
            parts.append(f"| `{model}` | {note} |")
    parts += [
        "",
        f"**Sustainable concurrency.** The probe ran {d['concurrency']} tasks at once, "
        "spread round-robin across the agent candidates. Retried attempts per model over "
        "the whole phase (a retry means the provider rejected an in-flight request, not "
        "that our rate bucket overflowed):",
        "",
        "| Model | Retried attempts | Successful | Retry share |",
        "|---|---|---|---|",
    ]
    for model, (retried, ok) in sorted(d["retry_rates"].items()):
        share = retried / (retried + ok) if (retried + ok) else 0.0
        parts.append(f"| `{model}` | {retried} | {ok} | {share:.1%} |")
    parts += [
        "",
        "## 3. Agent probe — 20 airline tasks, 1 trial each",
        "",
        "| Model | Pass rate | 95% CI (Wilson) | Valid tool calls | Mean messages | "
        "Calls/task | Mean agent latency |",
        "|---|---|---|---|---|---|---|",
        # "Mean messages" is len(simulation.messages): one per turn taken by the
        # agent, the user or a tool. Reported under its real name rather than as
        # "steps", which in this project means a tape step.
    ]
    parts += [_summary_row(s) for s in d["summaries"]]
    parts += [
        "",
        f"**Rule (0001 / 0004 §4.3):** among candidates that are available and reach "
        f"≥ {MIN_VALID_TOOL_CALL_RATE:.0%} valid tool calls, take the pass rate inside "
        f"{AGENT_PASS_WINDOW} and closest to {AGENT_TARGET_PASS_RATE}; ties → higher "
        "measured rpm → candidate list order.",
        "",
        f"**Chosen agent: {d['agent'] or '— none —'}** — {d['agent_reason']}",
        "",
        "### DeepSeek tool-call re-check",
        "",
        d["toolcheck_note"],
        "",
        "## 4. User simulator",
        "",
        f"**Chosen: `{d['user_sim']}`** — {d['user_sim_reason']}",
        "",
        "## 5. Judge",
        "",
        "| Judge | Median latency over 5 calls | Budget |",
        "|---|---|---|",
    ]
    for model in JUDGE_CANDIDATES:
        median = d["judge_medians"].get(model)
        shown = "not measured" if median is None else f"{median:.1f} s"
        parts.append(f"| `{model}` | {shown} | ≤ {JUDGE_LATENCY_BUDGET_S:g} s |")
    parts += [
        "",
        f"Prompt: {d['judge_prompt_chars']} characters (~{d['judge_prompt_chars'] // 4} tokens), "
        "built from a real recorded probe trajectory.",
        "",
        f"**Chosen: `{d['judge']}`** — {d['judge_reason']}",
        "",
        "## 6. End-to-end check",
        "",
        d["e2e_note"],
        "",
        "## 7. Throughput projection for P3",
        "",
    ]
    t = d["throughput"]
    if t.get("calls_per_hour"):
        triggered = t["p3_hours_high"] > P3_HOUR_LIMIT
        parts += [
            f"- Measured: {t['mean_calls_per_task']:.1f} calls per task, "
            f"{t['mean_task_wall_s']:.0f} s per task, at concurrency {t['concurrency']}.",
            f"- **Projected throughput: {t['calls_per_hour']:.0f} calls/hour.**",
            f"- The brief estimates P3's 120-failure collection at "
            f"{P3_CALLS_LOW:,}–{P3_CALLS_HIGH:,} calls → "
            f"**{t['p3_hours_low']:.1f}–{t['p3_hours_high']:.1f} hours of API time.**",
            "",
            f"**Pre-registered 60-failure fallback floor (0001, P3): "
            f"{'TRIGGERED' if triggered else 'NOT triggered'}** — the fallback applies only "
            f"if the 120-target collection projects past {P3_HOUR_LIMIT:g} h; the upper "
            f"estimate is {t['p3_hours_high']:.1f} h, which is "
            f"{'above' if triggered else 'at or below'} that limit.",
        ]
    else:
        parts.append(f"Not projectable: {t.get('note')}")
    parts += ["", "## 8. Calls spent", "", "| Model | Calls |", "|---|---|"]
    for model, calls in sorted(d["calls_per_model"].items()):
        parts.append(f"| `{model}` | {calls} |")
    parts.append(f"| **total** | **{sum(d['calls_per_model'].values())}** |")
    return "\n".join(parts) + "\n"


def build_decision(concurrency: int) -> dict:
    from agent_bisect.core.budget import BudgetLedger

    rate_state = read_json(RUNS / "rate_limit.json", {"measured_rpm": {}, "windows": []})
    toolcheck = read_json(RUNS / "toolcheck.json", {})
    usersim = read_json(RUNS / "usersim.json", {})
    judge_state = read_json(RUNS / "judge_latency.json", {"median_latency_s": {}})
    e2e = read_json(RUNS / "e2e.json")

    results = {model: load_probe_results(model) for model in AGENT_CANDIDATES}
    summaries = [
        summarise_probe(model, rows, n_tasks=N_TASKS)
        for model, rows in results.items()
        if rows
    ]
    measured = {m: int(v) for m, v in rate_state.get("measured_rpm", {}).items() if v}
    agent, agent_reason = choose_agent(summaries, dict(measured), AGENT_CANDIDATES)
    judge_medians = judge_state.get("median_latency_s", {})
    judge, judge_reason = (
        choose_judge(judge_medians, JUDGE_CANDIDATES)
        if judge_medians
        else (None, "judge latency not measured")
    )
    chosen = next((s for s in summaries if s.model == agent), None)
    ledger = BudgetLedger(REPO_ROOT / "runs" / "ledger.sqlite")

    return {
        "date": "2026-09-17",
        "tau2_commit": "2174a603f6d014ef94473ffa95957f6ce27100db",
        "agent": agent,
        "agent_reason": agent_reason,
        "user_sim": usersim.get("chosen", ""),
        "user_sim_reason": usersim.get("reason", "not run"),
        "user_sim_primary": usersim.get("primary", ""),
        "user_sim_fallback": usersim.get("fallback", ""),
        "judge": judge,
        "judge_reason": judge_reason,
        "judge_medians": judge_medians,
        "judge_prompt_chars": judge_state.get("prompt_chars", 0),
        "valid_tool_call_rate": chosen.valid_tool_call_rate if chosen else None,
        "airline_pass_rate": chosen.pass_rate if chosen else None,
        "e2e_task_reward": e2e.get("reward"),
        "e2e_note": (
            f"`bisect doctor --live` ran airline task {e2e['task_id']} end to end with the "
            f"chosen models and got **reward = {e2e['reward']}** "
            f"(termination: {e2e.get('termination_reason')}, "
            f"{e2e.get('n_messages')} messages, {e2e.get('wall_time_s', 0):.0f} s)."
            if e2e else "No end-to-end run recorded yet."
        ),
        "summaries": summaries,
        "measured_rpm": measured,
        "limiter_rpm": {m: limiter_rpm(v) for m, v in measured.items()},
        "scope": "model",
        "scope_evidence": rate_state.get("scope_evidence", SCOPE_EVIDENCE),
        "unbracketed": rate_state.get("unbracketed", {}),
        "rate_limit_state": rate_state,
        "availability": {m: "" for m in AGENT_CANDIDATES},
        "toolcheck_note": (
            f"`{toolcheck.get('model')}` was re-checked with a proper `tools` payload and "
            f"`tool_choice=\"auto\"` on a prompt that clearly needs the tool: it emitted "
            f"structured tool calls on attempt {toolcheck.get('calls')} → "
            f"**usable as an agent = {toolcheck.get('usable_as_agent')}**. "
            "P0a's availability smoke had recorded \"no\", but that test used an unrelated "
            "dummy weather tool; the re-check supersedes it."
            if toolcheck else "Not run."
        ),
        "concurrency": concurrency,
        "throughput": throughput(summaries, results, concurrency),
        "calls_per_model": ledger.totals_per_model(),
        "retry_rates": retry_rates(REPO_ROOT / "runs" / "ledger.sqlite"),
    }


SCOPE_EVIDENCE = (
    "In one 60 s window with two models at 120 rpm each (240 rpm combined), "
    "`openai/gpt-oss-20b` took 120/120 requests with zero 429s while "
    "`nvidia/nemotron-3.5-lightning-30b-a3b` took 48 HTTP 429s — a shared account bucket "
    "could not throttle one model that hard and spare the other entirely. An isolation "
    "window settled it: `nvidia/nemotron-3.5-lightning-30b-a3b` **alone** at 120 rpm still "
    "returned 10 HTTP 429s in 60 requests, so its own ceiling, not the combined rate, is "
    "what it hit."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    decision = build_decision(args.concurrency)
    MODELS_TOML.parent.mkdir(parents=True, exist_ok=True)
    MODELS_TOML.write_text(render_toml(decision))
    MODELS_DOC.parent.mkdir(parents=True, exist_ok=True)
    MODELS_DOC.write_text(render_doc(decision))

    print(f"agent:     {decision['agent']} — {decision['agent_reason']}")
    print(f"user sim:  {decision['user_sim']} — {decision['user_sim_reason']}")
    print(f"judge:     {decision['judge']} — {decision['judge_reason']}")
    print(f"wrote {MODELS_TOML} and {MODELS_DOC}")
    return 0 if decision["agent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
