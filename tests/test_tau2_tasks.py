"""Which tasks are collected from, and in what order.

`docs/decisions/0017-p3-collection-policy.md`: airline first, then the
retail tasks whose reward costs no model call, then the rest.
"""

from __future__ import annotations

import pytest
from agent_bisect.adapters.tau2_tasks import (
    collection_order,
    needs_a_judge,
    shard_of,
    task_ids,
)


def test_no_airline_task_needs_a_judge():
    assert task_ids("airline", judged=True) == []
    assert len(task_ids("airline")) == 50


def test_most_retail_tasks_are_as_cheap_to_score_as_airline():
    """112 of 114 retail tasks carry NL_ASSERTION in their reward basis,
    but only the 40 that also list nl_assertions actually call a model."""
    assert len(task_ids("retail", judged=True)) == 40
    assert len(task_ids("retail", judged=False)) == 74


def test_the_judged_tasks_come_last():
    order = collection_order()
    judged = {(d, t) for d in ("airline", "retail") for t in task_ids(d, judged=True)}

    first_judged = next(i for i, task in enumerate(order) if task in judged)

    assert all(task not in judged for task in order[:first_judged])
    assert len(order) == 164


def test_airline_comes_before_retail_among_the_cheap_tasks():
    cheap = [task for task in collection_order() if task[0] == "airline"] 

    assert collection_order()[: len(cheap)] == cheap


def test_a_task_without_evaluation_criteria_needs_no_judge():
    assert needs_a_judge(object()) is False


def test_shards_partition_the_tasks_without_overlap():
    tasks = collection_order()

    shards = [shard_of(tasks, index, 4) for index in range(4)]

    assert sorted(task for hand in shards for task in hand) == sorted(tasks)
    assert len({len(hand) for hand in shards}) <= 2


def test_a_shard_is_dealt_round_robin_so_cost_is_spread():
    tasks = [("d", str(index)) for index in range(10)]

    assert shard_of(tasks, 0, 3) == [("d", "0"), ("d", "3"), ("d", "6"), ("d", "9")]


def test_an_impossible_shard_is_refused():
    with pytest.raises(ValueError, match="shard"):
        shard_of([("d", "0")], 3, 3)
