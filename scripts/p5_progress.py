#!/usr/bin/env python
"""How far a P5 split has actually got, counted against the ids it asks for.

    uv run python scripts/p5_progress.py [--split dev] [--seed 20260917]

Counting rows on the tape overstates progress badly: forks recorded under
a superseded id scheme, and under the `-a<n>` ids a retry takes, all match
a naive `LIKE` and none of them are necessarily the draw the estimator is
waiting for. This asks the opposite question — for each draw the current
code would request, is there a recorded outcome? — which is the only
count that predicts when an item finishes.

Offline and read-only.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from agent_bisect.attribution.estimate import DEFAULT_BATCH, DEFAULT_MAX_N, _derive_seed
from agent_bisect.attribution.search import BlameConfig, rerun_id
from agent_bisect.bench.manifest import DEFAULT_MANIFEST_PATH, load_frozen

#: The suffixes a draw's outcome can end up under; see `Tau2ForkExecutor`.
SUFFIXES = ("", "-a1", "-a2", "-r1", "-a1-r1")


def satisfied(have: set[str], base: str) -> bool:
    return any(base + suffix in have for suffix in SUFFIXES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P5 progress by requested draw.")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--seed", type=int, default=20260917)
    args = parser.parse_args(argv)

    con = sqlite3.connect(f"file:{args.runs_dir / 'index.sqlite'}?mode=ro", uri=True)
    have = {row[0] for row in con.execute("SELECT run_id FROM outcomes")}
    variant = BlameConfig().fork_variant
    frozen = load_frozen(args.manifest)

    total_done = total_needed = 0
    for item in frozen.split(args.split):  # type: ignore[arg-type]
        started = sorted(
            {
                int(row[0][len(item.run_id) + 2 :].split("-")[0])
                for row in con.execute(
                    "SELECT run_id FROM runs WHERE run_id LIKE ?", (item.run_id + "-t%",)
                )
                if row[0][len(item.run_id) + 1] == "t"
            }
        )
        parts = []
        for step in started:
            done = sum(
                satisfied(
                    have,
                    rerun_id(
                        item.run_id, arm="treated", step=step,
                        seed=_derive_seed(args.seed, step, "treated", offset),
                        draw=draw, variant=variant,
                    ),
                )
                for offset in range(0, DEFAULT_MAX_N, DEFAULT_BATCH)
                for draw in range(DEFAULT_BATCH)
            )
            parts.append(f"t{step}:{done}/{DEFAULT_MAX_N}")
            total_done += done
        # Three suspects at m = 3; steps not yet started count as 0.
        total_needed += 3 * DEFAULT_MAX_N
        print(f"{item.item_id[:30]:30} " + "  ".join(parts or ["(no treated forks yet)"]))
    print(f"\ntreated draws satisfied: {total_done}/{total_needed} "
          f"({100 * total_done / max(total_needed, 1):.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
