"""`TapeLLM(unsafe_positional=True)`: the CAR-style baseline's defining weakness.

The re-run-live baseline of `docs/brief/summary.md` §8 re-executes the
prefix's tools instead of restoring a snapshot. The moment a tool answers
differently, the next model request differs from the recording and the
request-hash guard — correctly — refuses to serve it. A baseline that
stopped there would not be the baseline; CAR-style tools keep going and
hand the model the recorded reply anyway. This mode exists to reproduce
that, loudly and only where it is asked for.
"""

from __future__ import annotations

import pytest
from agent_bisect.core.replay import DivergenceError, TapeCursor, TapeLLM
from agent_bisect.core.tape import Step, canonical_request_hash

REQUEST = {"model": "m", "messages": [{"role": "user", "content": "hello"}]}
OTHER_REQUEST = {"model": "m", "messages": [{"role": "user", "content": "different"}]}


def _step(step_idx: int = 0, *, request: dict) -> Step:
    return Step(
        run_id="r",
        step_idx=step_idx,
        actor="agent",
        request_hash=canonical_request_hash(dict(request)),
        request_ref="req",
        response_ref="resp",
        state_before="s",
        state_after="s",
        state_hash="h",
    )


def _load(ref: str):
    return {"ref": ref}


def test_the_guard_is_on_by_default():
    # Arrange
    tape = TapeLLM(TapeCursor([_step(request=REQUEST)]), _load)

    # Act / Assert
    with pytest.raises(DivergenceError):
        tape.serve(OTHER_REQUEST)


def test_a_matching_request_is_served_in_either_mode():
    # Arrange
    guarded = TapeLLM(TapeCursor([_step(request=REQUEST)]), _load)
    unguarded = TapeLLM(TapeCursor([_step(request=REQUEST)]), _load, unsafe_positional=True)

    # Act
    first, second = guarded.serve(REQUEST), unguarded.serve(REQUEST)

    # Assert
    assert first == second == {"ref": "resp"}


def test_a_mismatched_request_is_served_positionally_when_asked_for():
    # Arrange
    tape = TapeLLM(TapeCursor([_step(request=REQUEST)]), _load, unsafe_positional=True)

    # Act
    served = tape.serve(OTHER_REQUEST)

    # Assert
    assert served == {"ref": "resp"}
    assert tape.calls_served == 1


def test_positional_serving_still_counts_unguarded_calls():
    # Arrange
    tape = TapeLLM(TapeCursor([_step(request=REQUEST)]), _load, unsafe_positional=True)

    # Act
    tape.serve(OTHER_REQUEST)

    # Assert
    assert tape.unguarded_calls == 1, "the baseline's weakness must be measurable, not silent"


def test_a_matching_request_is_not_counted_as_unguarded():
    # Arrange
    tape = TapeLLM(TapeCursor([_step(request=REQUEST)]), _load, unsafe_positional=True)

    # Act
    tape.serve(REQUEST)

    # Assert
    assert tape.unguarded_calls == 0


def test_the_actor_check_survives_positional_mode():
    # Arrange: the tape has a tool step, the replay asks for an LLM one
    step = Step(
        run_id="r", step_idx=0, actor="tool", tool_name="t",
        state_before="s", state_after="s", state_hash="h",
    )
    tape = TapeLLM(TapeCursor([step]), _load, unsafe_positional=True)

    # Act / Assert
    with pytest.raises(DivergenceError):
        tape.serve(REQUEST)


def test_running_off_the_end_of_the_tape_still_raises_in_positional_mode():
    # Arrange
    tape = TapeLLM(TapeCursor([]), _load, unsafe_positional=True)

    # Act / Assert
    with pytest.raises(DivergenceError):
        tape.serve(REQUEST)


def test_a_step_with_no_recorded_response_still_raises_in_positional_mode():
    # Arrange
    step = Step(
        run_id="r", step_idx=0, actor="agent",
        request_hash=canonical_request_hash(dict(REQUEST)), request_ref="req",
        state_before="s", state_after="s", state_hash="h",
    )
    tape = TapeLLM(TapeCursor([step]), _load, unsafe_positional=True)

    # Act / Assert
    with pytest.raises(DivergenceError):
        tape.serve(OTHER_REQUEST)
