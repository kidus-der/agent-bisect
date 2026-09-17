"""The four planted-fault mutators: deterministic, seeded, LLM-free.

A planted fault has to be *believable* (a wrong value looks like a value
of the same kind), *consequential* (it lands on something the agent is
likely to use) and *auditable* (every mutation says exactly what it
changed). These tests pin all three, plus the property that matters most
for a labelled dataset: nothing outside the named path moves.
"""

from __future__ import annotations

import json

import pytest
from agent_bisect.bench.faults import (
    FAULT_TYPES,
    FaultContext,
    Mutation,
    NoFaultPossibleError,
    plant,
)

RESERVATION = {
    "reservation_id": "HATHAT",
    "user_id": "mia_li_3668",
    "status": "confirmed",
    "created_at": "2024-05-15T15:00:00",
    "total_baggages": 2,
    "nonfree_baggages": 1,
    "flights": [{"flight_number": "HAT001", "date": "2024-05-16", "price": 122}],
}


def payload(content: object = None, **fields) -> dict:
    body = RESERVATION if content is None else content
    return {
        "id": "call-1",
        "role": "tool",
        "requestor": "assistant",
        "content": body if isinstance(body, str) else json.dumps(body),
        "error": False,
        **fields,
    }


def content_of(result) -> object:
    return json.loads(result.payload["content"])


def restored(mutated: object, mutation: Mutation, original: object) -> object:
    """`mutated` with the mutation's own path put back as it was."""
    if not mutation.path:
        return original
    node = mutated
    for key in mutation.path[:-1]:
        node = node[key]  # pyright: ignore[reportIndexIssue]
    last = mutation.path[-1]
    if mutation.fault_type == "missing_field":
        if isinstance(node, list):
            node.insert(last, mutation.old)  # pyright: ignore[reportArgumentType, reportCallIssue]
        else:
            node[last] = mutation.old  # pyright: ignore[reportIndexIssue]
    else:
        node[last] = mutation.old  # pyright: ignore[reportIndexIssue]
    return mutated


# ---- the shared properties ----


@pytest.mark.parametrize("fault_type", FAULT_TYPES)
def test_a_planted_fault_always_changes_the_result(fault_type):
    original = payload()

    faulted = plant(original, fault_type=fault_type, seed=7)

    assert faulted.payload != original
    assert faulted.payload["content"] != original["content"]


@pytest.mark.parametrize("fault_type", FAULT_TYPES)
def test_a_planted_fault_is_deterministic_per_seed(fault_type):
    first = plant(payload(), fault_type=fault_type, seed=11)
    second = plant(payload(), fault_type=fault_type, seed=11)
    other = plant(payload(), fault_type=fault_type, seed=12)

    assert first.payload == second.payload
    assert first.mutation == second.mutation
    assert isinstance(other.payload["content"], str)


@pytest.mark.parametrize("fault_type", FAULT_TYPES)
def test_a_planted_fault_keeps_the_calls_identity(fault_type):
    faulted = plant(payload(), fault_type=fault_type, seed=3)

    assert faulted.payload["id"] == "call-1"
    assert faulted.payload["role"] == "tool"
    assert faulted.payload["requestor"] == "assistant"


@pytest.mark.parametrize("fault_type", ["wrong_value", "missing_field", "stale_record"])
def test_a_structured_result_stays_valid_json_of_the_same_shape(fault_type):
    faulted = plant(payload(), fault_type=fault_type, seed=5)

    body = content_of(faulted)

    assert isinstance(body, dict)


@pytest.mark.parametrize("fault_type", ["wrong_value", "stale_record"])
def test_nothing_outside_the_named_path_moves(fault_type):
    faulted = plant(payload(), fault_type=fault_type, seed=5)

    assert restored(content_of(faulted), faulted.mutation, RESERVATION) == RESERVATION


def test_a_dropped_field_is_the_only_thing_missing():
    faulted = plant(payload(), fault_type="missing_field", seed=5)

    assert restored(content_of(faulted), faulted.mutation, RESERVATION) == RESERVATION


# ---- wrong_value ----


def test_wrong_value_preserves_the_type_of_what_it_changes():
    for seed in range(12):
        mutation = plant(payload(), fault_type="wrong_value", seed=seed).mutation

        assert type(mutation.new) is type(mutation.old)
        assert mutation.new != mutation.old


def test_wrong_value_keeps_a_date_looking_like_a_date():
    dated = payload({"date": "2024-05-16"})

    mutation = plant(dated, fault_type="wrong_value", seed=1).mutation

    assert mutation.path == ("date",)
    assert len(str(mutation.new)) == len("2024-05-16")
    assert str(mutation.new)[4] == "-"


