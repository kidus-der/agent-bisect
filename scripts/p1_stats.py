#!/usr/bin/env python3
"""What the P1 recordings look like — the numbers P3's planning needs.

Reads the tape only; runs nothing and spends nothing. Prints JSON, and
writes `<runs>/p1/stats.json` so `docs/gates/P1.md` can cite a file rather
than a transcript.

    uv run python scripts/p1_stats.py --runs-dir runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.core.run_stats import summarise_runs  # noqa: E402
from agent_bisect.core.store import BlobStore  # noqa: E402
from agent_bisect.core.tape import TapeReader  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    args = parser.parse_args(argv)

    stats = summarise_runs(TapeReader(args.runs_dir), BlobStore(args.runs_dir), args.runs_dir)
    payload = json.dumps(stats.model_dump(mode="json"), indent=2, sort_keys=True)
    out = args.runs_dir / "p1" / "stats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload)
    print(payload)
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
