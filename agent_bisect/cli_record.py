"""`bisect record` — record tau2 runs to the tape.

A separate module from `cli.py` so the command can be built and tested on
its own; `cli.py` registers it with two lines
(`from agent_bisect.cli_record import record; app.command()(record)`).

    bisect record --domain airline --tasks 0-19 --trials 1

Resumable: re-running skips whatever already has a checkpoint, so a
crashed or interrupted batch is restarted with the same command and pays
for nothing twice.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TextIO

import typer

from agent_bisect.adapters.tau2 import RunSpec, recording_session
from agent_bisect.adapters.tau2_batch import (
    BatchItem,
    Checkpoint,
    items_for,
    pending,
    record_batch,
    summarise,
    tasks_from_range,
    with_task,
)
from agent_bisect.cli_io import own_stdout, say
from agent_bisect.core.budget import DEFAULT_LEDGER_PATH, BudgetLedger
from agent_bisect.core.config import get_settings
from agent_bisect.core.models import load_chosen_models
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

MISSING_KEY_EXIT_CODE = 1
#: Ledger cap for a P1 recording batch, from the run plan's call budget.
DEFAULT_CALL_CAP = 1500
DEFAULT_PHASE = "P1"
#: Module-level so the option default is not a call (ruff B008).
DEFAULT_RUNS_DIR = Path("runs")


def _reporter(stream: TextIO) -> Callable[[Checkpoint], None]:
    """A progress callback writing to the command's own stdout.

    Not `typer.echo`: inside `own_stdout()` that would resolve to the
    redirected stream and the batch would run silently.
    """

    def report(checkpoint: Checkpoint) -> None:
        status = checkpoint.error or (
            "pass" if checkpoint.passed else f"reward={checkpoint.reward}"
        )
        say(
            stream,
            f"  {checkpoint.run_id}: {status} "
            f"({checkpoint.steps} steps, {checkpoint.termination_reason})",
        )

    return report


def record(
    domain: str = typer.Option("airline", help="tau2 domain to record."),
    tasks: str = typer.Option("0-19", help='Task ids: "0-19", "0,3,7" or "4".'),
    trials: int = typer.Option(1, help="Runs per task."),
    agent_model: str = typer.Option("", help="Agent model id. Default: the P0 choice."),
    user_model: str = typer.Option("", help="User-simulator model id. Default: the P0 choice."),
    seed: int = typer.Option(300, help="Seed pinned into every run manifest."),
    temperature: float = typer.Option(
        -1.0, help="Sampling temperature. Default: the pinned agent temperature."
    ),
    runs_dir: Annotated[
        Path, typer.Option(help="Tape, blob store and checkpoint root.")
    ] = DEFAULT_RUNS_DIR,
    concurrency: int = typer.Option(1, help="Runs recorded at once."),
    phase: str = typer.Option(DEFAULT_PHASE, help="Ledger phase for these calls."),
    max_calls: int = typer.Option(DEFAULT_CALL_CAP, help="Hard ledger cap for this batch."),
    ledger_path: Annotated[
        Path, typer.Option("--ledger", help="Call ledger to reserve against.")
    ] = DEFAULT_LEDGER_PATH,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Record tau2 runs, resuming from whatever is already on disk."""
    settings = get_settings()
    if not settings.has_nvidia_key:
        typer.echo("NVIDIA_API_KEY not set; cannot record.", err=True)
        raise typer.Exit(code=MISSING_KEY_EXIT_CODE)

    chosen = load_chosen_models()
    items = items_for(domain, tasks_from_range(tasks), trials=trials)
    store = BlobStore(runs_dir)
    tape = TapeWriter(runs_dir)
    reader = TapeReader(runs_dir)
    template = RunSpec(
        domain=domain,
        task_id="",
        agent_model=agent_model or chosen.agent,
        user_model=user_model or chosen.user_sim,
        seed=seed,
        temperature=chosen.agent_temperature if temperature < 0 else temperature,
    )
    outstanding = pending(runs_dir, items)
    if not json_output:
        typer.echo(
            f"{len(items)} runs, {len(outstanding)} outstanding "
            f"(agent {template.agent_model}, user {template.user_model})"
        )

    # The cap is this phase's budget, not the file's: the same ledger
    # already carries every call P0 spent.
    ledger = BudgetLedger(ledger_path, max_calls=max_calls, cap_scope="phase")
    with own_stdout() as stdout, recording_session(ledger=ledger, phase=phase):
        checkpoints = record_batch(
            items,
            spec_for=lambda item: _spec_for(template, item),
            store=store,
            tape=tape,
            reader=reader,
            root=runs_dir,
            concurrency=concurrency,
            on_done=None if json_output else _reporter(stdout),
        )

    summary = {
        **summarise(checkpoints),
        "calls": ledger.totals_per_phase().get(phase, 0),
        "calls_by_model": ledger.totals_per_model(),
    }
    if json_output:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        typer.echo(
            f"recorded {summary['recorded']}, aborted_infra {summary['aborted_infra']}, "
            f"pass rate {summary['pass_rate']}, {summary['calls']} calls"
        )


def _spec_for(template: RunSpec, item: BatchItem) -> RunSpec:
    return with_task(template, item)
