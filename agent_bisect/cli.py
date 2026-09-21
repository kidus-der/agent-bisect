"""Bisect CLI.

Only `doctor` is implemented. Every other command is a placeholder that
exits with code 2 until its phase lands — see `docs/LOOP_STATE.md` for the
phase board.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from agent_bisect.cli_blame import blame
from agent_bisect.cli_eval import eval_
from agent_bisect.cli_gate import gate
from agent_bisect.cli_inject import app as inject_app
from agent_bisect.cli_record import record
from agent_bisect.cli_replay import replay
from agent_bisect.core.config import get_settings
from agent_bisect.core.doctor import CheckResult, run_doctor
from agent_bisect.server.runserver import DEFAULT_HOST, DEFAULT_PORT, run_server
from agent_bisect.server.settings import DataSource

app = typer.Typer(help="Bisect: counterfactual replay for LLM agent failures.")

NOT_IMPLEMENTED_EXIT_CODE = 2
DOCTOR_FAILURE_EXIT_CODE = 1
SERVE_USAGE_EXIT_CODE = 2
#: Module-level so the option default is not a call (ruff B008).
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_DATA_DIR = Path("data")
DEFAULT_MODELS_PATH = Path("config/models.toml")


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
    live: bool = typer.Option(
        False,
        "--live",
        help="Run ONE real τ² airline task end to end with the chosen models "
        "(makes API calls). Without it, the recorded result is verified instead.",
    ),
) -> None:
    """Check the environment: key presence, tooling, tau2, NIM reachability, measured thresholds."""
    settings = get_settings()
    results = run_doctor(settings, live=live)

    if json_output:
        _print_json(results)
    else:
        _print_human(results)

    if not all(result.passed for result in results):
        raise typer.Exit(code=DOCTOR_FAILURE_EXIT_CODE)


app.command()(record)
app.command()(replay)
app.command()(blame)
app.command(name="eval")(eval_)
app.add_typer(inject_app, name="inject")








@app.command()
def serve(
    host: str = typer.Option(DEFAULT_HOST, help="Address to bind."),
    port: int = typer.Option(DEFAULT_PORT, help="Port to bind."),
    fixture: bool = typer.Option(
        False, "--fixture", help="Serve the simulated dataset instead of the recordings."
    ),
    real: bool = typer.Option(
        False, "--real", help="Serve the recordings; fail if there are none."
    ),
    runs_dir: Annotated[
        Path, typer.Option(help="Where the recordings live.")
    ] = DEFAULT_RUNS_DIR,
    data_dir: Annotated[
        Path,
        typer.Option(
            "--data-dir", help="Real mode only: where data/manifest.json and data/results/ live."
        ),
    ] = DEFAULT_DATA_DIR,
) -> None:
    """Serve the dashboard at http://127.0.0.1:8484 (phase P6)."""
    if fixture and real:
        typer.echo("--fixture and --real are mutually exclusive.", err=True)
        raise typer.Exit(code=SERVE_USAGE_EXIT_CODE)

    has_recordings = (runs_dir / "index.sqlite").exists()
    if real and not has_recordings:
        typer.echo(
            f"no recorded runs under {runs_dir} — record some first, or use --fixture.",
            err=True,
        )
        raise typer.Exit(code=SERVE_USAGE_EXIT_CODE)

    data_source: DataSource = "fixture" if fixture or not has_recordings else "real"
    if data_source == "fixture":
        # Never quietly: a dashboard of simulated numbers that does not say
        # so is indistinguishable from a dashboard of results.
        typer.echo("serving SIMULATED fixture data — these numbers are not results")
    else:
        typer.echo(f"serving real recordings from {runs_dir}")
    typer.echo(f"http://{host}:{port}")

    run_server(
        host,
        port,
        data_source,
        explicit_host=host != DEFAULT_HOST,
        runs_dir=runs_dir,
        data_dir=data_dir,
        models_path=DEFAULT_MODELS_PATH,
    )


app.command()(gate)


if __name__ == "__main__":
    app()
