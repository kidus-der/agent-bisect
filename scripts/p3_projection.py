#!/usr/bin/env python3
"""How much API time the P3 collection will cost, before spending any of it.

`docs/decisions/0001-preregistration.md` makes the target conditional:

  "P3: >= 120 labelled failures. Fallback floor: 60, used **only if** P0's
   measured throughput projects the 120-target collection past 10 h of API
   time. Which one applied is recorded."

This script is that projection. It is arithmetic over measured inputs, not
a simulation, and every input is either read off `runs/` or passed in, so
the result can be recomputed and argued with.

## The cost model

Per base task, with `C` model calls in a full run and `A` candidate
attempts per position bucket:

- **record** the base run: `C` calls, always;
- **stability**: four re-runs, but only if the base run passed. A
  stability re-run is a fork at step 0, so it replays nothing and costs a
  full `C`: `4C`;
- **candidates**: `3A` attempts, each `N = 4` faulted forks, but only if
  the run was stable. A fork at step k replays the prefix from tape for
  free and samples only the suffix, so an attempt in the early / middle /
  late bucket costs about `4 x {5/6, 1/2, 1/6} x C` — together `6AC`.

So a task that passes and is stable costs `C(5 + 6A)`, and one that fails
its base run costs only `C`.

Items come out of the stable runs: a bucket yields an item if any of its
`A` attempts flips the run, so a stable run yields about
`3 x (1 - (1 - keep)^A)` items, capped at the pre-registered three.

The keep rate is the one number nobody can know before collecting, so it
is not guessed: the table is reported at 20%, 35% and 50%.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

#: P0's measured figures (`docs/gates/P0.md`), used when `runs/` has no
#: recordings to read instead.
DEFAULT_CALLS_PER_RUN = 21.4
DEFAULT_CALLS_PER_HOUR = 1362.0
#: Fraction of a run's calls that come *after* a fork in each bucket.
SUFFIX_FRACTIONS = (5 / 6, 1 / 2, 1 / 6)
#: Pre-registered.
RERUNS = 4
STABILITY_RERUNS = 4
MAX_KEPT_PER_RUN = 3
TARGET_ITEMS = 120
FALLBACK_FLOOR = 60
#: The rule that decides between them.
HOURS_BUDGET = 10.0
KEEP_RATES = (0.20, 0.35, 0.50)
#: tau2's vendored task pool: 50 airline + 114 retail.
TASK_POOL = 164


@dataclass(frozen=True)
class Inputs:
    """Everything the projection multiplies together."""

    calls_per_run: float
    calls_per_hour: float
    pass_rate: float
    stable_rate: float
    attempts_per_bucket: int
    target: int
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls_per_run": round(self.calls_per_run, 2),
            "calls_per_hour": round(self.calls_per_hour, 1),
            "base_pass_rate": self.pass_rate,
            "stable_given_pass": self.stable_rate,
            "attempts_per_bucket": self.attempts_per_bucket,
            "target_items": self.target,
            "calls_per_run_source": self.source,
        }


@dataclass(frozen=True)
class Projection:
    """One row of the table: what this keep rate would cost."""

    keep_rate: float
    items_per_stable_run: float
    tasks_needed: float
    calls: float
    hours: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "keep_rate": self.keep_rate,
            "items_per_stable_run": round(self.items_per_stable_run, 2),
            "tasks_needed": round(self.tasks_needed, 1),
            "calls": round(self.calls),
            "hours": round(self.hours, 2),
        }


def calls_per_round(calls_per_run: float, reruns: int = RERUNS) -> float:
    """One attempt in *each* position bucket: `N x (5/6 + 1/2 + 1/6) x C`.

    A round, not a single attempt, because the pipeline visits the three
    buckets round-robin and an early fork costs far more than a late one.
    """
    return reruns * calls_per_run * sum(SUFFIX_FRACTIONS)


def items_per_stable_run(keep_rate: float, attempts: int) -> float:
    """Three buckets, each yielding an item if any of its attempts flips."""
    per_bucket = 1 - (1 - keep_rate) ** attempts
    return min(MAX_KEPT_PER_RUN, len(SUFFIX_FRACTIONS) * per_bucket)


def calls_per_task(inputs: Inputs) -> float:
    """Expected cost of putting one task through the funnel."""
    record = inputs.calls_per_run
    stability = inputs.pass_rate * STABILITY_RERUNS * inputs.calls_per_run
    candidates = (
        inputs.pass_rate
        * inputs.stable_rate
        * inputs.attempts_per_bucket
        * calls_per_round(inputs.calls_per_run)
    )
    return record + stability + candidates


def project(inputs: Inputs, keep_rate: float) -> Projection:
    yielded = items_per_stable_run(keep_rate, inputs.attempts_per_bucket)
    per_task = inputs.pass_rate * inputs.stable_rate * yielded
    tasks = inputs.target / per_task if per_task > 0 else float("inf")
    calls = tasks * calls_per_task(inputs)
    return Projection(
        keep_rate=keep_rate,
        items_per_stable_run=yielded,
        tasks_needed=tasks,
        calls=calls,
        hours=calls / inputs.calls_per_hour if inputs.calls_per_hour > 0 else float("inf"),
    )


# ---- measured inputs --------------------------------------------------------


def measure_calls_per_run(runs_dir: Path) -> tuple[float, str]:
    """Model calls per recorded run, read off the tape when there is one.

    Counts LLM steps (agent, user, evaluator) of runs that are recordings
    rather than forks, which is exactly what one full run costs.
    """
    index = runs_dir / "index.sqlite"
    if not index.exists():
        return DEFAULT_CALLS_PER_RUN, f"P0 measurement (no tape at {index})"
    connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT s.run_id, COUNT(*) FROM steps s JOIN runs r ON r.run_id = s.run_id "
            "WHERE json_extract(r.manifest_json, '$.parent_run_id') IS NULL "
            "AND json_extract(s.step_json, '$.actor') != 'tool' GROUP BY s.run_id"
        ).fetchall()
    except sqlite3.Error:
        return DEFAULT_CALLS_PER_RUN, "P0 measurement (tape unreadable)"
    finally:
        connection.close()
    if not rows:
        return DEFAULT_CALLS_PER_RUN, "P0 measurement (no recordings on the tape yet)"
    counts = [int(count) for _run_id, count in rows]
    return sum(counts) / len(counts), f"{len(counts)} recordings on the tape at {runs_dir}"


# ---- reporting --------------------------------------------------------------


def verdict(projections: list[Projection], budget: float, target: int) -> dict[str, Any]:
    """Whether the pre-registered throughput rule triggers the 60 floor.

    The rule is about the **120** target, so it is only answered when that
    is what was projected; projecting any other number reports the hours
    and says the rule does not apply to it.
    """
    worst = max(projection.hours for projection in projections)
    best = min(projection.hours for projection in projections)
    applies = target == TARGET_ITEMS
    triggered = applies and best > budget
    return {
        "projected_for": target,
        "hours_budget": budget,
        "hours_best_case": round(best, 2),
        "hours_worst_case": round(worst, 2),
        "rule_applies": applies,
        "floor_triggered": triggered,
        "target": (FALLBACK_FLOOR if triggered else TARGET_ITEMS) if applies else target,
        "rule": (
            f"the {TARGET_ITEMS} target stands unless projecting it puts it past "
            f"{budget} h of API time at every keep rate considered"
        ),
    }


def render(inputs: Inputs, projections: list[Projection], decision: dict[str, Any]) -> str:
    lines = [
        f"P3 cost projection — target {inputs.target} labelled failures",
        "",
        "inputs:",
        *(f"  {key}: {value}" for key, value in inputs.as_dict().items()),
        "",
        f"  {'keep':>6}  {'items/run':>9}  {'tasks':>7}  {'calls':>8}  {'hours':>6}",
    ]
    for projection in projections:
        lines.append(
            f"  {projection.keep_rate:>6.0%}  {projection.items_per_stable_run:>9.2f}  "
            f"{projection.tasks_needed:>7.0f}  {projection.calls:>8.0f}  {projection.hours:>6.2f}"
        )
    lines += [
        "",
        f"  task pool: {TASK_POOL} (50 airline + 114 retail); a projection above it needs "
        "more trials per task or more attempts per bucket",
        "",
        f"verdict: {_verdict_word(decision)} — "
        f"{decision['hours_best_case']}–{decision['hours_worst_case']} h for "
        f"{decision['projected_for']} items against a {decision['hours_budget']} h budget; "
        f"collect {decision['target']}",
    ]
    return "\n".join(lines)


def _verdict_word(decision: dict[str, Any]) -> str:
    if not decision["rule_applies"]:
        return f"the {TARGET_ITEMS}/{FALLBACK_FLOOR} rule does not apply to this target"
    return "FLOOR TRIGGERED" if decision["floor_triggered"] else "the 120 target stands"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--calls-per-run", type=float, default=None,
                        help="Override the measured calls per full run.")
    parser.add_argument("--calls-per-hour", type=float, default=DEFAULT_CALLS_PER_HOUR)
    parser.add_argument("--pass-rate", type=float, default=0.60,
                        help="P0's measured airline pass rate for the chosen agent.")
    parser.add_argument("--stable-rate", type=float, default=0.70,
                        help="Share of passing runs that clear the 0.75 stability bar.")
    parser.add_argument("--attempts-per-bucket", type=int, default=2)
    parser.add_argument("--target", type=int, default=TARGET_ITEMS)
    parser.add_argument("--hours-budget", type=float, default=HOURS_BUDGET)
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    measured, source = measure_calls_per_run(args.runs_dir)
    inputs = Inputs(
        calls_per_run=args.calls_per_run if args.calls_per_run else measured,
        calls_per_hour=args.calls_per_hour,
        pass_rate=args.pass_rate,
        stable_rate=args.stable_rate,
        attempts_per_bucket=args.attempts_per_bucket,
        target=args.target,
        source="given on the command line" if args.calls_per_run else source,
    )
    projections = [project(inputs, keep_rate) for keep_rate in KEEP_RATES]
    decision = verdict(projections, args.hours_budget, args.target)
    if args.json_output:
        print(json.dumps(
            {"inputs": inputs.as_dict(),
             "projections": [projection.as_dict() for projection in projections],
             "verdict": decision},
            indent=2, sort_keys=True,
        ))
    else:
        print(render(inputs, projections, decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
