"""Tests for agent_bisect.adapters.tau2_snapshot: Tau2Snapshotter.

The integration tests below build a real airline (and, if it loads,
retail) tau2 Environment and script >= 12 real tool calls through
`Environment.make_tool_call` -- no LLM, no network, both domains are
plain-tau2 deterministic (fixed seed data, no clock/random dependency in
their WRITE tools; see `_get_new_reservation_id`/`_get_datetime` in
`tau2.domains.airline.tools.AirlineTools`). For every step k, restoring
`state_before[k]` into a *fresh* environment must reproduce that step's
recorded `state_hash` before the call, and re-issuing the exact same call
on the restored environment must reproduce the recorded `state_hash`
after it -- exercising this module's capture/restore/state_hash together,
the same way a replayer will.
"""

from __future__ import annotations

from typing import Any

import pytest
from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter, Tau2StateUnavailableError
from agent_bisect.adapters.tau2_snapshot_check import (
    AIRLINE_CALLS,
    RETAIL_CALLS,
    StepCapture,
    check_round_trip,
    run_scripted_sequence,
)
from pydantic import BaseModel

ensure_tau2_data_dir()


# ---- unit tests against a lightweight fake environment (no real tau2) ----


class _FakeDB(BaseModel):
    value: int
    items: dict[str, int] = {}


class _FakeToolkit:
    def __init__(self, db: Any) -> None:
        self.db = db


class _FakeEnvironment:
    def __init__(
        self,
        tools: _FakeToolkit | None = None,
        user_tools: _FakeToolkit | None = None,
        db_hash: str | None = "fake-hash",
    ) -> None:
        self.tools = tools
        self.user_tools = user_tools
        self._db_hash = db_hash
        self.sync_calls = 0

    def get_db_hash(self) -> str | None:
        return self._db_hash

    def sync_tools(self) -> None:
        self.sync_calls += 1


def test_capture_raises_when_tools_is_none():
    snapshotter = Tau2Snapshotter(_FakeEnvironment(tools=None))

    with pytest.raises(Tau2StateUnavailableError):
        snapshotter.capture()


def test_capture_raises_when_agent_db_is_none():
    snapshotter = Tau2Snapshotter(_FakeEnvironment(tools=_FakeToolkit(db=None)))

    with pytest.raises(Tau2StateUnavailableError):
        snapshotter.capture()


def test_capture_returns_agent_db_and_none_user_db_when_no_user_tools():
    env = _FakeEnvironment(tools=_FakeToolkit(db=_FakeDB(value=1)))
    snapshotter = Tau2Snapshotter(env)

    state = snapshotter.capture()

    assert state == {"agent_db": {"value": 1, "items": {}}, "user_db": None}


def test_capture_omits_user_db_when_it_is_the_same_instance_as_agent_db():
    shared_db = _FakeDB(value=1)
    env = _FakeEnvironment(tools=_FakeToolkit(db=shared_db), user_tools=_FakeToolkit(db=shared_db))
    snapshotter = Tau2Snapshotter(env)

    state = snapshotter.capture()

    assert state["user_db"] is None


def test_capture_includes_separate_user_db_when_distinct_instance():
    env = _FakeEnvironment(
        tools=_FakeToolkit(db=_FakeDB(value=1)),
        user_tools=_FakeToolkit(db=_FakeDB(value=2)),
    )
    snapshotter = Tau2Snapshotter(env)

    state = snapshotter.capture()

    assert state["agent_db"]["value"] == 1
    assert state["user_db"]["value"] == 2


def test_restore_raises_when_tools_is_none():
    snapshotter = Tau2Snapshotter(_FakeEnvironment(tools=None))

    with pytest.raises(Tau2StateUnavailableError):
        snapshotter.restore({"agent_db": {"value": 1}})


def test_restore_replaces_agent_db_with_a_new_instance():
    env = _FakeEnvironment(tools=_FakeToolkit(db=_FakeDB(value=1)))
    snapshotter = Tau2Snapshotter(env)

    snapshotter.restore({"agent_db": {"value": 42}, "user_db": None})

    assert env.tools is not None
    assert env.tools.db.value == 42
    assert env.sync_calls == 1


