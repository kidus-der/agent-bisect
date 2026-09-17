"""`bisect eval --split test` — Bisect against every baseline, on a frozen split.

A separate module from `cli.py` so the command can be built and tested on
its own; `cli.py` registers it with two lines.

    bisect eval --split dev            # tuning happens here, and only here
    bisect eval --split test           # once, after 0014 says tuning is done
    bisect eval --split test --resume  # continue that one run after a stop
    bisect eval --split test --report-only   # rebuild the report, spend nothing

Three refusals, all of them before any call is made:

1. the manifest must be **frozen** and match its hash
   (`bench/manifest.load_frozen`);
2. for the test split, `docs/decisions/0014-p5-freeze.md` must exist and the
   split must not already have been opened (`bench/split_lock`);
3. without a key there is nothing to evaluate with.

`--report-only` is the `make reproduce` path: it reads the stored
per-`(item, method)` table and rebuilds every number offline, without a
judge, a fork or a network call. It is also how a number is re-checked
without re-opening the test split.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import typer

from agent_bisect.attribution.estimate import DEFAULT_MAX_N, SequentialConfig
from agent_bisect.bench.baselines import BaselineConfig
from agent_bisect.bench.eval_run import evaluate_dataset, outcome_rows, outcomes_from_rows
from agent_bisect.bench.evaluate import DEFAULT_TOP_M, build_report, score_outcomes
from agent_bisect.bench.manifest import (
    DEFAULT_MANIFEST_PATH,
    ManifestNotFrozenError,
    ManifestTamperedError,
    load_frozen,
)
from agent_bisect.bench.results import (
    DEFAULT_RESULTS_DIR,
    DEFAULT_RUNS_SUBDIR,
    read_outcome_rows,
    write_results,
)
from agent_bisect.bench.split_lock import SplitLockedError, guard
from agent_bisect.cli_io import own_stdout
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader

MISSING_KEY_EXIT_CODE = 1
MANIFEST_EXIT_CODE = 6
SPLIT_LOCKED_EXIT_CODE = 7
SENSITIVITY_SPLIT_EXIT_CODE = 8
#: Module-level so the option default is not a call (ruff B008).
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_PHASE = "P5"
DEFAULT_SEED = 20260917


def _report_only(
    *,
    split: str,
    seed: int,
    manifest_path: Path,
    out_dir: Path,
    results_dir: Path,
) -> dict[str, Any]:
    """Rebuild every number from the stored table. No judge, no fork, no network."""
    manifest = load_frozen(manifest_path)
    items = manifest.split(split)  # type: ignore[arg-type]
    outcomes = outcomes_from_rows(read_outcome_rows(out_dir))
    scores = score_outcomes(items, outcomes)
    report = build_report(
        scores,
        split=split,
        seed=seed,
        manifest_digest=manifest.digest,
        estimator_config=manifest.config,
        measured_to_m=int(manifest.config.get("top_m", DEFAULT_TOP_M)),
    )
    write_results(
        scores=scores,
        outcome_rows=outcome_rows(outcomes),
        report=report,
        runs_dir=out_dir,
        results_dir=results_dir,
    )
    return report


def _per_step_sensitivity(
    items: Sequence[Any],
    primary: BaselineConfig,
    base_kwargs: dict[str, Any],
    *,
    seed: int,
    methods: tuple[str, ...] = ("bisect",),
) -> dict[str, Any]:
    """Re-run Bisect against a per-step control, beside the primary.

    Decision 0016 keeps this as a **dev-split** analysis: it is the check
    that `docs/decisions/0005-shared-control.md` says exists, it costs a
    second control arm per tested step, and it answers "does the shared
    arm's flat-control assumption hold on real runs" without touching the
    pre-registered primary.
    """
    config = BaselineConfig(
        top_m=primary.top_m,
        sequential=primary.sequential,
        control_mode="per_step",
        methods=methods,  # type: ignore[arg-type]
    )
    run = evaluate_dataset(items, config=config, seed=seed, **base_kwargs)
    scores = score_outcomes(items, run.outcomes)
    return {
        "control_mode": "per_step",
        "split": "dev",
        "n_items": len({score.item_id for score in scores}),
        "accuracy": {
            method: sum(1 for s in scores if s.method == method and s.correct)
            / max(1, sum(1 for s in scores if s.method == method))
            for method in methods
        },
        "n_control_flags": run.n_control_flags,
        "note": (
            "per-step control: each suspect is compared with a control forked at "
            "that same step. Reported beside the primary, never in place of it."
        ),
    }


def _summarise(report: dict[str, Any], failures: int) -> str:
    lines = [f"split {report['config']['split']} · {report['config']['n_items']} items"]
    for row in report["methods"]:
        accuracy = row["accuracy"]
        lines.append(
            f"  {row['method']:<20} {accuracy['value']:.3f} "
            f"[{accuracy['ci_low']:.3f}, {accuracy['ci_high']:.3f}] "
            f"· {row['mean_calls']:.0f} calls/diagnosis"
        )
    gap = report.get("gap")
    if gap:
        lines.append(
            f"  gap vs {gap['comparator']}: {gap['points']:+.1f} points, "
            f"95% CI [{gap['ci_low']:+.3f}, {gap['ci_high']:+.3f}]"
        )
    if failures:
        lines.append(f"  {failures} item(s) could not be evaluated; scored as wrong")
    scope = report.get("scope") or {}
    if scope.get("n_control_flags"):
        lines.append(
            f"  {scope['n_control_flags']} item(s) whose control did not reproduce "
            "the recorded failure; reported, not dropped"
        )
    return "\n".join(lines)


def eval_(
    split: Annotated[str, typer.Option(help="Which frozen split to evaluate.")] = "dev",
    manifest: Annotated[Path, typer.Option(help="The frozen dataset manifest.")] = (
        DEFAULT_MANIFEST_PATH
    ),
    runs_dir: Annotated[Path, typer.Option(help="Tape and blob store root.")] = (
        DEFAULT_RUNS_DIR
    ),
    out_dir: Annotated[Path, typer.Option(help="Where the tidy tables go.")] = (
        DEFAULT_RUNS_SUBDIR
    ),
    results_dir: Annotated[Path, typer.Option(help="Where the committed summary goes.")] = (
        DEFAULT_RESULTS_DIR
    ),
    top: Annotated[int, typer.Option(help="Judge shortlist size (m).")] = DEFAULT_TOP_M,
    n: Annotated[int, typer.Option(help="Maximum re-runs per arm (N).")] = DEFAULT_MAX_N,
    seed: Annotated[int, typer.Option(help="Seed for draws and the bootstrap.")] = (
        DEFAULT_SEED
    ),
    resume: bool = typer.Option(False, help="Continue an interrupted test-split run."),
    per_step_sensitivity: bool = typer.Option(
        False,
        "--per-step-sensitivity",
        help="Also run the per-step control arm (dev split only; doubles replay spend).",
    ),
    report_only: bool = typer.Option(
        False, "--report-only", help="Rebuild the report from stored results. Offline."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Evaluate Bisect against the baselines on a frozen split."""
    try:
        frozen = load_frozen(manifest)
    except (ManifestNotFrozenError, ManifestTamperedError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=MANIFEST_EXIT_CODE) from None

    if report_only:
        report = _report_only(
            split=split, seed=seed, manifest_path=manifest,
            out_dir=out_dir, results_dir=results_dir,
        )
        typer.echo(
            json.dumps(report, indent=2, sort_keys=True) if json_output
            else _summarise(report, 0)
        )
        return

    if per_step_sensitivity and split != "dev":
        typer.echo(
            "--per-step-sensitivity is a dev-split analysis (decision 0016): it doubles "
            "replay spend and the test split is touched once, at the pre-registered "
            "shared-control configuration.",
            err=True,
        )
        raise typer.Exit(code=SENSITIVITY_SPLIT_EXIT_CODE)

    try:
        opening = guard(split, out_dir, resume=resume)
    except SplitLockedError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=SPLIT_LOCKED_EXIT_CODE) from None
    if opening is not None and not json_output:
        typer.echo(
            f"test split opened at {opening.opened_at}"
            + (" (resumed)" if opening.resumed else "")
        )

    from agent_bisect.adapters.tau2 import recording_session
    from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor
    from agent_bisect.adapters.tau2_task import task_text
    from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
    from agent_bisect.cli_blame import _backend
    from agent_bisect.core.budget import BudgetLedger
    from agent_bisect.core.config import get_settings
    from agent_bisect.core.tape import TapeWriter

    settings = get_settings()
    if not settings.has_nvidia_key:
        typer.echo("NVIDIA_API_KEY not set; eval asks a judge and re-runs live.", err=True)
        raise typer.Exit(code=MISSING_KEY_EXIT_CODE)

    items = frozen.split(split)  # type: ignore[arg-type]
    store = BlobStore(runs_dir)
    reader = TapeReader(runs_dir)
    ledger = BudgetLedger(runs_dir / "ledger.sqlite")

    sequential = SequentialConfig(
        max_n=n, efficacy_boundary="obf" if n == DEFAULT_MAX_N else "none"
    )
    base_kwargs: dict[str, Any] = dict(
        reader=reader,
        store=store,
        judge_backend=_backend(runs_dir, settings, ledger),
        executor=Tau2ForkExecutor(store=store, reader=reader, tape=TapeWriter(runs_dir)),
        task_text=task_text,
        runs_dir=runs_dir,
        truth_for_item=lambda item: Tau2TruthResolver(item.domain, item.task_id, store),
    )

    with own_stdout(), recording_session(ledger=ledger, phase=DEFAULT_PHASE):
        run = evaluate_dataset(
            items,
            config=BaselineConfig(top_m=top, sequential=sequential),
            seed=seed,
            **base_kwargs,
        )

    sensitivity = None
    if per_step_sensitivity:
        sensitivity = _per_step_sensitivity(
            items,
            BaselineConfig(top_m=top, sequential=sequential),
            base_kwargs,
            seed=seed,
        )

    scores = score_outcomes(items, run.outcomes)
    report = build_report(
        scores,
        split=split,
        seed=seed,
        manifest_digest=frozen.digest,
        estimator_config=frozen.config,
        control_flags=run.flag_rows(),
        unevaluated=run.failure_rows(),
        unguarded_calls=run.bisect_unguarded_calls,
        sensitivity=sensitivity,
        measured_to_m=top,
    )
    written = write_results(
        scores=scores,
        outcome_rows=outcome_rows(run.outcomes),
        report=report,
        runs_dir=out_dir,
        results_dir=results_dir,
    )
    if json_output:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
        return
    typer.echo(_summarise(report, run.n_failed_items))
    typer.echo(f"  summary     {written.summary}")
    for failure in run.failures:
        typer.echo(f"  unevaluated {failure.item_id}: {failure.reason}", err=True)
