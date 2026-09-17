"""The synthetic generator: parameters are fixed in docs/decisions/0006-p4-synthetic-design.md."""

from __future__ import annotations

import numpy as np
import pytest
from agent_bisect.attribution.estimate import DEFAULT_DELTA
from agent_bisect.attribution.fakes import (
    BRIEF_12_STEP_RUN,
    DEFAULT_SYNTHETIC_CONFIG,
    FakeRunSpec,
    ScriptedSampler,
    sample_run_spec,
    sample_run_specs,
)

BRIEF_TREATED = (0.10, 0.12, 0.12, 0.18, 0.10, 0.10, 0.88, 0.40, 0.30, 0.18, 0.12, 0.10)
SPECS = sample_run_specs(120, master_seed=4242)


def test_brief_fixture_reproduces_the_briefs_worked_example():
    assert BRIEF_12_STEP_RUN.n_steps == 12
    assert BRIEF_12_STEP_RUN.planted_step == 7
    assert BRIEF_12_STEP_RUN.control_prob == pytest.approx(0.10)
    assert BRIEF_12_STEP_RUN.treated_probs == BRIEF_TREATED


def test_treated_probabilities_are_indexed_from_step_one():
    assert BRIEF_12_STEP_RUN.treated_prob(1) == pytest.approx(0.10)
    assert BRIEF_12_STEP_RUN.treated_prob(7) == pytest.approx(0.88)
    assert BRIEF_12_STEP_RUN.treated_prob(12) == pytest.approx(0.10)


def test_true_effect_subtracts_the_control_rate():
    assert BRIEF_12_STEP_RUN.true_effect(7) == pytest.approx(0.78)
    assert BRIEF_12_STEP_RUN.true_effect(12) == pytest.approx(0.0)


def test_steps_is_the_one_indexed_range_of_the_run():
    assert tuple(BRIEF_12_STEP_RUN.steps) == tuple(range(1, 13))


@pytest.mark.parametrize("step", [0, 13])
def test_asking_for_a_step_outside_the_run_is_an_error(step: int):
    with pytest.raises(ValueError, match="outside"):
        BRIEF_12_STEP_RUN.treated_prob(step)


def test_a_spec_whose_planted_step_is_outside_the_run_is_rejected():
    with pytest.raises(ValueError, match="planted_step"):
        FakeRunSpec(run_id="bad", planted_step=9, control_prob=0.1, treated_probs=(0.1, 0.9))


def test_a_run_with_no_steps_at_all_is_rejected():
    with pytest.raises(ValueError, match="at least one step"):
        FakeRunSpec(run_id="empty", planted_step=1, control_prob=0.1, treated_probs=())


def test_asking_for_a_non_positive_number_of_runs_is_rejected():
    with pytest.raises(ValueError, match="count must be positive"):
        sample_run_specs(0, master_seed=1)


def test_a_spec_with_a_probability_outside_zero_to_one_is_rejected():
    with pytest.raises(ValueError, match="probabilit"):
        FakeRunSpec(run_id="bad", planted_step=2, control_prob=0.1, treated_probs=(0.1, 1.7))


def test_every_generated_run_has_between_eight_and_thirty_steps():
    assert all(
        DEFAULT_SYNTHETIC_CONFIG.min_steps <= spec.n_steps <= DEFAULT_SYNTHETIC_CONFIG.max_steps
        for spec in SPECS
    )


def test_every_generated_run_uses_the_full_step_range_over_enough_draws():
    observed = {spec.n_steps for spec in SPECS}

    assert min(observed) <= 10 and max(observed) >= 28


def test_every_planted_step_leaves_room_for_earlier_and_later_steps():
    for spec in SPECS:
        assert spec.planted_step >= 1 + DEFAULT_SYNTHETIC_CONFIG.min_steps_before_planted
        assert spec.planted_step <= spec.n_steps - DEFAULT_SYNTHETIC_CONFIG.min_steps_after_planted


def test_control_and_planted_rates_stay_inside_their_configured_ranges():
    low, high = DEFAULT_SYNTHETIC_CONFIG.control_prob_range
    planted_low, planted_high = DEFAULT_SYNTHETIC_CONFIG.planted_prob_range

    for spec in SPECS:
        assert low <= spec.control_prob <= high
        assert planted_low <= spec.treated_prob(spec.planted_step) <= planted_high


def test_steps_before_the_planted_step_have_exactly_the_control_rate():
    for spec in SPECS:
        for step in range(1, spec.planted_step):
            assert spec.true_effect(step) == pytest.approx(0.0)


