"""The O'Brien-Fleming efficacy boundary (docs/decisions/0008-*).

The constants are checked against their published form rather than pasted in:
OBF sets z_j = C * sqrt(K / j), and on the score scale the boundary is the
constant C * sqrt(K), so the overall two-sided alpha can be integrated directly.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pytest
from agent_bisect.attribution.estimate import (
    OBF_CONSTANT,
    OBF_CRITICAL_Z,
    OBF_LOOKS,
    ArmResult,
    SequentialConfig,
    confidence_for_z,
    decision_confidence,
    estimate_run,
    estimate_step,
)

NOMINAL_ALPHAS = (0.00005, 0.00420, 0.01944, 0.04297)


def test_the_boundary_has_one_critical_value_per_planned_look():
    assert len(OBF_CRITICAL_Z) == OBF_LOOKS == 4


def test_each_critical_value_matches_the_published_obf_form():
    # Arrange / Act -- z_j = C * sqrt(K / j) with C = C_B(4, 0.05) = 2.024.
    expected = [OBF_CONSTANT * math.sqrt(OBF_LOOKS / look) for look in range(1, OBF_LOOKS + 1)]

    # Assert -- the tabulated values are the published constant rounded to three
    # decimals, so they sit within one rounding step of C * sqrt(K / j).
    for actual, wanted in zip(OBF_CRITICAL_Z, expected, strict=True):
        assert actual == pytest.approx(wanted, abs=2e-3)


def test_the_critical_values_reproduce_the_published_nominal_alphas():
    for critical_z, alpha in zip(OBF_CRITICAL_Z, NOMINAL_ALPHAS, strict=True):
        two_sided = 2.0 * (1.0 - NormalDist().cdf(critical_z))
        assert two_sided == pytest.approx(alpha, abs=5e-6)


def test_the_boundary_gets_less_strict_at_every_later_look():
    assert list(OBF_CRITICAL_Z) == sorted(OBF_CRITICAL_Z, reverse=True)


def test_the_final_look_is_stricter_than_an_uncorrected_ninety_five_percent_test():
    assert OBF_CRITICAL_Z[-1] > NormalDist().inv_cdf(0.975)


def test_the_overall_two_sided_alpha_of_the_whole_boundary_is_five_percent():
    """On the score scale OBF is the constant b = C*sqrt(K); integrate the crossing."""
    # Arrange -- density of the restricted random walk, unit normal increments.
    bound = OBF_CONSTANT * math.sqrt(OBF_LOOKS)
    step = 0.002
    grid = np.arange(-bound, bound + step / 2, step)
    normal = lambda x: np.exp(-x * x / 2) / math.sqrt(2 * math.pi)  # noqa: E731
    kernel = normal(np.arange(-12, 12 + step / 2, step)) * step
    density = normal(grid)

    # Act -- convolve once per further look, restricting to the continuation region.
    for _ in range(OBF_LOOKS - 1):
        convolved = np.convolve(density, kernel)
        offset = (len(kernel) - 1) // 2
        density = convolved[offset : offset + len(grid)]

    # Assert
    alpha = 1.0 - float(np.trapezoid(density, grid))
    assert alpha == pytest.approx(0.05, abs=1e-3)


def test_a_confidence_level_round_trips_through_its_critical_value():
    assert confidence_for_z(NormalDist().inv_cdf(0.975)) == pytest.approx(0.95, abs=1e-12)


def test_the_decision_confidence_follows_the_boundary_look_by_look():
    config = SequentialConfig(efficacy_boundary="obf")

    levels = [decision_confidence(config, look) for look in range(1, 5)]

    assert levels == [pytest.approx(confidence_for_z(z), abs=1e-12) for z in OBF_CRITICAL_Z]
    assert levels[0] > levels[-1] > config.conf


def test_without_a_boundary_every_look_uses_the_nominal_level():
    config = SequentialConfig(efficacy_boundary="none")

    assert [decision_confidence(config, look) for look in range(1, 5)] == [config.conf] * 4


def test_a_plan_with_four_looks_is_required_by_the_obf_boundary():
    with pytest.raises(ValueError, match="exactly 4 looks"):
        SequentialConfig(batch=16, max_n=16, efficacy_boundary="obf")


def test_a_single_look_fixed_design_is_still_allowed_without_a_boundary():
    config = SequentialConfig(batch=16, max_n=16, efficacy_boundary="none")

    assert decision_confidence(config, 1) == config.conf


def test_an_unknown_boundary_name_is_rejected():
    with pytest.raises(ValueError, match="efficacy_boundary"):
        SequentialConfig(efficacy_boundary="pocock")  # type: ignore[arg-type]


def test_the_boundary_is_on_by_default():
    assert SequentialConfig().efficacy_boundary == "obf"


class _AlwaysPasses:
    """Treated arm passes every re-run; control never does."""

    def sample(self, step: int, arm: str, n: int, seed: int) -> tuple[bool, ...]:
        return (arm == "treated",) * n


def test_a_perfect_first_look_no_longer_blames_under_the_boundary():
    # Arrange -- 4/4 treated against a 0/16 control cleared delta at the old
    # nominal level; at look 1 the boundary demands z = 4.049.
    sampler = _AlwaysPasses()

    # Act
    corrected = estimate_step(
        7,
        sampler,
        SequentialConfig(efficacy_boundary="obf"),
        seed=1,
        control_mode="shared",
        shared_control=ArmResult(0, 16),
    )
    uncorrected = estimate_step(
        7,
        sampler,
        SequentialConfig(efficacy_boundary="none"),
        seed=1,
        control_mode="shared",
        shared_control=ArmResult(0, 16),
    )

    # Assert
    assert uncorrected.n_batches == 1 and uncorrected.blameworthy
    assert corrected.n_batches > 1


def test_an_overwhelming_treated_arm_is_still_blamed_once_enough_looks_agree():
    # A perfect arm is not decisive at look 1 under the boundary, but it does
    # not have to survive to N = 16 either -- 8/8 against 0/16 clears look 2.
    effect = estimate_step(
        7,
        _AlwaysPasses(),
        SequentialConfig(efficacy_boundary="obf"),
        seed=1,
        control_mode="shared",
        shared_control=ArmResult(0, 16),
    )

    assert effect.blameworthy
    assert 1 < effect.n_batches <= OBF_LOOKS
    assert effect.treated == ArmResult(effect.treated.n, effect.treated.n)


def test_the_reported_interval_stays_at_the_nominal_level_while_the_decision_does_not():
    effect = estimate_step(
        7,
        _AlwaysPasses(),
        SequentialConfig(efficacy_boundary="obf"),
        seed=1,
        control_mode="shared",
        shared_control=ArmResult(0, 16),
    )

    # The decision used the boundary level for the look that made it ...
    assert effect.decision_conf == pytest.approx(
        confidence_for_z(OBF_CRITICAL_Z[effect.n_batches - 1])
    )
    # ... which is stricter than nominal, so its bound is the more conservative one.
    assert effect.decision_conf > 0.95
    assert effect.decision_ci_low < effect.ci_low


class _NullSampler:
    """Both arms pass at the same rate: every step has a true effect of zero."""

    def __init__(self, prob: float) -> None:
        self._prob = prob

    def sample(self, step: int, arm: str, n: int, seed: int) -> tuple[bool, ...]:
        rng = np.random.default_rng(seed)
        return tuple(bool(draw) for draw in rng.random(n) < self._prob)


def _null_flag_rate(boundary: str, runs: int = 300) -> float:
    """Fraction of truly-null steps wrongly declared blame-worthy."""
    config = SequentialConfig(efficacy_boundary=boundary)  # type: ignore[arg-type]
    sampler = _NullSampler(0.10)
    flagged = tested = 0
    for seed in range(runs):
        estimate = estimate_run(range(1, 9), sampler, config, "shared", seed=seed)
        flagged += sum(1 for effect in estimate.step_effects if effect.blameworthy)
        tested += len(estimate.step_effects)
    return flagged / tested


def test_the_boundary_cuts_the_false_positive_rate_on_truly_null_steps():
    assert _null_flag_rate("obf") < _null_flag_rate("none")


def test_the_boundary_leaves_almost_no_false_positives_on_truly_null_steps():
    assert _null_flag_rate("obf") < 0.005