def test_restore_drops_keys_absent_from_the_captured_state():
    """The whole point of full-model replacement over a dict merge: keys
    added after capture (e.g. a booked reservation) must not survive a
    restore to a pre-addition state."""
    env = _FakeEnvironment(tools=_FakeToolkit(db=_FakeDB(value=1, items={"a": 1})))
    snapshotter = Tau2Snapshotter(env)
    state_before = snapshotter.capture()
    assert env.tools is not None

    env.tools.db.items["b"] = 2  # simulate a later mutation that adds a key
    assert env.tools.db.items == {"a": 1, "b": 2}

    snapshotter.restore(state_before)

    assert env.tools.db.items == {"a": 1}


def test_restore_reassigns_shared_user_db_when_not_separately_captured():
    env = _FakeEnvironment(
        tools=_FakeToolkit(db=_FakeDB(value=1)),
        user_tools=_FakeToolkit(db=_FakeDB(value=1)),
    )
    snapshotter = Tau2Snapshotter(env)

    snapshotter.restore({"agent_db": {"value": 5}, "user_db": None})

    assert env.tools is not None
    assert env.user_tools is not None
    assert env.user_tools.db is env.tools.db


def test_restore_raises_when_user_db_captured_but_current_user_tools_db_is_none():
    env = _FakeEnvironment(
        tools=_FakeToolkit(db=_FakeDB(value=1)),
        user_tools=_FakeToolkit(db=None),
    )
    snapshotter = Tau2Snapshotter(env)

    with pytest.raises(Tau2StateUnavailableError):
        snapshotter.restore({"agent_db": {"value": 5}, "user_db": {"value": 9}})


def test_restore_assigns_separate_user_db_when_captured_separately():
    env = _FakeEnvironment(
        tools=_FakeToolkit(db=_FakeDB(value=1)),
        user_tools=_FakeToolkit(db=_FakeDB(value=1)),
    )
    snapshotter = Tau2Snapshotter(env)

    snapshotter.restore({"agent_db": {"value": 5}, "user_db": {"value": 9}})

    assert env.tools is not None
    assert env.user_tools is not None
    assert env.tools.db.value == 5
    assert env.user_tools.db.value == 9
    assert env.user_tools.db is not env.tools.db


def test_state_hash_delegates_to_environment_get_db_hash():
    snapshotter = Tau2Snapshotter(_FakeEnvironment(db_hash="abc123"))

    assert snapshotter.state_hash() == "abc123"


def test_state_hash_raises_when_environment_reports_none():
    snapshotter = Tau2Snapshotter(_FakeEnvironment(db_hash=None))

    with pytest.raises(Tau2StateUnavailableError):
        snapshotter.state_hash()


# ---- integration: real tau2 airline/retail environments, no LLM ----


def test_airline_snapshot_round_trips_at_every_step():
    from tau2.domains.airline.environment import get_environment

    live_env = get_environment()
    steps = run_scripted_sequence(live_env, AIRLINE_CALLS)
    assert len(steps) >= 12

    result = check_round_trip("airline", steps, get_environment)

    assert result.all_reproduced, result.failures


def test_retail_snapshot_round_trips_at_every_step():
    retail = pytest.importorskip("tau2.domains.retail.environment")

    live_env = retail.get_environment()
    steps = run_scripted_sequence(live_env, RETAIL_CALLS)
    assert len(steps) >= 12

    result = check_round_trip("retail", steps, retail.get_environment)

    assert result.all_reproduced, result.failures


def test_check_round_trip_reports_a_failure_for_a_mismatched_step():
    from tau2.domains.airline.environment import get_environment

    live_env = get_environment()
    [real_step] = run_scripted_sequence(live_env, [("calculate", {"expression": "1 + 1"})])
    bad_step = StepCapture(
        tool_name=real_step.tool_name,
        kwargs=real_step.kwargs,
        state_before=real_step.state_before,
        hash_before=real_step.hash_before,
        hash_after="not-the-real-hash",
    )

    result = check_round_trip("airline", [bad_step], get_environment)

    assert result.all_reproduced is False
    assert result.reproduced == 0
    assert len(result.failures) == 1
    assert "calculate" in result.failures[0]
