"""`bisect blame RUN_ID --top 3 --n 8` — attribute one failure to its causal step.

A separate module from `cli.py` so the command can be built and tested on
its own; `cli.py` registers it with two lines
(`from agent_bisect.cli_blame import blame; app.command()(blame)`).

    bisect blame airline-3-faulted --top 3 --n 8

What it does, in the order the brief describes it: ask the judge which
steps look wrong, take the top `m`, re-run each of them `n` times against a
control, and name the **earliest** step whose interval clears delta. The
result is written under `runs/blame/` in the shape the dashboard reads
(`attribution/blame_store.py`), so `bisect serve` can show it.

Exit codes: 0 when a step was blamed, 5 when the search ran but nothing
cleared delta (a real answer, not an error, so it is distinct from a
failure), 4 for an unknown run, 1 for a missing key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from agent_bisect.attribution.blame_store import blame_path, save_blame
from agent_bisect.attribution.estimate import (
    DEFAULT_BATCH,
    DEFAULT_DELTA,
    DEFAULT_MAX_N,
    SequentialConfig,
)
from agent_bisect.attribution.judge import DEFAULT_CONFIG as DEFAULT_JUDGE_CONFIG
from agent_bisect.attribution.judge import JudgeBackend
from agent_bisect.attribution.search import (
    BlameConfig,
    BlameResult,
    ForkExecutor,
    TruthFor,
    run_blame,
)
from agent_bisect.attribution.trajectory import build_judge_input
from agent_bisect.bench.baselines import ItemJudgement, judge_item
from agent_bisect.cli_io import own_stdout
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, UnknownRunError

NO_STEP_BLAMED_EXIT_CODE = 5
UNKNOWN_RUN_EXIT_CODE = 4
MISSING_KEY_EXIT_CODE = 1
#: Module-level so the option default is not a call (ruff B008).
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_TOP_M = 3
DEFAULT_PHASE = "P5"


@dataclass(frozen=True, slots=True)
class BlameRun:
    """One diagnosis and the judge output that produced it."""

    result: BlameResult
    judgement: ItemJudgement


def blame_run(
    run_id: str,
    *,
    reader: TapeReader,
    store: BlobStore,
    judge_backend: JudgeBackend,
    executor: ForkExecutor,
    task_text,
    top_m: int,
    max_n: int,
    seed: int,
    runs_dir: Path,
    concurrency: int = 1,
    control_mode: str = "shared",
    truth_for: TruthFor | None = None,
    step_by_step: bool = False,
) -> BlameRun:
    """The command's whole body, with every dependency injected for testing."""
    manifest = reader.get_manifest(run_id)
    description, policy = task_text(manifest.domain, manifest.task_id)
    judge_input = build_judge_input(
        run_id,
        reader=reader,
        store=store,
        item_id=run_id,
        task_description=description,
        policy=policy,
    )
    judgement = judge_item(
        judge_input, judge_backend, DEFAULT_JUDGE_CONFIG, step_by_step=step_by_step
    )
    result = run_blame(
        item_id=run_id,
        run_id=run_id,
        steps=reader.get_steps(run_id),
        verdict=judgement.all_at_once,
        executor=executor,
        config=BlameConfig(
            top_m=top_m,
            sequential=SequentialConfig(
                batch=min(DEFAULT_BATCH, max_n),
                max_n=max_n,
                delta=DEFAULT_DELTA,
                efficacy_boundary="obf" if max_n == DEFAULT_MAX_N else "none",
            ),
            control_mode=control_mode,  # type: ignore[arg-type]
            concurrency=concurrency,
        ),
        seed=seed,
        truth_for=truth_for,
    )
    save_blame(runs_dir, result, judgement.step_by_step)
    return BlameRun(result=result, judgement=judgement)


def payload_of(run: BlameRun, runs_dir: Path) -> dict[str, Any]:
    """What the command prints: the answer, the evidence and the cost."""
    result = run.result
    effects = [] if result.estimate is None else [
        {
            "step": effect.step,
            "effect": effect.effect,
            "ci_low": effect.ci_low,
            "ci_high": effect.ci_high,
            "stop_reason": effect.stop_reason,
            "treated": [effect.treated.successes, effect.treated.n],
            "control": (
                None if effect.control is None
                else [effect.control.successes, effect.control.n]
            ),
        }
        for effect in result.estimate.step_effects
    ]
    return {
        "run_id": result.run_id,
        "blamed_step": result.blamed_step,
        "shortlist": list(result.shortlist),
        "tested_steps": list(result.tested_steps),
        "interventions": {str(k): v for k, v in result.interventions.items()},
        "untestable": list(result.untestable),
        "judge_rationale": result.judge.rationale,
        "judge_parse_failed": result.judge.parse_failed,
        "step_effects": effects,
        "cost": {
            "judge_calls": result.judge_calls,
            "replay_calls": result.replay_calls,
            "total_calls": result.total_calls,
        },
        "result_path": str(blame_path(runs_dir, result.run_id, result.method)),
    }


