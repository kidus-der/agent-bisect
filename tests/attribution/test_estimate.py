"""Sequential estimation, control modes, cost accounting and the blame rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest
from agent_bisect.attribution.estimate import (
    ArmResult,
    RunEstimate,
    SequentialConfig,
    StepEffect,
    blame,
    estimate_run,
    estimate_step,
)

PREREGISTERED = SequentialConfig()
FIXED_N = SequentialConfig(batch=16, max_n=16)


@dataclass
class RecordingSampler:
    """Deterministic pass/fail per arm; remembers every call it was asked for."""

    treated_passes: bool = True
    control_passes: bool = False
    calls: list[tuple[int, str, int, int]] = field(default_factory=list)

    def sample(self, step: int, arm: str, n: int, seed: int) -> tuple[bool, ...]:
        self.calls.append((step, arm, n, seed))
        passes = self.treated_passes if arm == "treated" else self.control_passes
        return (passes,) * n

    def calls_for(self, arm: str) -> list[tuple[int, str, int, int]]:
        return [call for call in self.calls if call[1] == arm]


class BernoulliSampler:
    """Seeded coin flips, so the same seed always yields the same outcomes."""

    def __init__(self, treated_prob: float, control_prob: float) -> None:
        self._treated_prob = treated_prob
        self._control_prob = control_prob

    def sample(self, step: int, arm: str, n: int, seed: int) -> tuple[bool, ...]:
        prob = self._treated_prob if arm == "treated" else self._control_prob
        rng = np.random.default_rng(seed)
        return tuple(bool(value) for value in rng.random(n) < prob)


class WrongLengthSampler:
    def sample(self, step: int, arm: str, n: int, seed: int) -> tuple[bool, ...]:
        return (True,) * (n + 1)


def _effect(step: int, ci_low: float, ci_high: float) -> StepEffect:
    return StepEffect(
        step=step,
        treated=ArmResult(4, 4),
        control=ArmResult(0, 16),
        effect=ci_low,
        ci_low=ci_low,
        ci_high=ci_high,
        n_batches=1,
        stop_reason="blameworthy",
    )


def test_step_stops_at_the_first_batch_when_the_treated_arm_always_passes():
    # Arrange
    sampler = RecordingSampler(treated_passes=True, control_passes=False)

    # Act
    effect = estimate_step(
        7,
        sampler,
        PREREGISTERED,
        seed=1,
        control_mode="shared",
        shared_control=ArmResult(0, 16),
    )

    # Assert
    assert effect.stop_reason == "blameworthy"
    assert effect.n_batches == 1
    assert effect.treated == ArmResult(4, 4)
    assert effect.ci_low > PREREGISTERED.delta


def test_step_runs_to_max_n_when_four_at_a_time_is_never_decisive():
    sampler = RecordingSampler(treated_passes=False, control_passes=False)

    effect = estimate_step(
        3, sampler, PREREGISTERED, seed=1, control_mode="shared", shared_control=ArmResult(0, 16)
    )

    assert effect.stop_reason == "max_n"
    assert effect.treated.n == PREREGISTERED.max_n
    assert effect.n_batches == PREREGISTERED.max_n // PREREGISTERED.batch


def test_step_stops_as_cleared_once_the_interval_sits_at_or_below_delta():
    # Arrange -- delta is only reachable with arms far larger than the pre-registered plan.
    config = SequentialConfig(batch=50, max_n=200)
    sampler = RecordingSampler(treated_passes=False, control_passes=False)

    # Act
    effect = estimate_step(
        3, sampler, config, seed=1, control_mode="shared", shared_control=ArmResult(0, 200)
    )

    # Assert
    assert effect.stop_reason == "cleared"
    assert effect.ci_high <= config.delta
    assert effect.treated.n < config.max_n


def test_fixed_n_design_takes_exactly_one_look_of_max_n():
    sampler = RecordingSampler(treated_passes=False, control_passes=False)

    effect = estimate_step(
        3, sampler, FIXED_N, seed=1, control_mode="shared", shared_control=ArmResult(0, 16)
    )

    assert effect.n_batches == 1
    assert effect.treated.n == 16


def test_shared_control_is_drawn_once_at_the_earliest_tested_step():
    # Arrange
    sampler = RecordingSampler(treated_passes=True, control_passes=False)

    # Act
    estimate_run([9, 4, 6], sampler, PREREGISTERED, control_mode="shared", seed=11)

    # Assert
    control_calls = sampler.calls_for("control")
    assert len(control_calls) == 1
    assert control_calls[0][0] == 4
    assert control_calls[0][2] == PREREGISTERED.max_n


def test_shared_control_arm_is_identical_for_every_tested_step():
    sampler = BernoulliSampler(treated_prob=0.5, control_prob=0.3)

    estimate = estimate_run([2, 5, 8], sampler, PREREGISTERED, control_mode="shared", seed=11)

    controls = {effect.control for effect in estimate.step_effects}
    assert len(controls) == 1
    assert estimate.control_fork_step == 2


def test_per_step_control_grows_in_lockstep_with_its_treated_arm():
    sampler = BernoulliSampler(treated_prob=0.5, control_prob=0.5)

    estimate = estimate_run([2, 5], sampler, PREREGISTERED, control_mode="per_step", seed=11)

    assert estimate.control_fork_step is None
    for effect in estimate.step_effects:
        assert effect.control is not None
        assert effect.control.n == effect.treated.n


def test_no_control_mode_reports_the_treated_pass_rate_with_a_wilson_interval():
    # Arrange
    sampler = RecordingSampler(treated_passes=True)

    # Act
    estimate = estimate_run([4], sampler, PREREGISTERED, control_mode="none", seed=3)
    effect = estimate.step_effects[0]

    # Assert
    assert effect.control is None
    assert effect.effect == pytest.approx(1.0)
    assert estimate.control_reruns == 0
    assert sampler.calls_for("control") == []


def test_shared_control_costs_max_n_reruns_and_one_extra_sampler_call():
    # Arrange -- treated always passes, so every step stops after one batch.
    sampler = RecordingSampler(treated_passes=True, control_passes=False)

    # Act
    estimate = estimate_run([1, 2, 3], sampler, PREREGISTERED, control_mode="shared", seed=5)

    # Assert
    assert estimate.treated_reruns == 3 * PREREGISTERED.batch
    assert estimate.control_reruns == PREREGISTERED.max_n
    assert estimate.total_reruns == 3 * PREREGISTERED.batch + PREREGISTERED.max_n
    assert estimate.sampler_calls == 3 + 1
    assert len(sampler.calls) == estimate.sampler_calls


def test_per_step_control_doubles_both_the_reruns_and_the_sampler_calls():
    sampler = RecordingSampler(treated_passes=True, control_passes=False)

    estimate = estimate_run([1, 2, 3], sampler, PREREGISTERED, control_mode="per_step", seed=5)

    assert estimate.control_reruns == estimate.treated_reruns
    assert estimate.sampler_calls == 2 * 3
    assert len(sampler.calls) == estimate.sampler_calls


def test_early_stopping_spends_fewer_reruns_than_the_fixed_design():
    sampler = BernoulliSampler(treated_prob=0.9, control_prob=0.05)

    sequential = estimate_run([1, 2, 3], sampler, PREREGISTERED, seed=7)
    fixed = estimate_run([1, 2, 3], sampler, FIXED_N, seed=7)

    assert sequential.total_reruns < fixed.total_reruns


def test_blame_names_the_earliest_step_whose_lower_bound_clears_delta():
    effects = (_effect(2, 0.05, 0.4), _effect(5, 0.30, 0.8), _effect(9, 0.60, 0.95))

    assert blame(effects, delta=0.10) == 5


def test_blame_ignores_a_larger_effect_at_a_later_step():
    effects = (_effect(9, 0.90, 0.99), _effect(5, 0.11, 0.5))

    assert blame(effects, delta=0.10) == 5


def test_blame_returns_none_when_no_step_clears_delta():
    effects = (_effect(2, 0.05, 0.4), _effect(5, 0.10, 0.8))

    assert blame(effects, delta=0.10) is None


def test_blame_of_no_steps_is_none():
    assert blame(()) is None


def test_estimate_run_is_reproducible_for_the_same_seed():
    sampler = BernoulliSampler(treated_prob=0.6, control_prob=0.1)

    first = estimate_run(range(1, 9), sampler, PREREGISTERED, seed=2026)
    second = estimate_run(range(1, 9), sampler, PREREGISTERED, seed=2026)

    assert first == second
    assert isinstance(first, RunEstimate)


def test_a_different_seed_draws_different_outcomes():
    sampler = BernoulliSampler(treated_prob=0.6, control_prob=0.1)

    first = estimate_run(range(1, 9), sampler, PREREGISTERED, seed=1)
    second = estimate_run(range(1, 9), sampler, PREREGISTERED, seed=2)

    assert first != second


def test_arms_of_one_step_are_seeded_independently_of_each_other():
    sampler = RecordingSampler(treated_passes=False, control_passes=False)

    estimate_run([4], sampler, PREREGISTERED, control_mode="per_step", seed=99)

    seeds = [call[3] for call in sampler.calls]
    assert len(set(seeds)) == len(seeds)


def test_estimate_run_sorts_and_deduplicates_the_tested_steps():
    sampler = BernoulliSampler(treated_prob=0.6, control_prob=0.1)

    estimate = estimate_run([5, 2, 5, 2, 9], sampler, PREREGISTERED, seed=4)

    assert [effect.step for effect in estimate.step_effects] == [2, 5, 9]


def test_estimate_run_rejects_an_empty_step_list():
    with pytest.raises(ValueError, match="tested_steps must not be empty"):
        estimate_run([], RecordingSampler(), PREREGISTERED, seed=1)


def test_estimate_step_rejects_shared_mode_without_a_control_arm():
    with pytest.raises(ValueError, match="requires a shared_control"):
        estimate_step(1, RecordingSampler(), PREREGISTERED, seed=1, control_mode="shared")


@pytest.mark.parametrize("mode", ["per_step", "none"])
def test_estimate_step_rejects_a_shared_control_arm_in_other_modes(mode: str):
    with pytest.raises(ValueError, match="only meaningful for control_mode='shared'"):
        estimate_step(
            1,
            RecordingSampler(),
            PREREGISTERED,
            seed=1,
            control_mode=mode,  # type: ignore[arg-type]
            shared_control=ArmResult(0, 16),
        )


def test_estimate_step_rejects_a_sampler_that_returns_the_wrong_number_of_outcomes():
    with pytest.raises(ValueError, match="expected 4"):
        estimate_step(
            1,
            WrongLengthSampler(),
            PREREGISTERED,
            seed=1,
            control_mode="shared",
            shared_control=ArmResult(0, 16),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"batch": 0}, "batch must be positive"),
        ({"batch": 8, "max_n": 4}, "must be at least batch"),
        ({"delta": 1.0}, "delta must be in"),
        ({"delta": -0.1}, "delta must be in"),
        ({"conf": 1.0}, "conf must be strictly between"),
    ],
)
def test_sequential_config_rejects_impossible_plans(kwargs: dict[str, Any], message: str):
    with pytest.raises(ValueError, match=message):
        SequentialConfig(**kwargs)


def test_arm_result_rejects_more_successes_than_draws():
    with pytest.raises(ValueError, match="successes must be between"):
        ArmResult(5, 4)


def test_arm_result_rejects_a_negative_draw_count():
    with pytest.raises(ValueError, match="n must not be negative"):
        ArmResult(0, -1)


def test_an_empty_arm_has_no_pass_rate():
    with pytest.raises(ValueError, match="empty arm"):
        _ = ArmResult(0, 0).rate


def test_extending_an_arm_returns_a_new_arm_and_leaves_the_original_alone():
    original = ArmResult(1, 4)

    extended = original.extended(3, 4)

    assert original == ArmResult(1, 4)
    assert extended == ArmResult(4, 8)


def test_step_effect_exposes_its_interval():
    effect = _effect(3, 0.2, 0.5)

    assert effect.interval.contains(0.3)
    assert effect.interval.width == pytest.approx(0.3)
