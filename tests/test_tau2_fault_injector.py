"""The standing planted fault: one call that always lies, a world that doesn't.

`docs/decisions/0016-persistent-planted-fault.md`. What has to hold:
the matched call's *answer* is corrupted every time it runs, the database
is not, every other call is untouched, and the whole thing survives a
round trip through a run manifest so any later fork rebuilds the same
world.
"""

from __future__ import annotations

import json

import pytest
from agent_bisect.adapters.tau2_fault_injector import (
    MANIFEST_KEY,
    FaultSpec,
    fault_injected,
    injector_spec_from,
    restored_fault,
    with_injector,
)
from agent_bisect.adapters.tau2_flaky import FlakyConfig, flaky_world
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
from tests.inject_offline import PANIC_BOOKING
from tests.tau2_offline import quiet_tau2
from tests.test_tau2_flaky import environment_for, tool_call

quiet_tau2()

LOOKUP = FaultSpec(
    tool_name="get_user_details",
    tool_args={"user_id": "mia_li_3668"},
    content='{"user_id": "mia_li_3668", "membership": "gold"}',
    step_idx=2,
    fault_type="wrong_value",
)


def look_up(environment, user_id: str = "mia_li_3668"):
    return environment.get_response(tool_call("get_user_details", user_id=user_id))


# ---- matching ----


def test_the_matched_call_lies_every_single_time():
    environment = environment_for()

    with fault_injected(environment, LOOKUP) as injector:
        answers = [look_up(environment).content for _ in range(3)]

    assert answers == [LOOKUP.content] * 3
    assert injector.hits == 3


def test_a_call_with_different_arguments_is_untouched():
    environment = environment_for()

    with fault_injected(environment, LOOKUP) as injector:
        other = look_up(environment, user_id="omar_rossi_1241").content

    assert other != LOOKUP.content
    assert injector.hits == 0
    assert injector.executions == 1


def test_a_different_tool_is_untouched():
    environment = environment_for()

    with fault_injected(environment, LOOKUP):
        airports = environment.get_response(tool_call("list_all_airports")).content

    assert airports != LOOKUP.content


def test_the_fault_is_gone_once_the_world_is_left():
    environment = environment_for()

    with fault_injected(environment, LOOKUP):
        pass

    assert look_up(environment).content != LOOKUP.content


def test_matching_ignores_argument_order():
    spec = FaultSpec(tool_name="t", tool_args={"a": 1, "b": 2}, content="x")

    assert spec.matches("t", {"b": 2, "a": 1})
    assert not spec.matches("t", {"a": 1})
    assert not spec.matches("other", {"a": 1, "b": 2})


# ---- the world is not touched ----


def test_the_tool_still_runs_and_still_writes():
    """The fault is one of perception: the database moves exactly as it
    would have, and only the answer is corrupted."""
    booking = FaultSpec(
        tool_name="book_reservation",
        tool_args=dict(PANIC_BOOKING.arguments),
        content="Error: Booking failed",
        error=True,
    )
    clean, faulted = environment_for(), environment_for()

    clean.get_response(tool_call("book_reservation", **dict(PANIC_BOOKING.arguments)))
    with fault_injected(faulted, booking):
        message = faulted.get_response(
            tool_call("book_reservation", **dict(PANIC_BOOKING.arguments))
        )

    assert message.error is True
    assert message.content == "Error: Booking failed"
    assert Tau2Snapshotter(faulted).state_hash() == Tau2Snapshotter(clean).state_hash()


def test_an_injected_error_flag_is_carried_through():
    spec = FaultSpec(tool_name="get_user_details", tool_args={"user_id": "mia_li_3668"},
                     content="Error: User not found", error=True)
    environment = environment_for()

    with fault_injected(environment, spec):
        message = look_up(environment)

    assert message.error is True


# ---- travelling in a manifest ----


def test_a_fault_round_trips_through_a_manifest():
    params = with_injector({"temperature": 0.0}, LOOKUP)

    restored = injector_spec_from(params)

    assert restored == LOOKUP
    assert params["temperature"] == 0.0
    assert params[MANIFEST_KEY]["tool_name"] == "get_user_details"
    assert json.loads(json.dumps(params)) == params


def test_an_ordinary_run_has_no_fault_to_restore():
    assert injector_spec_from({"temperature": 0.0}) is None
    assert injector_spec_from(None) is None


def test_restoring_a_fault_from_a_manifest_reinstalls_it():
    environment = environment_for()

    with restored_fault(environment, with_injector({}, LOOKUP)) as injector:
        answer = look_up(environment).content

    assert answer == LOOKUP.content
    assert injector is not None and injector.hits == 1


def test_restoring_nothing_is_a_no_op():
    environment = environment_for()

    with restored_fault(environment, {}) as injector:
        answer = look_up(environment).content

    assert injector is None
    assert answer != LOOKUP.content


def test_the_fault_hash_identifies_the_fault():
    other = FaultSpec(**{**LOOKUP.as_dict(), "content": "something else"})

    assert LOOKUP.fault_hash == FaultSpec.from_dict(LOOKUP.as_dict()).fault_hash
    assert LOOKUP.fault_hash != other.fault_hash


def test_a_spec_can_be_built_from_a_mutated_payload():
    spec = FaultSpec.from_mutation(
        tool_name="get_user_details",
        tool_args={"user_id": "mia_li_3668"},
        mutated={"content": '{"membership": "silver"}', "error": False, "id": "c1"},
        step_idx=4,
        fault_type="wrong_value",
    )

    assert spec.content == '{"membership": "silver"}'
    assert spec.step_idx == 4
    assert spec.fault_type == "wrong_value"


# ---- composing with the flaky world ----


def test_the_fault_still_stands_in_a_flaky_world():
    """The two layers are independent: the flaky world decides whether the
    call runs at all, and the fault decides what it says when it does."""
    environment = environment_for()

    # Order matters: the world goes on first, the faulty tool on top of it.
    with (
        flaky_world(environment, FlakyConfig(seed=4, p_error=0.0)),
        fault_injected(environment, LOOKUP) as injector,
    ):
        answer = look_up(environment).content

    assert answer == LOOKUP.content
    assert injector.hits == 1


def test_a_transient_failure_is_left_alone_because_there_is_no_answer_to_corrupt():
    environment = environment_for()

    with (
        flaky_world(environment, FlakyConfig(seed=4, p_error=1.0)),
        fault_injected(environment, LOOKUP) as injector,
    ):
        message = look_up(environment)

    assert message.error is True
    assert message.content != LOOKUP.content
    assert injector.hits == 0


@pytest.mark.parametrize("error", [True, False])
def test_every_spec_serialises_to_plain_json(error):
    spec = FaultSpec(tool_name="t", tool_args={"a": [1, {"b": 2}]}, content="x", error=error)

    assert FaultSpec.from_dict(json.loads(json.dumps(spec.as_dict()))) == spec
