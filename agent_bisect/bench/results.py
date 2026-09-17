"""Where P5's numbers land, and in what shape.

Three destinations, each with a different reader in mind:

- `runs/p5/outcomes.parquet` — the tidy per-`(item, method)` table, one row
  per answer. It is the *input* `make reproduce` replays: `build_report` is
  a pure function of these rows and the manifest, so the report can be
  rebuilt offline without re-running an agent or a judge.
- `runs/p5/report.json` — the full report, including the failure cases and
  the cost curve. Not committed: it is large and derivable.
- `data/results/p5_summary.json` + `data/results/p5_items.json` —
  **committed**, small, payload-free. The dashboard's real repository, the
  P5 gate and the P8 report read these. `p5_items.json` is one row per
  `(item, method)` with the label, the answer and the cost — no
  trajectories, no tool results, nothing that could carry a secret.

Every file is written atomically and with sorted keys, so re-running the
same evaluation produces byte-identical output and a diff means a number
changed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_bisect.bench.evaluate import ScoredItem

DEFAULT_RUNS_SUBDIR = Path("runs/p5")
DEFAULT_RESULTS_DIR = Path("data/results")

OUTCOMES_PARQUET = "outcomes.parquet"
OUTCOMES_JSON = "outcomes.json"
REPORT_JSON = "report.json"
SUMMARY_JSON = "p5_summary.json"
ITEMS_JSON = "p5_items.json"

#: Keys of the full report that the committed summary keeps. `failures` and
#: `cost_curve` stay in the big file: the summary is meant to be read in a
#: diff.
SUMMARY_KEYS = (
    "config",
    "methods",
    "gap",
    "recall",
    "recall_provenance",
    "heatmap",
    "by_position",
    "sankey",
    "flaky_ablation",
    "scope",
    "sensitivity",
    "integrity",
)


@dataclass(frozen=True, slots=True)
class WrittenResults:
    """Where everything went, so a caller can print it."""

    outcomes: Path
    report: Path
    summary: Path
    items: Path
    parquet: Path | None


def _write_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def item_rows(scores: Sequence[ScoredItem]) -> list[dict[str, Any]]:
    """One payload-free row per `(item, method)`: the label, the answer, the cost."""
    return [
        {
            "item_id": score.item_id,
            "run_id": score.run_id,
            "task_group": score.task_group,
            "domain": score.domain,
            "split": score.split,
            "fault_type": score.fault_type,
            "position_bucket": score.position_bucket,
            "planted_step": score.planted_step,
            "method": score.method,
            "predicted_step": score.predicted_step,
            "verdict": score.verdict,
            "correct": score.correct,
            "shortlist_hit": score.shortlist_hit,
            "judge_calls": score.judge_calls,
            "replay_calls": score.replay_calls,
            "total_calls": score.total_calls,
            "reruns": score.reruns,
            "parse_failed": score.parse_failed,
        }
        for score in sorted(scores, key=lambda row: (row.item_id, row.method))
    ]


def _write_parquet(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path | None:
    """Write the tidy table as Parquet, or `None` if polars is unavailable.

    The JSON copy beside it is authoritative: Parquet is a convenience for
    analysis, and a missing optional writer must not lose the numbers.
    """
    if not rows:
        return None
    try:
        import polars
    except ImportError:  # pragma: no cover - polars is a declared dependency
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    # `ranking`/`shortlist` are variable-length lists of ints, which Parquet
    # handles, but a row with an all-null column would make polars guess;
    # the schema is inferred from the whole frame at once instead.
    polars.DataFrame(list(rows), strict=False).write_parquet(path)
    return path


def write_results(
    *,
    scores: Sequence[ScoredItem],
    outcome_rows: Sequence[Mapping[str, Any]],
    report: Mapping[str, Any],
    runs_dir: Path = DEFAULT_RUNS_SUBDIR,
    results_dir: Path = DEFAULT_RESULTS_DIR,
) -> WrittenResults:
    """Write every P5 output. Deterministic and atomic."""
    outcomes_json = _write_atomic(runs_dir / OUTCOMES_JSON, _dump(list(outcome_rows)))
    parquet = _write_parquet(runs_dir / OUTCOMES_PARQUET, outcome_rows)
    report_path = _write_atomic(runs_dir / REPORT_JSON, _dump(dict(report)))
    summary = {key: report[key] for key in SUMMARY_KEYS if key in report}
    summary_path = _write_atomic(results_dir / SUMMARY_JSON, _dump(summary))
    items_path = _write_atomic(results_dir / ITEMS_JSON, _dump(item_rows(scores)))
    return WrittenResults(
        outcomes=outcomes_json,
        report=report_path,
        summary=summary_path,
        items=items_path,
        parquet=parquet,
    )


def read_outcome_rows(runs_dir: Path = DEFAULT_RUNS_SUBDIR) -> list[dict[str, Any]]:
    """The stored tidy table, for `make reproduce` to rebuild the report from."""
    path = runs_dir / OUTCOMES_JSON
    if not path.exists():
        raise FileNotFoundError(
            f"no stored outcomes at {path}; `bisect eval` writes them, and "
            "`make reproduce` rebuilds the report from them rather than re-running"
        )
    return json.loads(path.read_text(encoding="utf-8"))
