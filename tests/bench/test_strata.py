"""Position buckets, attempt order and fault-type balance.

The pre-registration fixes the strata (`docs/decisions/0001-preregistration.md`):
"fault step k is a TOOL-RESULT step, stratified early / middle / late
(thirds of the run's tool-result steps by position in the run)" and "4
fault types". These are the mechanics of both.
"""

from __future__ import annotations

import pytest
from agent_bisect.bench.faults import FAULT_TYPES
from agent_bisect.bench.strata import (
    POSITION_BUCKETS,
    FaultBalancer,
    attempt_order,
    bucket_of,
    bucketed,
)


def test_the_thirds_are_thirds():
    assert [bucket_of(index, 9) for index in range(9)] == [
        "early", "early", "early", "middle", "middle", "middle", "late", "late", "late"
    ]


def test_a_run_too_short_for_three_buckets_fills_them_in_order():
    """Thirds of a two-step run are the first and the second third; there
    is no late stratum to put anything in, and inventing one by calling
    the last step "late" would make the strata disagree with the counts
    the dataset card reports."""
    assert [bucket_of(index, 3) for index in range(3)] == ["early", "middle", "late"]
    assert [bucket_of(index, 2) for index in range(2)] == ["early", "middle"]
    assert bucket_of(0, 1) == "early"


def test_a_bucket_is_never_outside_the_three():
    for total in range(1, 40):
        assert {bucket_of(index, total) for index in range(total)} <= set(POSITION_BUCKETS)


def test_bucket_of_refuses_an_impossible_position():
    with pytest.raises(ValueError, match="position"):
        bucket_of(3, 3)


def test_tool_steps_are_bucketed_by_their_position_among_tool_steps():
    """Position is among the run's *tool-result* steps, not among all its
    steps: an LLM turn is not a candidate fault site."""
    assert bucketed([2, 5, 9, 11, 14, 18]) == {
        "early": [2, 5],
        "middle": [9, 11],
        "late": [14, 18],
    }


def test_the_attempt_order_visits_every_bucket_before_repeating_one():
    order = attempt_order(bucketed([1, 2, 3, 4, 5, 6]), seed=1, attempts_per_bucket=2)

    assert [bucket for bucket, _step in order[:3]] == list(POSITION_BUCKETS)
    assert len(order) == 6


def test_the_attempt_order_is_seeded_and_reproducible():
    steps = list(range(12))

    first = attempt_order(bucketed(steps), seed=4, attempts_per_bucket=2)
    again = attempt_order(bucketed(steps), seed=4, attempts_per_bucket=2)
    other = attempt_order(bucketed(steps), seed=5, attempts_per_bucket=2)

    assert first == again
    assert first != other


def test_the_attempt_order_never_offers_more_than_a_bucket_holds():
    order = attempt_order(bucketed([1, 2]), seed=0, attempts_per_bucket=3)

    assert sorted(step for _bucket, step in order) == [1, 2]


def test_the_balancer_spreads_the_four_fault_types_evenly():
    balancer = FaultBalancer()

    taken = [balancer.take(FAULT_TYPES) for _ in range(8)]

    assert sorted(taken) == sorted(FAULT_TYPES * 2)


def test_the_balancer_only_offers_what_is_possible_here():
    balancer = FaultBalancer()

    taken = [balancer.take(("tool_error", "wrong_value")) for _ in range(4)]

    assert set(taken) == {"tool_error", "wrong_value"}
    assert balancer.counts["tool_error"] == 2


def test_the_balancer_refuses_an_empty_choice():
    with pytest.raises(ValueError, match="no fault type"):
        FaultBalancer().take(())


def test_the_balancer_resumes_from_what_is_already_kept():
    balancer = FaultBalancer({"wrong_value": 3, "tool_error": 3, "stale_record": 3})

    assert balancer.take(FAULT_TYPES) == "missing_field"
