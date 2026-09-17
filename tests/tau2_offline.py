"""Shared harness for the offline record/replay tests.

Every test here drives tau2's real orchestrator, environment and evaluator
over a real domain with sockets blocked; only the model is scripted.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agent_bisect.adapters.tau2_fake_llm import ScriptedLLM
from agent_bisect.adapters.tau2_scenarios import AGENT_MODEL, USER_MODEL, Scenario
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

#: `route_tau2_llm` wants credentials even when nothing is ever sent; the
#: scripted model is the only thing the router ever calls.
UNUSED_API_KEY = "unused-in-offline-tests"
UNUSED_API_BASE = "https://integrate.api.nvidia.com/v1"


def reward_of(result: Any) -> float:
    """`result.outcome.reward`, with the "there is an outcome" check the
    type checker needs stated once rather than at every call site."""
    assert result.outcome is not None, "the run has no outcome to read a reward from"
    return result.outcome.reward


def ref(digest: str | None) -> str:
    """A blob ref that must be present. Every recorded step of the kind
    being read has one; a missing one is a bug, not a branch."""
    assert digest is not None, "the step has no blob reference"
    return digest


def quiet_tau2() -> None:
    """Silence tau2's own loguru sink for the duration of a test module.

    tau2 logs an ERROR per call for every model litellm cannot price, and
    the scripted models are exactly that. Left on, a genuine failure is
    buried in hundreds of lines about `completion_cost`.
    """
    from loguru import logger

    logger.remove()


class _NoLimiter:
    """A limiter that never sleeps: pacing is irrelevant with no network."""

    requests_per_minute = 10_000

    def acquire_sync(self) -> None:
        return None


def no_limiter(_model: str) -> _NoLimiter:
    return _NoLimiter()


def spec_for(scenario: Scenario, **overrides: Any):
    from agent_bisect.adapters.tau2 import RunSpec

    defaults: dict[str, Any] = dict(
        domain=scenario.domain,
        task_id=scenario.task_id,
        agent_model=AGENT_MODEL,
        user_model=USER_MODEL,
        seed=42,
    )
    defaults.update(overrides)
    return RunSpec(**defaults)


class Store:
    """A tape + blob store rooted at one directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs = BlobStore(root)
        self.tape = TapeWriter(root)
        self.reader = TapeReader(root)


def ledger_for(root: Path) -> BudgetLedger:
    return BudgetLedger(root / "ledger.sqlite")


@contextmanager
def scripted_session(
    scenario: Scenario, root: Path, *, phase: str = "test"
) -> Iterator[ScriptedLLM]:
    """A `recording_session` whose model is `scenario`'s script."""
    from agent_bisect.adapters.tau2 import recording_session

    llm = ScriptedLLM(scenario.scripts)
    with recording_session(
        ledger=ledger_for(root),
        phase=phase,
        completion_fn=llm.completion,
        api_key=UNUSED_API_KEY,
        api_base=UNUSED_API_BASE,
        limiter_for=no_limiter,
    ):
        yield llm


def record(scenario: Scenario, store: Store, *, run_id: str | None = None, **spec_overrides: Any):
    """Record one scripted scenario and return `(RecordedRun, ScriptedLLM)`."""
    from agent_bisect.adapters.tau2 import record_run

    run_id = run_id or f"{scenario.name}-1"
    with scripted_session(scenario, store.root) as llm:
        recorded = record_run(
            spec_for(scenario, **spec_overrides),
            run_id=run_id,
            store=store.blobs,
            tape=store.tape,
        )
    return recorded, llm
