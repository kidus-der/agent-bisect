"""`bisect inject` — collect planted-fault failures, then freeze the split.

Three commands, because collection is hours of API time and freezing is
the irreversible act at the end of it:

    bisect inject collect --domain airline --tasks 0-19
    bisect inject status
    bisect inject freeze

`collect` is resumable: re-running the same command skips everything that
already has a checkpoint under `runs/p3/`, so a batch that died or was
stopped is restarted with the same line and pays for nothing twice. Every
call goes through the ledger under the phase's hard cap; a spent budget
or a rejected key stops it cleanly with the work so far intact.

`freeze` writes `data/manifest.json` and `data/manifest.sha256` from the
kept candidates and refuses to overwrite a manifest that already exists —
the dev:test split is frozen once, before any P5 evaluation
(`docs/decisions/0001-preregistration.md`).

A separate module from `cli.py` so it can be built and tested on its own;
`cli.py` registers it with two lines:

    from agent_bisect.cli_inject import app as inject_app
    app.add_typer(inject_app, name="inject")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from agent_bisect.adapters.tau2 import recording_session, tau2_commit
from agent_bisect.adapters.tau2_batch import tasks_from_range
from agent_bisect.adapters.tau2_flaky import FlakyConfig, canonical_rewards
from agent_bisect.adapters.tau2_inject import Tau2InjectRunner
from agent_bisect.adapters.tau2_judge import judge_routed
from agent_bisect.adapters.tau2_tasks import collection_order, shard_of
from agent_bisect.bench.inject import InjectConfig
from agent_bisect.bench.inject import collect as run_collection
from agent_bisect.bench.journal import Journal
from agent_bisect.bench.manifest import (
    DEFAULT_MANIFEST_PATH,
    ManifestExistsError,
)
from agent_bisect.bench.manifest import (
    freeze as freeze_manifest,
)
from agent_bisect.cli_io import own_stdout, say
from agent_bisect.core.budget import DEFAULT_LEDGER_PATH, BudgetLedger
from agent_bisect.core.config import get_settings
from agent_bisect.core.models import load_chosen_models
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

MISSING_KEY_EXIT_CODE = 1
FROZEN_EXIT_CODE = 2
NOTHING_TO_FREEZE_EXIT_CODE = 3
#: The run plan's P3 budget, as a hard ledger cap.
DEFAULT_CALL_CAP = 12_000
DEFAULT_PHASE = "P3"
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_WORK_DIR = Path("runs/p3")

app = typer.Typer(help="Plant faults on stable successes and freeze the dataset.")


@app.command()
def collect(
    domain: str = typer.Option("airline", help="tau2 domain to collect from."),
    tasks: str = typer.Option("0-19", help='Task ids: "0-19", "0,3,7" or "4".'),
    all_tasks: bool = typer.Option(
        False, "--all-tasks",
        help="Every task, cheapest-to-score first (decision 0017). Ignores --domain/--tasks.",
    ),
    shard: int = typer.Option(0, help="This worker's index, for a sharded collection."),
    shards: int = typer.Option(1, help="How many workers share this journal."),
    max_hours: float = typer.Option(
        0.0, help="Wall-clock budget; 0 means no limit. The floor still applies."
    ),
    floor: int = typer.Option(
        InjectConfig().floor_items, help="Never stop on time below this many items."
    ),
    agent_model: str = typer.Option("", help="Agent model id. Default: the P0 choice."),
    user_model: str = typer.Option("", help="User-simulator model id. Default: the P0 choice."),
    seed: int = typer.Option(300, help="Seed pinned into every base run manifest."),
    collection_seed: int = typer.Option(
        InjectConfig().seed, help="Seed for fault choice, strata order and re-run seeds."
    ),
    attempts_per_bucket: int = typer.Option(
        InjectConfig().attempts_per_bucket, help="Candidate tries per position bucket."
    ),
    target: int = typer.Option(InjectConfig().target_items, help="Stop once this many are kept."),
    runs_dir: Annotated[
        Path, typer.Option(help="Tape and blob store root.")
    ] = DEFAULT_RUNS_DIR,
    work_dir: Annotated[
        Path, typer.Option(help="Checkpoints and the decision log.")
    ] = DEFAULT_WORK_DIR,
    phase: str = typer.Option(DEFAULT_PHASE, help="Ledger phase for these calls."),
    max_calls: int = typer.Option(DEFAULT_CALL_CAP, help="Hard ledger cap for this batch."),
    ledger_path: Annotated[
        Path, typer.Option("--ledger", help="Call ledger to reserve against.")
    ] = DEFAULT_LEDGER_PATH,
    concurrency: int = typer.Option(
        1, help="Tasks in flight at once. Roughly the number of model calls in flight."
    ),
    flaky: bool = typer.Option(
        False, "--flaky", help="Collect in the flaky world (decisions 0011, 0017 section 4)."
    ),
    flaky_error_rate: float = typer.Option(0.05, help="Injected tool-error probability."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Record, check, fault and re-run, resuming from whatever is on disk."""
    settings = get_settings()
    if not settings.has_nvidia_key:
        typer.echo("NVIDIA_API_KEY not set; cannot collect.", err=True)
        raise typer.Exit(code=MISSING_KEY_EXIT_CODE)

    chosen = load_chosen_models()
    config = InjectConfig(
        attempts_per_bucket=attempts_per_bucket,
        seed=collection_seed,
        target_items=target,
        floor_items=floor,
        max_seconds=max_hours * 3600 if max_hours > 0 else None,
    )
    journal = Journal(work_dir)
    ledger = BudgetLedger(ledger_path, max_calls=max_calls)
    task_list = shard_of(
        collection_order() if all_tasks
        else [(domain, task_id) for task_id in tasks_from_range(tasks)],
        shard,
        shards,
    )
    if not json_output:
        typer.echo(
            f"shard {shard}/{shards}: {len(task_list)} tasks, {concurrency} in flight, "
            f"target {target} items (floor {floor}), cap {max_calls} calls"
        )

    world = (
        FlakyConfig(seed=collection_seed, p_error=flaky_error_rate) if flaky else None
    )
    with (
        own_stdout() as stdout,
        recording_session(ledger=ledger, phase=phase) as router,
        canonical_rewards(),
        judge_routed() as judge,
    ):
        if not json_output:
            typer.echo(f"tau2's NL-assertion judge routed to {judge}")
        runner = Tau2InjectRunner(
            store=BlobStore(runs_dir),
            tape=TapeWriter(runs_dir),
            reader=TapeReader(runs_dir),
            agent_model=agent_model or chosen.agent,
            user_model=user_model or chosen.user_sim,
            seed=seed,
            temperature=chosen.agent_temperature,
            flaky=world,
            # The router, captured explicitly, never read off tau2's seam
            # at fork time. Once any fork is in flight the seam holds the
            # replay dispatcher, so a fork that read it there would call
            # the dispatcher, which routes back to that same fork's own
            # completion, which calls the dispatcher: unbounded recursion,
            # and 45 candidates died of it before this line existed.
            live_completion=router.completion,
        )
        result = run_collection(
            runner,
            tasks=task_list,
            journal=journal,
            config=config,
            on_progress=None if json_output else (lambda line: say(stdout, f"  {line}")),
            runs_dir=runs_dir,
            calls_spent=ledger.total_calls,
            concurrency=concurrency,
        )

    summary = {
        "items": len(result.items),
        "stopped_reason": result.stopped_reason,
        "calls": ledger.total_calls(),
        **result.counts,
    }
    _report(summary, json_output)


