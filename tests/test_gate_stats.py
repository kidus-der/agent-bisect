"""`gate.stats`: the pooled two-proportion regression rule of
`docs/decisions/0019-gate-rule.md`."""

from __future__ import annotations

import pytest
from agent_bisect.gate.stats import GateComparison, two_proportion_p_value


def test_identical_pass_rates_are_not_a_regression():
    comparison = GateComparison(head_passes=29, head_n=32, base_passes=29, base_n=32)

    assert comparison.is_regression is False


def test_a_large_reliable_drop_is_a_regression():
    # base ~0.91 (29/32), head ~0.28 (9/32): a 63-point drop, comfortably
    # clear of both the CI-below-0 and the 10-point floor.
    comparison = GateComparison(head_passes=9, head_n=32, base_passes=29, base_n=32)

    assert comparison.is_regression is True
    assert comparison.interval.high < 0.0
    assert comparison.diff == pytest.approx(9 / 32 - 29 / 32)


def test_a_small_drop_below_the_ten_point_floor_is_not_a_regression():
    # base 0.90, head 0.85 on a huge n: the CI clears 0 easily, but the
    # point drop never reaches 10 points, so the floor blocks it.
    comparison = GateComparison(head_passes=850, head_n=1000, base_passes=900, base_n=1000)

    assert comparison.base_rate - comparison.head_rate == pytest.approx(0.05)
    assert comparison.is_regression is False


def test_a_drop_that_clears_ten_points_but_not_the_ci_is_not_a_regression():
    # Small n: base 3/4, head 2/4 is a 25-point drop, but the Wilson/Newcombe
    # interval at this n is wide enough that it still straddles 0.
    comparison = GateComparison(head_passes=2, head_n=4, base_passes=3, base_n=4)

    assert comparison.base_rate - comparison.head_rate == pytest.approx(0.25)
    assert comparison.interval.high >= 0.0
    assert comparison.is_regression is False


def test_an_improvement_is_never_a_regression():
    comparison = GateComparison(head_passes=32, head_n=32, base_passes=20, base_n=32)

    assert comparison.is_regression is False
    assert comparison.diff > 0


def test_p_value_is_small_for_a_stark_difference_and_large_for_none():
    stark = two_proportion_p_value(9, 32, 29, 32)
    none = two_proportion_p_value(29, 32, 29, 32)

    assert stark < 0.01
    assert none == pytest.approx(1.0)


def test_p_value_is_symmetric_in_its_two_arms():
    assert two_proportion_p_value(9, 32, 29, 32) == pytest.approx(
        two_proportion_p_value(29, 32, 9, 32)
    )


@pytest.mark.parametrize("head_n,base_n", [(0, 10), (10, 0)])
def test_an_empty_arm_is_rejected(head_n, base_n):
    with pytest.raises(ValueError, match="at least one run"):
        GateComparison(head_passes=0, head_n=head_n, base_passes=0, base_n=base_n)
