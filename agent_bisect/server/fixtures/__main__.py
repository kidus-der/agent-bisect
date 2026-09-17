"""`uv run python -m agent_bisect.server.fixtures --out data/fixtures --seed 20260917`."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_bisect.server.fixtures.bundle import build_bundle
from agent_bisect.server.fixtures.writer import write_bundle

DEFAULT_SEED = 20260917
DEFAULT_OUT = "data/fixtures"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output directory for fixture JSON.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Master seed.")
    args = parser.parse_args()

    bundle = build_bundle(args.seed)
    write_bundle(bundle, Path(args.out))
    print(f"wrote {len(bundle.plans)} runs to {args.out} (seed={args.seed})")


if __name__ == "__main__":
    main()
