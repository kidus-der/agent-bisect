"""`demo.policy`: loading the versioned rule file a PR edits.

Deterministic loading and deterministic slip draws are the two properties
`bisect gate` depends on: a PR that only touches `agent_policy.yaml` must
reproduce the same pass/fail on every machine, and the gate's own local
gate-of-the-gate (`scripts/gates/p7.py`) plants regressions by editing this
same file.
"""

from __future__ import annotations

import random

import pytest
from demo.policy import DemoPolicy, PolicyError, load_policy

POLICY_PATH = "demo/agent_policy.yaml"


def test_the_shipped_policy_loads_five_ordered_rules():
    # Act
    policy = load_policy(POLICY_PATH)

    # Assert
    assert [rule.id for rule in policy.rules] == [
        "use_stated_title",
        "use_correct_task_id",
        "set_completed_status",
        "escalate_impossible_requests",
    ]
    assert [rule.order for rule in policy.rules] == [1, 2, 3, 4]


def test_a_rule_is_looked_up_by_id():
    # Arrange
    policy = load_policy(POLICY_PATH)

    # Act
    rule = policy.rule("set_completed_status")

    # Assert
    assert rule.slip_probability == pytest.approx(0.08)
    assert "completed" in rule.statement


def test_looking_up_an_unknown_rule_raises():
    # Arrange
    policy = load_policy(POLICY_PATH)

    # Act / Assert
    with pytest.raises(KeyError):
        policy.rule("does_not_exist")


def test_slip_draws_are_a_pure_function_of_the_rng_state():
    # Arrange
    policy = load_policy(POLICY_PATH)
    rule = policy.rule("use_correct_task_id")  # slip_probability 0.10

    # Act
    first = [policy.slips(rule, random.Random(f"seed-{i}")) for i in range(200)]
    second = [policy.slips(rule, random.Random(f"seed-{i}")) for i in range(200)]

    # Assert
    assert first == second
    slip_rate = sum(first) / len(first)
    assert 0.05 < slip_rate < 0.30, f"200 draws at p=0.15 landed at {slip_rate}"


def test_a_zero_probability_rule_never_slips():
    # Arrange
    policy = DemoPolicy(
        version=1,
        description="test",
        rules=(_rule("never", slip_probability=0.0),),
    )
    rule = policy.rule("never")

    # Act
    outcomes = [policy.slips(rule, random.Random(i)) for i in range(500)]

    # Assert
    assert not any(outcomes)


def test_duplicate_rule_ids_are_rejected(tmp_path):
    # Arrange
    bad = tmp_path / "bad_policy.yaml"
    bad.write_text(
        "version: 1\n"
        "description: bad\n"
        "rules:\n"
        "  - id: dup\n"
        "    order: 1\n"
        "    slip_probability: 0.1\n"
        "    statement: a\n"
        "    slip: b\n"
        "  - id: dup\n"
        "    order: 2\n"
        "    slip_probability: 0.1\n"
        "    statement: c\n"
        "    slip: d\n"
    )

    # Act / Assert
    with pytest.raises(PolicyError, match="duplicate"):
        load_policy(bad)


def test_an_out_of_range_slip_probability_is_rejected(tmp_path):
    # Arrange
    bad = tmp_path / "bad_policy.yaml"
    bad.write_text(
        "version: 1\n"
        "description: bad\n"
        "rules:\n"
        "  - id: r\n"
        "    order: 1\n"
        "    slip_probability: 1.5\n"
        "    statement: a\n"
        "    slip: b\n"
    )

    # Act / Assert
    with pytest.raises(PolicyError, match="slip_probability"):
        load_policy(bad)


def _rule(rule_id: str, *, slip_probability: float):
    from demo.policy import Rule

    return Rule(
        id=rule_id,
        order=1,
        slip_probability=slip_probability,
        statement="s",
        slip="x",
    )
