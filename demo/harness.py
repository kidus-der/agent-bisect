"""The tape + blob store and no-op limiter the demo suite records under.

Mirrors `tests/tau2_offline.py`'s harness, but lives outside `tests/`
because `demo/runner.py` and `demo/blame.py` are run as ordinary processes
(`python -m demo.runner`, inside a PR-check worktree), not under pytest.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

#: `route_tau2_llm` wants credentials even though the demo suite never
#: sends one anywhere -- the scripted `demo_completion` is the only thing
#: the router ever calls.
UNUSED_API_KEY = "unused-in-the-demo-suite"
UNUSED_API_BASE = "https://integrate.api.nvidia.com/v1"


def ensure_litellm_offline() -> None:
    """Stop litellm from fetching its model cost map over the network.

    litellm tries to refresh `model_prices_and_context_window.json` from
    GitHub on its own, regardless of which provider a call names --
    `demo_completion` never reaches litellm's network path at all, but
    litellm's *import-time* housekeeping still does, which is exactly the
    kind of network attempt rule 2 (`docs/brief/summary.md` §3: no test,
    and nothing this suite runs, ever touches the network) forbids. Setting
    `LITELLM_LOCAL_MODEL_COST_MAP` before litellm's own check runs makes it
    use its bundled local copy instead. `setdefault` never overrides a
    caller's own explicit choice of either value.
    """
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


ensure_litellm_offline()


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
