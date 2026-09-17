"""The tape + blob store and no-op limiter the demo suite records under.

Mirrors `tests/tau2_offline.py`'s harness, but lives outside `tests/`
because `demo/runner.py` and `demo/blame.py` are run as ordinary processes
(`python -m demo.runner`, inside a PR-check worktree), not under pytest.
"""

from __future__ import annotations

from pathlib import Path

from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

#: `route_tau2_llm` wants credentials even though the demo suite never
#: sends one anywhere -- the scripted `demo_completion` is the only thing
#: the router ever calls.
UNUSED_API_KEY = "unused-in-the-demo-suite"
UNUSED_API_BASE = "https://integrate.api.nvidia.com/v1"


class Store:
    """A tape + blob store rooted at one directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs = BlobStore(root)
        self.tape = TapeWriter(root)
        self.reader = TapeReader(root)


def ledger_for(root: Path) -> BudgetLedger:
    return BudgetLedger(root / "ledger.sqlite")


class NoLimiter:
    """A limiter that never sleeps: nothing here ever leaves the process."""

    requests_per_minute = 10_000

    def acquire_sync(self) -> None:
        return None


def no_limiter(_model: str) -> NoLimiter:
    return NoLimiter()
