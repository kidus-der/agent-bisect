#!/usr/bin/env python3
"""How much do N re-runs of the same fork actually differ?

`docs/decisions/0017-p3-collection-policy.md` §5. A fork carries no
per-re-run seed — τ² puts the run seed into every model request, so
re-pinning it breaks the hash-checked prefix and injecting it into the
live suffix alone makes the forked recording unreplayable. The N draws
therefore differ **only** by provider non-determinism at temperature 0.

Every interval P5 reports rests on that variation being real. If the four
re-runs of a fork are the same run four times, a Wilson interval computed
from them is narrower than the truth, and the honest thing is to say so.

So this measures, from the journal and the tape, with no model calls:

- **stability spread** — how many base runs passed 4/4, 3/4, 2/4, 1/4,
  0/4 of their stability re-runs;
- **trajectory spread** — how often the re-runs of one fork group are
  *step-identical* to each other (the same sequence of actors and tool
  calls) rather than diverging, for the stability groups and for the
  faulted groups separately.

Read together: identical trajectories with identical outcomes means the
re-runs are one draw repeated; identical trajectories with *different*
outcomes would mean the variation is in the reward, not the agent.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.bench.journal import Journal  # noqa: E402
from agent_bisect.core.store import canonical_json_bytes  # noqa: E402
from agent_bisect.core.tape import TapeReader, UnknownRunError  # noqa: E402

DEFAULT_WORK_DIR = Path("runs/p3")
DEFAULT_RUNS_DIR = Path("runs")


@dataclass(frozen=True)
class GroupSpread:
    """One set of re-runs that were meant to be the same draw."""

    groups: int
    identical: int
    distinct_shapes: list[int]

    @property
    def identical_share(self) -> float:
        return self.identical / self.groups if self.groups else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "groups": self.groups,
            "identical": self.identical,
            "identical_share": round(self.identical_share, 4),
            "distinct_trajectories_per_group": self.distinct_shapes,
        }


def trajectory(reader: TapeReader, run_id: str) -> tuple | None:
    """The run's shape: what each step did, ignoring how it was worded.

    Actors and tool calls, not model text: two re-runs that reach the
    same tool calls in the same order took the same actions, which is
    what "the same run again" has to mean here.
    """
    try:
        steps = reader.get_steps(run_id)
    except UnknownRunError:
        return None
    if not steps:
        return None
    return tuple(
        (step.actor, step.tool_name or "", canonical_json_bytes(step.tool_args or {}).decode())
        for step in steps
    )


def spread_of(reader: TapeReader, groups: Sequence[Sequence[str]]) -> GroupSpread:
    """How many of these re-run groups are one trajectory repeated."""
    identical = 0
    shapes: list[int] = []
    counted = 0
    for run_ids in groups:
        found = [trajectory(reader, run_id) for run_id in run_ids]
        present = [shape for shape in found if shape is not None]
        if len(present) < 2:
            continue
        counted += 1
        distinct = len(set(present))
        shapes.append(distinct)
        identical += int(distinct == 1)
    return GroupSpread(groups=counted, identical=identical, distinct_shapes=shapes)


def stability_spread(journal: Journal) -> dict[str, Any]:
    """The distribution of per-task pass rates over the stability re-runs."""
    tally: dict[str, int] = {}
    records = journal.all("stability")
    for record in records:
        key = f"{int(record.get('passes', 0))}/{len(record.get('run_ids') or []) or 4}"
        tally[key] = tally.get(key, 0) + 1
    return {
        "base_runs": len(records),
        "passes_out_of_four": dict(sorted(tally.items(), reverse=True)),
        "stable": sum(1 for record in records if record.get("stable")),
    }


def stability_groups(journal: Journal) -> list[list[str]]:
    return [list(record.get("run_ids") or []) for record in journal.all("stability")]


def faulted_groups(journal: Journal) -> list[list[str]]:
    return [
        list(record.get("rerun_run_ids") or [])
        for record in journal.all("candidate")
        if record.get("rerun_run_ids")
    ]


def summary(work_dir: Path, runs_dir: Path) -> dict[str, Any]:
    """Everything the interim note and `docs/gates/P3.md` report."""
    journal = Journal(work_dir)
    reader = TapeReader(runs_dir)
    return {
        "stability": stability_spread(journal),
        "stability_trajectories": spread_of(reader, stability_groups(journal)).as_dict(),
        "faulted_trajectories": spread_of(reader, faulted_groups(journal)).as_dict(),
    }


def render(report: dict[str, Any]) -> str:
    stability = report["stability"]
    lines = [
        f"stability over {stability['base_runs']} base runs "
        f"({stability['stable']} stable): {stability['passes_out_of_four']}",
    ]
    for name, label in (
        ("stability_trajectories", "stability re-runs"),
        ("faulted_trajectories", "faulted re-runs"),
    ):
        spread = report[name]
        lines.append(
            f"{label}: {spread['identical']}/{spread['groups']} groups were one "
            f"trajectory repeated ({spread['identical_share']:.0%})"
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / DEFAULT_WORK_DIR)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / DEFAULT_RUNS_DIR)
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = summary(args.work_dir, args.runs_dir)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