def format_human(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    blamed = payload["blamed_step"]
    if blamed is None:
        lines.append(f"no step blamed in {payload['run_id']}")
    else:
        lines.append(f"blame: step {blamed} · {payload['run_id']}")
    lines.append(f"  shortlist   {payload['shortlist']}")
    for effect in payload["step_effects"]:
        marker = "←" if effect["step"] == blamed else " "
        lines.append(
            f"  step {effect['step']:>3} {marker} effect {effect['effect']:+.2f} "
            f"95% CI [{effect['ci_low']:+.2f}, {effect['ci_high']:+.2f}] "
            f"({effect['stop_reason']})"
        )
    for note in payload["untestable"]:
        lines.append(f"  not tested  {note}")
    cost = payload["cost"]
    lines.append(
        f"  cost        {cost['total_calls']} calls "
        f"({cost['judge_calls']} judge, {cost['replay_calls']} replay)"
    )
    lines.append(f"  details     {payload['result_path']}")
    return "\n".join(lines)


def blame(
    run_id: str = typer.Argument(..., help="The recorded failure to attribute."),
    top: Annotated[int, typer.Option(help="How many judge suspects to test.")] = (
        DEFAULT_TOP_M
    ),
    n: Annotated[int, typer.Option(help="Maximum re-runs per arm.")] = DEFAULT_MAX_N,
    runs_dir: Annotated[Path, typer.Option(help="Tape and blob store root.")] = (
        DEFAULT_RUNS_DIR
    ),
    seed: Annotated[int, typer.Option(help="Seed for the re-run draws.")] = 0,
    concurrency: Annotated[int, typer.Option(help="Forks in flight within a batch.")] = 4,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Attribute a recorded failure to its earliest causal step."""
    from agent_bisect.adapters.tau2 import recording_session
    from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor, serialized_truth
    from agent_bisect.adapters.tau2_task import task_text
    from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
    from agent_bisect.core.budget import BudgetLedger
    from agent_bisect.core.config import get_settings
    from agent_bisect.core.tape import TapeWriter

    settings = get_settings()
    if not settings.has_nvidia_key:
        typer.echo(
            "NVIDIA_API_KEY not set; blame asks a judge and samples live re-runs.",
            err=True,
        )
        raise typer.Exit(code=MISSING_KEY_EXIT_CODE)

    store = BlobStore(runs_dir)
    reader = TapeReader(runs_dir)
    try:
        manifest = reader.get_manifest(run_id)
    except UnknownRunError:
        typer.echo(f"no run {run_id!r} in {runs_dir}", err=True)
        raise typer.Exit(code=UNKNOWN_RUN_EXIT_CODE) from None

    ledger = BudgetLedger(runs_dir / "ledger.sqlite")
    # The session installs the router for the whole diagnosis, so every
    # live re-run of every fork is limited, ledgered and recorded.
    with own_stdout(), recording_session(ledger=ledger, phase=DEFAULT_PHASE):
        run = blame_run(
            run_id,
            reader=reader,
            store=store,
            judge_backend=_backend(runs_dir, settings, ledger),
            executor=Tau2ForkExecutor(
                store=store, reader=reader, tape=TapeWriter(runs_dir)
            ),
            task_text=task_text,
            top_m=top,
            max_n=n,
            seed=seed,
            runs_dir=runs_dir,
            concurrency=concurrency,
            truth_for=serialized_truth(
                Tau2TruthResolver(manifest.domain, manifest.task_id, store)
            ),
        )

    payload = payload_of(run, runs_dir)
    typer.echo(
        json.dumps(payload, indent=2, sort_keys=True) if json_output
        else format_human(payload)
    )
    if payload["blamed_step"] is None:
        raise typer.Exit(code=NO_STEP_BLAMED_EXIT_CODE)


def _backend(runs_dir: Path, settings: Any, ledger: Any) -> JudgeBackend:
    """The real judge backend: ledgered, rate-limited, recorded before use."""
    from agent_bisect.attribution.judge_store import JudgeCallStore, LedgeredJudgeBackend
    from agent_bisect.core.limits import get_shared_limiter
    from agent_bisect.core.llm import LiteLLMTransport, LLMClient
    from agent_bisect.core.models import load_chosen_models

    model = load_chosen_models().judge

    def make_client(record_before_use):
        return LLMClient(
            LiteLLMTransport(),
            ledger,
            api_base=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key.get_secret_value(),
            limiter=get_shared_limiter(model),
            record_before_use=record_before_use,
        )

    return LedgeredJudgeBackend(
        make_client=make_client,
        store=JudgeCallStore(runs_dir),
        model=model,
        phase=DEFAULT_PHASE,
    )
