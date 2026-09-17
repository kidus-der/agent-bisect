"""`demo.tasks`: the fixed scenario table and its run-id bookkeeping."""

from __future__ import annotations

import pytest
from demo.tasks import SCENARIOS, run_id_for, scenario, scenario_of_run_id


def test_eight_scenarios_with_unique_names_and_task_ids():
    assert len(SCENARIOS) == 8
    assert len({s.name for s in SCENARIOS}) == 8
    assert len({s.task_id for s in SCENARIOS}) == 8


def test_every_rule_id_governs_at_least_one_scenario():
    from demo.policy import load_policy

    policy = load_policy("demo/agent_policy.yaml")
    governed = {s.rule_id for s in SCENARIOS}
    assert governed == {rule.id for rule in policy.rules}


def test_scenario_looks_up_by_name():
    assert scenario("impossible_delete").task_id == "impossible_task_1"


def test_unknown_scenario_name_raises():
    with pytest.raises(KeyError):
        scenario("does-not-exist")


def test_run_id_round_trips_through_scenario_of_run_id():
    run_id = run_id_for("create_task", 2)

    assert scenario_of_run_id(run_id).name == "create_task"


def test_scenario_of_run_id_resolves_a_forked_run_id():
    # A fork id built the way `attribution.search.rerun_id` builds one:
    # `f"{parent}-{arm[0]}{step}-{digest}"`.
    forked = f"{run_id_for('update_task_from_history', 0)}-t3-abc123"

    assert scenario_of_run_id(forked).name == "update_task_from_history"


def test_scenario_of_run_id_does_not_confuse_a_prefix_scenario_name():
    # "update_task_fixed_id" is not a prefix of "update_task_from_history"'s
    # run id, but the reverse check (longest match) is what this guards.
    run_id = run_id_for("update_task_history_env_assertion", 1)

    assert scenario_of_run_id(run_id).name == "update_task_history_env_assertion"


def test_unresolvable_run_id_raises():
    with pytest.raises(KeyError):
        scenario_of_run_id("not-a-demo-run")
