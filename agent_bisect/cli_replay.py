"""`bisect replay RUN_ID` — re-run a recording from the tape, with no network.

A separate module from `cli.py` so the command can be built and tested on
its own; `cli.py` registers it with two lines
(`from agent_bisect.cli_replay import replay; app.command()(replay)`).

    bisect replay airline-0-t0

Exits 0 when the replay was step-identical and reached the same reward,
and 3 on `DivergenceError`, which is a distinct code because a divergence
is a finding about the recording, not a usage error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from agent_bisect.adapters.tau2_replay import replay_run
from agent_bisect.cli_io import own_stdout
from agent_bisect.core.replay import DivergenceError
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, UnknownRunError

DIVERGENCE_EXIT_CODE = 3
UNKNOWN_RUN_EXIT_CODE = 4
#: Module-level so the option default is not a call (ruff B008).
DEFAULT_RUNS_DIR = Path("runs")


def replay(
    run_id: str = typer.Argument(..., help="The recorded run to replay."),
    runs_dir: Annotated[Path, typer.Option(help="Tape and blob store root.")] = DEFAULT_RUNS_DIR,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Replay a recorded run from the tape. Makes no network call, ever."""
    store = BlobStore(runs_dir)
    reader = TapeReader(runs_dir)
    try:
        with own_stdout():
            result = replay_run(run_id, store=store, reader=reader)
    except UnknownRunError:
        typer.echo(f"no run {run_id!r} in {runs_dir}", err=True)
        raise typer.Exit(code=UNKNOWN_RUN_EXIT_CODE) from None
    except DivergenceError as error:
        _report_divergence(error, json_output)
        raise typer.Exit(code=DIVERGENCE_EXIT_CODE) from None

    payload = {
        "run_id": result.run_id,
        "steps": result.steps,
        "reward": None if result.outcome is None else result.outcome.reward,
        "passed": None if result.outcome is None else result.outcome.passed,
        "termination_reason": result.termination_reason,
        "tape_llm_calls": result.tape_llm_calls,
        "live_llm_calls": result.live_llm_calls,
        "identical": True,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(
            f"✓ {result.run_id}: {result.steps} steps replayed identically, "
            f"reward {payload['reward']}, {result.tape_llm_calls} responses from tape, "
            f"{result.live_llm_calls} live calls"
        )


def _report_divergence(error: DivergenceError, json_output: bool) -> None:
    payload = {
        "identical": False,
        "step_idx": error.step_idx,
        "actor": error.actor,
        "expected": error.expected,
        "got": error.got,
        "diff": error.diff,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"✗ diverged at step {error.step_idx} (actor {error.actor})", err=True)
    typer.echo(f"  expected {error.expected}", err=True)
    typer.echo(f"  got      {error.got}", err=True)
    typer.echo(f"  {error.diff}", err=True)
