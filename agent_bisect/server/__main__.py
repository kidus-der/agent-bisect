"""`python -m agent_bisect.server --fixture --port 8484`."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_bisect.server.fixture_repository import DEFAULT_FIXTURE_SEED
from agent_bisect.server.runserver import DEFAULT_HOST, DEFAULT_PORT, UnsafeHostError, run_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None, help=f"default: {DEFAULT_HOST} (loopback)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--fixture", action="store_true", help="serve the seeded fixture dataset")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="real mode only")
    parser.add_argument("--seed", type=int, default=DEFAULT_FIXTURE_SEED, help="fixture mode only")
    args = parser.parse_args()

    explicit_host = args.host is not None
    host = args.host or DEFAULT_HOST
    data_source = "fixture" if args.fixture else "real"

    try:
        run_server(
            host=host,
            port=args.port,
            data_source=data_source,
            explicit_host=explicit_host,
            fixture_seed=args.seed,
            runs_dir=args.runs_dir,
        )
    except UnsafeHostError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
