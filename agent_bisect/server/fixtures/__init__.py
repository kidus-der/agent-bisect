"""Deterministic seeded fixture dataset generator for the dashboard.

Run as `uv run python -m agent_bisect.server.fixtures --out data/fixtures
--seed 20260917`. Everything under here is fake data manufactured to make
the React dashboard usable before `bisect record`/`blame`/`eval` produce
real recordings -- every response built from it carries
`meta.simulated = true` (enforced in `agent_bisect.server.app`, not here).

`build_bundle(seed)` is the single entry point the writer and the tests
both call; it is pure (no filesystem I/O) so determinism can be checked by
building twice and comparing, without touching disk.
"""

from __future__ import annotations

from agent_bisect.server.fixtures.bundle import FixtureBundle, build_bundle

__all__ = ["FixtureBundle", "build_bundle"]
