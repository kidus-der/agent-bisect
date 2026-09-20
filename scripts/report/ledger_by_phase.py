#!/usr/bin/env python3
"""Read-only query of the call ledger, grouped by phase and model.

    uv run python scripts/report/ledger_by_phase.py

Opens `runs/ledger.sqlite` with `mode=ro` (a SQLite URI, refuses to write)
and writes `data/results/ledger_by_phase.json`. This is the only script in
`scripts/report/` that touches the ledger; the report itself
(`scripts/report/render.py`) reads the committed JSON this writes, never the
database directly, so `make reproduce` stays a read of committed inputs
rather than a live query. Regenerate only when the ledger has moved and a
committing agent wants the report to reflect it.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO_ROOT / "runs" / "ledger.sqlite"
DEFAULT_OUT = REPO_ROOT / "data" / "results" / "ledger_by_phase.json"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def query_ledger(path: Path) -> dict[str, Any]:
    """Calls by phase, and by (phase, model), read-only."""
    con = _connect_readonly(path)
    try:
        cur = con.cursor()
        by_phase: dict[str, int] = defaultdict(int)
        by_phase_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        by_phase_status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        cur.execute("SELECT phase, model, status FROM calls")
        total = 0
        for phase, model, status in cur.fetchall():
            by_phase[phase] += 1
            by_phase_model[phase][model] += 1
            by_phase_status[phase][status] += 1
            total += 1
    finally:
        con.close()
    return {
        "total_calls": total,
        "by_phase": dict(sorted(by_phase.items())),
        "by_phase_and_model": {
            phase: dict(sorted(models.items())) for phase, models in sorted(by_phase_model.items())
        },
        "by_phase_and_status": {
            phase: dict(sorted(statuses.items()))
            for phase, statuses in sorted(by_phase_status.items())
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.ledger.exists():
        sys.stderr.write(f"no ledger at {args.ledger}\n")
        return 1

    result = query_ledger(args.ledger)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.out} ({result['total_calls']} calls)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