def test_wrong_value_keeps_an_identifier_looking_like_an_identifier():
    identified = payload({"reservation_id": "HATHAT"})

    mutation = plant(identified, fault_type="wrong_value", seed=1).mutation

    assert len(str(mutation.new)) == len("HATHAT")
    assert str(mutation.new).isupper()


def test_wrong_value_prefers_a_field_the_agent_uses_later():
    """A fault the run never reads is not a fault -- it is noise that the
    KEEP rule would throw away after four re-runs."""
    both = payload({"unused_note": "nothing", "reservation_id": "HATHAT"})
    context = FaultContext(downstream='the agent later says reservation_id HATHAT again')

    mutation = plant(both, fault_type="wrong_value", seed=4, context=context).mutation

    assert mutation.path == ("reservation_id",)


# ---- missing_field ----


def test_missing_field_drops_a_key():
    faulted = plant(payload(), fault_type="missing_field", seed=2)

    assert faulted.mutation.path[-1] not in content_of(faulted)  # pyright: ignore[reportOperatorIssue]


def test_missing_field_can_drop_a_list_element():
    listed = payload({"flights": [{"flight_number": "HAT001"}, {"flight_number": "HAT002"}]})

    faulted = plant(listed, fault_type="missing_field", seed=0)
    body = content_of(faulted)

    assert isinstance(body, dict)
    assert len(body["flights"]) == 1


def test_missing_field_refuses_a_result_with_nothing_to_drop():
    with pytest.raises(NoFaultPossibleError, match="missing_field"):
        plant(payload("just a sentence"), fault_type="missing_field", seed=1)


# ---- stale_record ----


def test_stale_record_serves_an_earlier_version_when_there_is_one():
    earlier = payload({**RESERVATION, "status": "pending", "total_baggages": 0})

    faulted = plant(payload(), fault_type="stale_record", seed=1,
                    context=FaultContext(earlier=earlier))
    body = content_of(faulted)

    assert isinstance(body, dict)
    assert body["status"] == "pending"
    assert faulted.mutation.path == ()


def test_stale_record_ignores_an_earlier_version_identical_to_the_truth():
    """"Stale" has to mean different, or the run is unfaulted and the KEEP
    rule would silently label a passing run as a planted failure."""
    faulted = plant(payload(), fault_type="stale_record", seed=1,
                    context=FaultContext(earlier=payload()))

    assert faulted.payload["content"] != payload()["content"]
    assert faulted.mutation.path != ()


def test_stale_record_rolls_a_status_backwards():
    delivered = payload({"order_status": "delivered"})

    mutation = plant(delivered, fault_type="stale_record", seed=1).mutation

    assert mutation.old == "delivered"
    assert mutation.new in {"shipped", "pending", "processed"}


def test_stale_record_rolls_a_number_down():
    counted = payload({"total_baggages": 3})

    mutation = plant(counted, fault_type="stale_record", seed=1).mutation

    assert mutation.new < mutation.old


# ---- tool_error ----


def test_tool_error_looks_like_a_real_tau2_error():
    faulted = plant(
        payload(), fault_type="tool_error", seed=1,
        context=FaultContext(tool_name="get_reservation_details",
                             tool_args={"reservation_id": "HATHAT"}),
    )

    assert faulted.payload["error"] is True
    assert faulted.payload["content"].startswith("Error: ")
    assert faulted.mutation.path == ()


def test_tool_error_mentions_the_argument_it_failed_on_when_it_can():
    faulted = plant(
        payload(), fault_type="tool_error", seed=0,
        context=FaultContext(tool_name="get_reservation_details",
                             tool_args={"reservation_id": "HATHAT"}),
    )

    assert "HATHAT" in faulted.payload["content"]


def test_tool_error_still_works_without_any_context():
    faulted = plant(payload(), fault_type="tool_error", seed=0)

    assert faulted.payload["content"].startswith("Error: ")


# ---- refusals ----


def test_an_unknown_fault_type_is_refused():
    with pytest.raises(ValueError, match="unknown fault type"):
        plant(payload(), fault_type="gremlins", seed=1)  # pyright: ignore[reportArgumentType]


def test_a_result_with_no_usable_leaf_is_refused():
    with pytest.raises(NoFaultPossibleError):
        plant(payload({}), fault_type="wrong_value", seed=1)


def test_a_result_already_an_error_cannot_be_faulted_into_an_error():
    already = payload("Error: Reservation HATHAT not found", error=True)

    with pytest.raises(NoFaultPossibleError, match="already"):
        plant(already, fault_type="tool_error", seed=1)


def test_the_mutation_serialises_to_the_dataset_card():
    faulted = plant(payload(), fault_type="wrong_value", seed=1)

    as_json = faulted.mutation.to_dict()

    assert json.loads(json.dumps(as_json))["fault_type"] == "wrong_value"
    assert as_json["path"] == list(faulted.mutation.path)
