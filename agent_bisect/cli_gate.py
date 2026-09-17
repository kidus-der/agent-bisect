"""`bisect gate`: the P7 PR-check CLI command.

Thin: parses options, builds a `gate.action.GateConfig`, runs the pipeline,
prints the comment, and exits 0 (clean), 1 (regression) or 2 (error) --
the contract `.github/workflows/bisect-gate.yml` and `scripts/gates/p7.py`
both depend on.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import typer

from agent_bisect.gate.action import ERROR_EXIT, GateConfig, GateError, run_gate

DEFAULT_RUNS_DIR = Path("runs")


def gate(
    base: str = typer.Option(..., "--base", help="The ref to compare against (e.g. main)."),
    head: str = typer.Option(..., "--head", help="The ref under test (e.g. the PR branch)."),
    suite: str = typer.Option("demo", "--suite", help="Only 'demo' exists so far."),
    runs: int = typer.Option(4, "--runs", help="Runs per scenario, per side."),
    out: Path | None = typer.Option(
        None, "--out", help="Where to write the gate's evidence. Default: runs/gate/<random id>."
    ),
    seed: int = typer.Option(20260917, "--seed", help="Base seed for the demo suite."),
    repo: Path = typer.Option(
        Path("."), "--repo", help="The git repository to check `--base`/`--head` out of."
    ),
) -> None:
    """Run the demo suite on `--base` and `--head`, compare, and blame a regression."""
    if suite != "demo":
        typer.echo(f"unsupported suite {suite!r}: only 'demo' exists so far.", err=True)
        raise typer.Exit(code=ERROR_EXIT)

    out_dir = out or (DEFAULT_RUNS_DIR / "gate" / uuid.uuid4().hex[:12])
    config = GateConfig(
        repo=repo.resolve(), base=base, head=head, out=out_dir, runs=runs, seed=seed, suite=suite
    )
    try:
        exit_code, document = run_gate(config)
    except GateError as exc:
        typer.echo(f"gate error: {exc}", err=True)
        raise typer.Exit(code=ERROR_EXIT) from exc

    typer.echo(document["comment_markdown"])
    typer.echo(f"\nevidence written to {out_dir}")
    raise typer.Exit(code=exit_code)