@app.command()
def status(
    work_dir: Annotated[Path, typer.Option(help="Checkpoints and the decision log.")]
    = DEFAULT_WORK_DIR,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """The funnel so far, from the decision log. Costs nothing."""
    journal = Journal(work_dir)
    kept = _kept_items(journal)
    counts: dict[str, Any] = {"kept": len(kept)}
    for event in journal.events():
        name = f"{event.get('kind')}_{event.get('status')}"
        counts[name] = int(counts.get(name, 0)) + 1
    counts["by_fault_type"] = _tally(item["fault_type"] for item in kept)
    counts["by_position"] = _tally(item["position_bucket"] for item in kept)
    counts["by_domain"] = _tally(item["domain"] for item in kept)
    _report(counts, json_output)


@app.command()
def freeze(
    work_dir: Annotated[Path, typer.Option(help="Checkpoints and the decision log.")]
    = DEFAULT_WORK_DIR,
    out: Annotated[Path, typer.Option(help="Manifest path.")] = DEFAULT_MANIFEST_PATH,
    judge_model: str = typer.Option("", help="Judge model id. Default: the P0 choice."),
    unsplit: bool = typer.Option(
        False, "--unsplit",
        help="Freeze without a dev:test split, for a set nothing is tuned on (the flaky world).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Freeze the 1:2 dev:test split. Refuses to overwrite a frozen manifest."""
    journal = Journal(work_dir)
    items = _kept_items(journal)
    if not items:
        typer.echo(f"no kept items under {work_dir}; nothing to freeze.", err=True)
        raise typer.Exit(code=NOTHING_TO_FREEZE_EXIT_CODE)

    chosen = load_chosen_models()
    try:
        path = freeze_manifest(
            items,
            path=out,
            models={"agent": chosen.agent, "user_sim": chosen.user_sim,
                    "judge": judge_model or chosen.judge},
            tau2_commit=tau2_commit(),
            config=InjectConfig().as_dict(),
            counts=_funnel(journal),
            created_at=datetime.now(UTC),
            assign_split=not unsplit,
        )
    except ManifestExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=FROZEN_EXIT_CODE) from exc

    _report({"manifest": str(path), "items": len(items),
             "sha256": path.with_suffix(".sha256").read_text().strip()}, json_output)


def _kept_items(journal: Journal) -> list[dict[str, Any]]:
    """Every kept item, in a stable order. The dataset, before it is split."""
    items = [
        record["item"]
        for record in journal.all("candidate")
        if record.get("status") == "kept" and record.get("item")
    ]
    return sorted(items, key=lambda item: item["item_id"])


def _funnel(journal: Journal) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in journal.all("candidate"):
        name = f"candidate_{record.get('reason_code', 'unknown')}"
        counts[name] = counts.get(name, 0) + 1
    for record in journal.all("stability"):
        name = "stable" if record.get("stable") else "unstable"
        counts[name] = counts.get(name, 0) + 1
    counts["base_runs"] = len(journal.all("base"))
    return counts


def _tally(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _report(summary: dict[str, Any], json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True, default=str))
        return
    for key, value in sorted(summary.items()):
        typer.echo(f"{key}: {value}")