def test_steps_after_the_planted_step_decay_and_never_fall_below_the_control_rate():
    for spec in SPECS:
        tail = [spec.treated_prob(step) for step in range(spec.planted_step + 1, spec.n_steps + 1)]
        assert tail == sorted(tail, reverse=True)
        assert all(prob >= spec.control_prob - 1e-12 for prob in tail)


def test_the_planted_step_is_the_earliest_step_whose_true_effect_clears_delta():
    for spec in SPECS:
        clearing = [
            step for step in spec.steps if spec.true_effect(step) > DEFAULT_DELTA
        ]
        assert clearing and clearing[0] == spec.planted_step


def test_the_planted_step_always_has_the_largest_true_effect():
    for spec in SPECS:
        effects = {step: spec.true_effect(step) for step in spec.steps}
        assert max(effects, key=lambda step: effects[step]) == spec.planted_step


def test_generating_specs_twice_from_one_master_seed_gives_identical_runs():
    assert sample_run_specs(20, master_seed=7) == sample_run_specs(20, master_seed=7)


def test_a_different_master_seed_gives_different_runs():
    assert sample_run_specs(20, master_seed=7) != sample_run_specs(20, master_seed=8)


def test_generated_runs_within_one_batch_are_not_all_the_same():
    assert len({spec.n_steps for spec in SPECS}) > 1
    assert len({spec.planted_step for spec in SPECS}) > 1


def test_each_generated_run_carries_a_distinct_id():
    assert len({spec.run_id for spec in SPECS}) == len(SPECS)


def test_sample_run_spec_takes_its_randomness_from_the_generator_it_is_given():
    first = sample_run_spec(np.random.default_rng(5), run_id="r")
    second = sample_run_spec(np.random.default_rng(5), run_id="r")

    assert first == second


def test_the_sampler_returns_one_outcome_per_requested_rerun():
    sampler = ScriptedSampler(BRIEF_12_STEP_RUN)

    outcomes = sampler.sample(step=7, arm="treated", n=4, seed=1)

    assert len(outcomes) == 4
    assert all(isinstance(outcome, bool) for outcome in outcomes)


def test_the_sampler_repeats_itself_for_the_same_seed_and_differs_across_seeds():
    sampler = ScriptedSampler(BRIEF_12_STEP_RUN)

    assert sampler.sample(step=7, arm="treated", n=16, seed=3) == sampler.sample(
        step=7, arm="treated", n=16, seed=3
    )
    assert sampler.sample(step=7, arm="treated", n=16, seed=3) != sampler.sample(
        step=7, arm="treated", n=16, seed=4
    )


def test_the_treated_arm_passes_at_roughly_the_scripted_rate():
    sampler = ScriptedSampler(BRIEF_12_STEP_RUN)

    outcomes = sampler.sample(step=7, arm="treated", n=20_000, seed=11)

    assert sum(outcomes) / len(outcomes) == pytest.approx(0.88, abs=0.02)


def test_the_control_arm_passes_at_the_control_rate_whatever_step_it_forks_at():
    sampler = ScriptedSampler(BRIEF_12_STEP_RUN)

    early = sampler.sample(step=2, arm="control", n=20_000, seed=12)
    late = sampler.sample(step=11, arm="control", n=20_000, seed=13)

    assert sum(early) / len(early) == pytest.approx(0.10, abs=0.02)
    assert sum(late) / len(late) == pytest.approx(0.10, abs=0.02)


def test_sampling_never_touches_the_global_numpy_random_state():
    # Arrange
    np.random.seed(1234)
    expected = np.random.random()

    # Act
    np.random.seed(1234)
    ScriptedSampler(BRIEF_12_STEP_RUN).sample(step=7, arm="treated", n=64, seed=99)

    # Assert
    assert np.random.random() == expected


def test_the_sampler_rejects_an_arm_it_does_not_know():
    with pytest.raises(ValueError, match="arm"):
        ScriptedSampler(BRIEF_12_STEP_RUN).sample(step=7, arm="placebo", n=4, seed=1)  # type: ignore[arg-type]


def test_the_sampler_rejects_a_step_outside_the_run():
    with pytest.raises(ValueError, match="outside"):
        ScriptedSampler(BRIEF_12_STEP_RUN).sample(step=99, arm="treated", n=4, seed=1)


def test_the_sampler_rejects_a_non_positive_number_of_reruns():
    with pytest.raises(ValueError, match="n must be positive"):
        ScriptedSampler(BRIEF_12_STEP_RUN).sample(step=7, arm="treated", n=0, seed=1)
