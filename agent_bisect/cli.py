"""Bisect CLI.

Only `doctor` is implemented. Every other command is a placeholder that
exits with code 2 until its phase lands — see `docs/LOOP_STATE.md` for the
phase board.
"""

from __future__ import annotations

import json

import typer

from agent_bisect.core.config import get_settings
from agent_bisect.core.doctor import CheckResult, run_doctor

app = typer.Typer(help="Bisect: counterfactual replay for LLM agent failures.")

NOT_IMPLEMENTED_EXIT_CODE = 2
DOCTOR_FAILURE_EXIT_CODE = 1


def _not_implemented(phase: str) -> None:
    typer.echo(f"not implemented yet (phase {phase})")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


def _print_human(results: list[CheckResult]) -> None:
    for result in results:
        mark = "✓" if result.passed else "✗"
        typer.echo(f"{mark} {result.name}: {result.detail}")


def _print_json(results: list[CheckResult]) -> None:
    payload = [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results]
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Check the environment: key presence, tooling, tau2, NIM reachability, measured thresholds."""
    settings = get_settings()
    results = run_doctor(settings)

    if json_output:
        _print_json(results)
    else:
        _print_human(results)

    if not all(result.passed for result in results):
        raise typer.Exit(code=DOCTOR_FAILURE_EXIT_CODE)


@app.command()
def record() -> None:
    """Record an agent run (phase P1)."""
    _not_implemented("P1")


@app.command()
def replay() -> None:
    """Replay a recorded run from a snapshot (phase P2)."""
    _not_implemented("P2")


@app.command()
def blame() -> None:
    """Attribute a failure to its earliest causal step (phase P5)."""
    _not_implemented("P5")


@app.command()
def inject() -> None:
    """Plant a fault into a recorded run (phase P3)."""
    _not_implemented("P3")


@app.command(name="eval")
def eval_() -> None:
    """Evaluate Bisect against baselines on the frozen test split (phase P5)."""
    _not_implemented("P5")


@app.command()
def serve() -> None:
    """Serve the dashboard (phase P6)."""
    _not_implemented("P6")


@app.command()
def gate() -> None:
    """Run the PR regression gate (phase P7)."""
    _not_implemented("P7")


if __name__ == "__main__":
    app()
