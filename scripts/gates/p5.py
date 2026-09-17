#!/usr/bin/env python
"""P5 gate: Bisect against the baselines, on the frozen test split.

    uv run python scripts/gates/p5.py [--summary data/results/p5_summary.json]

Zero network calls: it reads the committed summary that `bisect eval` wrote and
checks it. Re-running the gate never re-runs the evaluation, which is what lets
`make reproduce` check the same numbers offline.

Gate, pre-registered in `docs/decisions/0001-preregistration.md` and not
restated in any tunable form here -- the thresholds below are the only copy and
this script never writes them anywhere:

1. **step accuracy** — Bisect >= best judge + 15 points on the TEST split, and
2. **the gap's interval** — the 95% paired bootstrap CI of that gap is entirely
   above 0, and
3. **the flaky world** — the no-snapshot baseline is measurably worse than
   Bisect, i.e. the 95% CI of the difference is entirely above 0.

Each criterion prints PASS or FAIL with the numbers that decided it. A missing
input is a FAIL with a reason, never a skip: a gate that quietly passes because
it could not find its data is worse than no gate. The exit code is 0 only if
every criterion passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SUMMARY = Path("data/results/p5_summary.json")

#: The pre-registered bar, in accuracy points.
REQUIRED_POINTS = 15.0
#: The split the gate is defined on. Dev numbers never gate anything.
GATED_SPLIT = "test"


@dataclass(frozen=True, slots=True)
class Criterion:
    """One gate criterion and the numbers that decided it."""

    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


def _accuracy_of(summary: dict[str, Any], method: str) -> float | None:
    for row in summary.get("methods") or ():
        if row.get("method") == method:
            return float(row["accuracy"]["value"])
    return None


def check_split(summary: dict[str, Any]) -> Criterion:
    """The gate is defined on the test split; anything else is not it."""
    split = (summary.get("config") or {}).get("split")
    return Criterion(
        name="split",
        passed=split == GATED_SPLIT,
        detail=(
            f"summary is for split {split!r}, the gate is defined on {GATED_SPLIT!r}"
            if split != GATED_SPLIT
            else f"{GATED_SPLIT} split, {(summary.get('config') or {}).get('n_items')} items"
        ),
    )


def check_gap_points(summary: dict[str, Any]) -> Criterion:
    """Criterion 1: Bisect beats the best judge by at least 15 points."""
    gap = summary.get("gap")
    if not gap:
        return Criterion("accuracy gap", False, "the summary carries no gap")
    bisect = _accuracy_of(summary, "bisect")
    comparator = gap.get("comparator")
    judge = _accuracy_of(summary, comparator) if comparator else None
    points = float(gap["value"]) * 100.0
    detail = (
        f"bisect {bisect:.3f} vs {comparator} {judge:.3f} = {points:+.1f} points "
        f"(need >= {REQUIRED_POINTS:.0f})"
        if bisect is not None and judge is not None
        else f"{points:+.1f} points (need >= {REQUIRED_POINTS:.0f})"
    )
    return Criterion("accuracy gap", points >= REQUIRED_POINTS, detail)


def check_gap_interval(summary: dict[str, Any]) -> Criterion:
    """Criterion 2: the bootstrap interval of the gap excludes 0 from above."""
    gap = summary.get("gap")
    if not gap:
        return Criterion("gap interval", False, "the summary carries no gap")
    low, high = float(gap["ci_low"]), float(gap["ci_high"])
    return Criterion(
        name="gap interval",
        passed=low > 0.0,
        detail=(
            f"95% CI [{low:+.3f}, {high:+.3f}] from {gap.get('resamples')} resamples "
            "(need the whole interval above 0)"
        ),
    )


def check_flaky(summary: dict[str, Any]) -> Criterion:
    """Criterion 3: without snapshots the flaky world is measurably worse."""
    ablation = summary.get("flaky_ablation")
    if not ablation:
        return Criterion(
            "flaky ablation",
            False,
            "no flaky-world comparison in the summary; the ablation was not run",
        )
    difference = ablation["difference"]
    low, high = float(difference["ci_low"]), float(difference["ci_high"])
    arms = {arm["name"]: arm["accuracy"]["value"] for arm in ablation["arms"]}
    return Criterion(
        name="flaky ablation",
        passed=low > 0.0,
        detail=(
            f"snapshot {arms.get('snapshot', float('nan')):.3f} vs no_snapshot "
            f"{arms.get('no_snapshot', float('nan')):.3f}, difference 95% CI "
            f"[{low:+.3f}, {high:+.3f}] (need the whole interval above 0)"
        ),
    )


def run_gate(summary: dict[str, Any]) -> list[Criterion]:
    return [
        check_split(summary),
        check_gap_points(summary),
        check_gap_interval(summary),
        check_flaky(summary),
    ]


def load_summary(path: Path) -> dict[str, Any] | str:
    """The summary document, or a one-line reason it could not be read."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"no summary at {path}; run `bisect eval --split test` first"
    except ValueError as exc:
        return f"{path} is not readable JSON: {exc}"


def format_report(criteria: list[Criterion]) -> str:
    lines = ["P5 gate — Bisect vs baselines on the frozen test split", ""]
    lines.extend(criterion.line() for criterion in criteria)
    lines.append("")
    lines.append("GATE PASS" if all(c.passed for c in criteria) else "GATE FAIL")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the P5 gate.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args(argv)

    summary = load_summary(args.summary)
    if isinstance(summary, str):
        sys.stdout.write(
            format_report([Criterion("summary", False, summary)]) + "\n"
        )
        return 1

    criteria = run_gate(summary)
    sys.stdout.write(format_report(criteria) + "\n")
    return 0 if all(criterion.passed for criterion in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
