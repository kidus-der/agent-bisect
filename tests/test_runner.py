"""Tests for agent_bisect.core.runner: the fork sequence
(restore -> apply -> run_rest), the forked run's manifest, and the two
end-of-replay checks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from agent_bisect.core.replay import DivergenceError, NoOpIntervention, TapeCursor
from agent_bisect.core.runner import (
    ForkSpec,
    check_replay_complete,
    check_same_outcome,
    fork_manifest,
    run_fork,
)
from agent_bisect.core.tape import Outcome, RunManifest, Step
from pydantic import ValidationError


class _RecordingDriver:
    """A `ForkDriver` that records the order it was driven in."""

    def __init__(self, outcome: Outcome | None = None) -> None:
        self.events: list[tuple[str, Any]] = []
        self._outcome = outcome or Outcome(run_id="fork-1", reward=1.0)

    def restore(self, fork_step: int) -> None:
        self.events.append(("restore", fork_step))

    def apply(self, intervention: Any) -> None:
        self.events.append(("apply", intervention.name))

    def run_rest(self, seed: int | None) -> Outcome:
        self.events.append(("run_rest", seed))
        return self._outcome


def _manifest(**overrides: Any) -> RunManifest:
    defaults: dict[str, Any] = dict(
        run_id="run-1",
        domain="airline",
        task_id="task-0",
        agent_model="deepseek-ai/deepseek-v4-flash-0731",
        user_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        params={"temperature": 0.0},
        seed=42,
        tau2_commit="2174a603f6d014ef94473ffa95957f6ce27100db",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    defaults.update(overrides)
    return RunManifest(**defaults)


def _step(step_idx: int) -> Step:
    return Step(
        run_id="run-1",
        step_idx=step_idx,
        actor="agent",
        state_before="a" * 64,
        state_after="b" * 64,
        state_hash="c" * 64,
    )


# ---- ForkSpec ----


def test_fork_spec_is_frozen():
    spec = ForkSpec(parent_run_id="run-1", run_id="fork-1", fork_step=3)

    with pytest.raises(ValidationError):
        spec.fork_step = 4  # pyright: ignore[reportAttributeAccessIssue]


def test_fork_spec_defaults_to_the_snapshot_prefix():
    """Snapshot is Bisect; rerun_live is the CAR-style baseline, opt in."""
    assert ForkSpec(parent_run_id="run-1", run_id="fork-1", fork_step=0).prefix_tools == "snapshot"


def test_fork_spec_rejects_an_unknown_prefix_mode():
    with pytest.raises(ValidationError):
        ForkSpec(
            parent_run_id="run-1",
            run_id="fork-1",
            fork_step=0,
            prefix_tools="guess",  # pyright: ignore[reportArgumentType]
        )


def test_fork_spec_rejects_a_negative_fork_step():
    with pytest.raises(ValidationError):
        ForkSpec(parent_run_id="run-1", run_id="fork-1", fork_step=-1)


# ---- run_fork ----


def test_run_fork_drives_restore_then_apply_then_run_rest():
    driver = _RecordingDriver()
    spec = ForkSpec(parent_run_id="run-1", run_id="fork-1", fork_step=3, seed=7)

    run_fork(driver, spec, NoOpIntervention())

    assert driver.events == [("restore", 3), ("apply", "noop"), ("run_rest", 7)]


def test_run_fork_returns_the_drivers_outcome():
    outcome = Outcome(run_id="fork-1", reward=0.0)
    driver = _RecordingDriver(outcome)

    result = run_fork(driver, ForkSpec(parent_run_id="run-1", run_id="fork-1", fork_step=1),
                      NoOpIntervention())

    assert result is outcome


# ---- fork_manifest ----


def test_fork_manifest_pins_the_parent_and_the_fork_step():
    parent = _manifest()

    forked = fork_manifest(parent, run_id="fork-1", fork_step=3, created_at=parent.created_at)

    assert forked.run_id == "fork-1"
    assert forked.parent_run_id == "run-1"
    assert forked.fork_step == 3


def test_fork_manifest_keeps_everything_the_parent_pinned():
    parent = _manifest()

    forked = fork_manifest(parent, run_id="fork-1", fork_step=3, created_at=parent.created_at)

    assert (forked.domain, forked.task_id, forked.agent_model, forked.user_model) == (
        parent.domain, parent.task_id, parent.agent_model, parent.user_model
    )
    assert forked.params == parent.params
    assert forked.tau2_commit == parent.tau2_commit


def test_fork_manifest_does_not_mutate_the_parent():
    parent = _manifest()

    fork_manifest(parent, run_id="fork-1", fork_step=3, created_at=parent.created_at)

    assert parent.parent_run_id is None
    assert parent.fork_step is None
    assert parent.run_id == "run-1"


def test_fork_manifest_can_override_the_seed():
    parent = _manifest(seed=42)

    forked = fork_manifest(
        parent, run_id="fork-1", fork_step=3, created_at=parent.created_at, seed=99
    )

    assert forked.seed == 99
    assert parent.seed == 42


def test_fork_manifest_of_a_fork_points_at_its_immediate_parent():
    parent = _manifest(run_id="fork-1", parent_run_id="run-1", fork_step=3)

    forked = fork_manifest(parent, run_id="fork-2", fork_step=5, created_at=parent.created_at)

    assert forked.parent_run_id == "fork-1"


# ---- end-of-replay checks ----


def test_check_replay_complete_passes_when_the_tape_is_spent():
    cursor = TapeCursor([_step(0)])
    cursor.take({"agent"})

    check_replay_complete(cursor)


def test_check_replay_complete_raises_when_steps_are_left_over():
    cursor = TapeCursor([_step(0), _step(1), _step(2)])
    cursor.take({"agent"})

    with pytest.raises(DivergenceError) as excinfo:
        check_replay_complete(cursor)

    assert excinfo.value.step_idx == 1
    assert "2" in excinfo.value.diff


def test_check_same_outcome_passes_on_an_identical_reward():
    check_same_outcome(Outcome(run_id="run-1", reward=1.0), Outcome(run_id="replay-1", reward=1.0))


def test_check_same_outcome_raises_on_a_different_reward():
    with pytest.raises(DivergenceError) as excinfo:
        check_same_outcome(
            Outcome(run_id="run-1", reward=1.0), Outcome(run_id="replay-1", reward=0.0)
        )

    assert "reward" in excinfo.value.diff


def test_check_same_outcome_raises_when_the_recording_has_no_outcome():
    with pytest.raises(DivergenceError) as excinfo:
        check_same_outcome(None, Outcome(run_id="replay-1", reward=1.0))

    assert "no recorded outcome" in excinfo.value.diff
