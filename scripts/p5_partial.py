#!/usr/bin/env python
"""What the unfinished test split actually holds, item by item.

    uv run python scripts/p5_partial.py [--out data/results/p5_test_partial.json]

The test split did not complete (decision 0023), so it has no accuracy,
no gap and no recall — and the one thing that must not happen is for a
number to be computed from the part of it that did run. This writes the
inventory instead: per item, how many forks are on the tape and how many
of them carry an outcome. Every item's `verdict` is `null`, by
construction rather than by omission.

It is the committed, machine-readable counterpart of the table in
`docs/gates/P5.md`, so P8 can render the partial state without anyone
re-deriving it, and it regenerates offline from the tape index.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from agent_bisect.bench.manifest import DEFAULT_MANIFEST_PATH, load_frozen

DEFAULT_OUT = Path("data/results/p5_test_partial.json")
DEFAULT_INDEX = Path("runs/index.sqlite")
SPLIT = "test"

NOTE = (
    "The test split did not complete. These counts are inventory, not results: no "
    "accuracy, gap or recall is computed from them, and they are never pooled into a "
    "number. One item reached a verdict inside an incomplete pass, which by design "
    "wrote no results file. See docs/decisions/0023-p5-cutoff.md."
)


def fork_counts(
    run_ids: set[str], outcome_ids: set[str], parent: str
) -> tuple[int, int]:
    """Forks recorded for `parent`, and how many of them finished.

    A fork that died mid-run leaves a manifest behind with no outcome, so
    the two numbers differ by exactly the forks the outage killed.
    """
    forks = {run_id for run_id in run_ids if run_id.startswith(parent) and run_id != parent}
    return len(forks), len(forks & outcome_ids)


def build_rows(manifest_items: list[Any], index_path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(f"file:{index_path}?mode=ro", uri=True) as connection:
        run_ids = {row[0] for row in connection.execute("select run_id from runs")}
        outcome_ids = {row[0] for row in connection.execute("select run_id from outcomes")}
    rows = []
    for item in manifest_items:
        recorded, finished = fork_counts(run_ids, outcome_ids, item.run_id)
        rows.append(
            {
                "item_id": item.item_id,
                "run_id": item.run_id,
                "domain": item.domain,
                "fault_type": item.fault_type,
                "planted_step": item.planted_step,
                "forks_recorded": recorded,
                "forks_completed": finished,
                "verdict": None,
            }
        )
    return rows


def document(manifest_path: Path, index_path: Path) -> dict[str, Any]:
    manifest = load_frozen(manifest_path)
    items = manifest.split(SPLIT)  # type: ignore[arg-type]
    rows = build_rows(list(items), index_path)
    return {
        "split": SPLIT,
        "status": "incomplete",
        "note": NOTE,
        "manifest_digest": manifest.digest,
        "n_items": len(rows),
        "n_items_with_verdict": 0,
        "items": sorted(rows, key=lambda row: row["item_id"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory the unfinished test split.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    payload = document(args.manifest, args.index)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"{args.out}: {payload['n_items']} test items, none with a verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
