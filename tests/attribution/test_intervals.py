"""Wilson and Newcombe intervals, checked against published reference values.

The implementation must not depend on scipy or statsmodels, so the
independent check here re-derives the Wilson interval from the roots of the
score equation -- algebraically different code for the same quantity.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import pytest
from agent_bisect.attribution.estimate import newcombe_diff_interval, wilson_interval
from hypothesis import given
from hypothesis import strategies as st


def _wilson_by_quadratic_roots(successes: int, n: int, conf: float) -> tuple[float, float]:
    """Roots of (n + z^2) p^2 - (2x + z^2) p + x^2/n = 0, the score equation for p."""
    z = NormalDist().inv_cdf(1.0 - (1.0 - conf) / 2.0)
    a = n + z * z
    b = -(2 * successes + z * z)
    c = successes * successes / n
    disc = math.sqrt(b * b - 4 * a * c)
    return ((-b - disc) / (2 * a), (-b + disc) / (2 * a))


def test_wilson_matches_published_reference_for_81_of_263():
    # Arrange / Act
    interval = wilson_interval(81, 263)

    # Assert -- Wilson 95% interval for 81/263 is [0.2553, 0.3662].
    assert interval.low == pytest.approx(0.2553, abs=5e-5)
    assert interval.high == pytest.approx(0.3662, abs=5e-5)


@pytest.mark.parametrize(
    ("successes", "n", "conf"),
    [(0, 4, 0.95), (1, 4, 0.95), (4, 4, 0.95), (7, 16, 0.95), (81, 263, 0.95), (3, 10, 0.90)],
)
def test_wilson_matches_independent_quadratic_root_solution(successes: int, n: int, conf: float):
    # Arrange
    expected_low, expected_high = _wilson_by_quadratic_roots(successes, n, conf)

    # Act
    interval = wilson_interval(successes, n, conf=conf)

    # Assert
    assert interval.low == pytest.approx(expected_low, abs=1e-12)
    assert interval.high == pytest.approx(expected_high, abs=1e-12)


def test_wilson_keeps_a_positive_width_at_zero_successes():
    interval = wilson_interval(0, 16)

    assert interval.low == 0.0
    assert 0.0 < interval.high < 1.0


def test_wilson_keeps_a_positive_width_at_full_successes():
    interval = wilson_interval(16, 16)

    assert interval.high == 1.0
    assert 0.0 < interval.low < 1.0


def test_wilson_narrows_monotonically_as_n_grows():
    widths = [wilson_interval(n // 2, n).width for n in (4, 16, 64, 256, 1024)]

    assert widths == sorted(widths, reverse=True)


def test_wilson_raises_on_zero_n():
    with pytest.raises(ValueError, match="n must be positive"):
        wilson_interval(0, 0)


@pytest.mark.parametrize(("successes", "n"), [(-1, 4), (5, 4)])
def test_wilson_raises_when_successes_outside_zero_to_n(successes: int, n: int):
    with pytest.raises(ValueError, match="successes"):
        wilson_interval(successes, n)


@pytest.mark.parametrize("conf", [0.0, 1.0, -0.1, 1.5])
def test_wilson_raises_on_confidence_outside_the_open_unit_interval(conf: float):
    with pytest.raises(ValueError, match="conf"):
        wilson_interval(1, 4, conf=conf)


def test_newcombe_matches_newcombe_1998_method_10_example():
    # Arrange / Act -- Newcombe (1998) hybrid score interval, method 10.
    interval = newcombe_diff_interval(56, 70, 48, 80)

    # Assert
    assert interval.low == pytest.approx(0.0524, abs=5e-5)
    assert interval.high == pytest.approx(0.3339, abs=5e-5)


def test_newcombe_is_built_from_the_two_wilson_intervals():
    # Arrange
    treated, control = wilson_interval(56, 70), wilson_interval(48, 80)
    diff = 56 / 70 - 48 / 80
    expected_low = diff - math.hypot(56 / 70 - treated.low, control.high - 48 / 80)
    expected_high = diff + math.hypot(treated.high - 56 / 70, 48 / 80 - control.low)

    # Act
    interval = newcombe_diff_interval(56, 70, 48, 80)

    # Assert
    assert interval.low == pytest.approx(expected_low, abs=1e-12)
    assert interval.high == pytest.approx(expected_high, abs=1e-12)


def test_newcombe_is_antisymmetric_under_arm_swap():
    forward = newcombe_diff_interval(12, 16, 2, 16)
    swapped = newcombe_diff_interval(2, 16, 12, 16)

    assert swapped.low == pytest.approx(-forward.high, abs=1e-12)
    assert swapped.high == pytest.approx(-forward.low, abs=1e-12)


def test_newcombe_narrows_monotonically_as_both_arms_grow():
    widths = [newcombe_diff_interval(3 * k, 4 * k, k, 4 * k).width for k in (1, 4, 16, 64)]

    assert widths == sorted(widths, reverse=True)


def test_newcombe_spans_the_full_range_when_both_arms_are_extreme():
    interval = newcombe_diff_interval(4, 4, 0, 4)

    assert -1.0 <= interval.low < 1.0
    assert interval.high == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize(("x1", "n1", "x2", "n2"), [(0, 0, 1, 4), (1, 4, 0, 0)])
def test_newcombe_raises_on_an_empty_arm(x1: int, n1: int, x2: int, n2: int):
    with pytest.raises(ValueError, match="n must be positive"):
        newcombe_diff_interval(x1, n1, x2, n2)


@given(
    n=st.integers(min_value=1, max_value=200),
    frac=st.floats(min_value=0.0, max_value=1.0),
    conf=st.floats(min_value=0.50, max_value=0.999),
)
def test_wilson_bounds_stay_inside_the_unit_interval_and_contain_the_estimate(
    n: int, frac: float, conf: float
):
    successes = round(frac * n)

    interval = wilson_interval(successes, n, conf=conf)

    assert 0.0 <= interval.low <= successes / n <= interval.high <= 1.0


@given(
    n1=st.integers(min_value=1, max_value=64),
    f1=st.floats(min_value=0.0, max_value=1.0),
    n2=st.integers(min_value=1, max_value=64),
    f2=st.floats(min_value=0.0, max_value=1.0),
)
def test_newcombe_bounds_stay_inside_minus_one_to_one_and_contain_the_difference(
    n1: int, f1: float, n2: int, f2: float
):
    x1, x2 = round(f1 * n1), round(f2 * n2)
    diff = x1 / n1 - x2 / n2

    interval = newcombe_diff_interval(x1, n1, x2, n2)

    assert -1.0 <= interval.low <= diff <= interval.high <= 1.0


@given(
    n1=st.integers(min_value=1, max_value=64),
    f1=st.floats(min_value=0.0, max_value=1.0),
    n2=st.integers(min_value=1, max_value=64),
    f2=st.floats(min_value=0.0, max_value=1.0),
)
def test_newcombe_antisymmetry_holds_for_any_pair_of_arms(n1: int, f1: float, n2: int, f2: float):
    x1, x2 = round(f1 * n1), round(f2 * n2)

    forward = newcombe_diff_interval(x1, n1, x2, n2)
    swapped = newcombe_diff_interval(x2, n2, x1, n1)

    assert swapped.low == pytest.approx(-forward.high, abs=1e-12)
    assert swapped.high == pytest.approx(-forward.low, abs=1e-12)
