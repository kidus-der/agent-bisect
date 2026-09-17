"""P5's statistics: classification, Wilson accuracy, recall@m, cluster bootstrap."""

from __future__ import annotations

import pytest
from agent_bisect.bench.metrics import (
    BOOTSTRAP_RESAMPLES,
    accuracy_with_ci,
    classify,
    paired_bootstrap_gap,
    recall_at,
    recall_curve,
)

# ---- classify ----


def test_naming_the_planted_step_is_exact():
    assert classify(predicted=7, planted=7) == "exact"


def test_naming_an_earlier_step_is_earlier():
    assert classify(predicted=3, planted=7) == "earlier"


def test_naming_a_later_step_is_later():
    assert classify(predicted=9, planted=7) == "later"


def test_naming_no_step_is_none():
    assert classify(predicted=None, planted=7) == "none"


# ---- accuracy_with_ci ----


def test_accuracy_counts_only_exact_hits():
    # Arrange
    outcomes = [True, True, False, False]

    # Act
    result = accuracy_with_ci(outcomes)

    # Assert
    assert result.value == 0.5


def test_a_non_detection_counts_as_wrong_not_as_missing():
    # Arrange: three items, one of which blamed nothing
    labels = ["exact", "none", "later"]

    # Act
    result = accuracy_with_ci([label == "exact" for label in labels])

    # Assert
    assert result.value == pytest.approx(1 / 3)


def test_the_interval_brackets_the_estimate():
    # Arrange / Act
    result = accuracy_with_ci([True] * 7 + [False] * 3)

    # Assert
    assert result.ci_low <= result.value <= result.ci_high


def test_a_perfect_score_still_has_an_interval_below_one():
    # Arrange / Act
    result = accuracy_with_ci([True] * 10)

    # Assert
    assert result.value == 1.0
    assert result.ci_low < 1.0


def test_an_empty_sample_is_refused():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="empty"):
        accuracy_with_ci([])


# ---- recall@m ----


def test_recall_at_one_is_the_top_of_the_ranking():
    # Arrange
    rankings = [(5, 1, 3), (2, 7, 9)]
    planted = [5, 7]

    # Act / Assert
    assert recall_at(rankings, planted, 1) == 0.5


def test_recall_at_three_catches_a_second_place_hit():
    # Arrange
    rankings = [(5, 1, 3), (2, 7, 9)]
    planted = [5, 7]

    # Act / Assert
    assert recall_at(rankings, planted, 2) == 1.0


def test_an_empty_ranking_never_contains_the_planted_step():
    # Arrange / Act / Assert
    assert recall_at([()], [5], 10) == 0.0


def test_recall_is_monotonic_in_m():
    # Arrange
    rankings = [(1, 2, 3, 4, 5), (9, 8, 7, 6, 5)]
    planted = [4, 5]

    # Act
    curve = recall_curve(rankings, planted, max_m=5)

    # Assert
    assert [curve[m] for m in range(1, 6)] == sorted(curve[m] for m in range(1, 6))


def test_the_recall_curve_covers_every_requested_m():
    # Arrange / Act
    curve = recall_curve([(1,)], [1], max_m=10)

    # Assert
    assert sorted(curve) == list(range(1, 11))


def test_mismatched_rankings_and_labels_are_refused():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="same length"):
        recall_at([(1,)], [1, 2], 1)


# ---- paired bootstrap ----


def test_the_gap_is_the_difference_of_the_two_accuracies():
    # Arrange: a beats b on 4 of 4 items
    a = [True, True, True, True]
    b = [False, False, False, False]

    # Act
    gap = paired_bootstrap_gap(a, b, groups=["t1", "t2", "t3", "t4"], seed=1)

    # Assert
    assert gap.value == 1.0


def test_two_identical_methods_have_a_zero_gap_and_a_degenerate_interval():
    # Arrange
    outcomes = [True, False, True, False]

    # Act
    gap = paired_bootstrap_gap(outcomes, outcomes, groups=list("abcd"), seed=1)

    # Assert
    assert gap.value == 0.0
    assert gap.ci_low == gap.ci_high == 0.0


def test_the_interval_contains_the_point_estimate():
    # Arrange
    a = [True] * 8 + [False] * 2
    b = [True] * 4 + [False] * 6

    # Act
    gap = paired_bootstrap_gap(a, b, groups=[f"t{i}" for i in range(10)], seed=7)

    # Assert
    assert gap.ci_low <= gap.value <= gap.ci_high


def test_the_bootstrap_is_reproducible_from_its_seed():
    # Arrange
    a = [True, False] * 10
    b = [False] * 20
    groups = [f"t{i // 2}" for i in range(20)]

    # Act
    first = paired_bootstrap_gap(a, b, groups=groups, seed=42)
    second = paired_bootstrap_gap(a, b, groups=groups, seed=42)

    # Assert
    assert (first.ci_low, first.ci_high) == (second.ci_low, second.ci_high)


def test_the_seed_really_drives_the_resampling():
    # Arrange: few resamples, so the quantiles are noisy enough that two
    # seeds must disagree if the seed is being used at all. At the
    # pre-registered 10,000 they agree to the grid, which is the point of
    # running that many.
    a = [True] * 12 + [False] * 8
    b = [True] * 4 + [False] * 16
    groups = [f"t{i // 2}" for i in range(20)]

    # Act
    first = paired_bootstrap_gap(a, b, groups=groups, seed=1, resamples=40)
    second = paired_bootstrap_gap(a, b, groups=groups, seed=2, resamples=40)

    # Assert
    assert (first.ci_low, first.ci_high) != (second.ci_low, second.ci_high)


def test_the_full_resample_count_is_stable_across_seeds_on_a_coarse_sample():
    # Arrange: 10 two-item tasks put every group mean on {0, 0.5, 1}, so the
    # 95% quantiles land on the same grid points whatever the seed. Pinned
    # so a future change to the resampling cannot quietly make the gate
    # seed-sensitive without a test noticing.
    a = [True] * 12 + [False] * 8
    b = [True] * 4 + [False] * 16
    groups = [f"t{i // 2}" for i in range(20)]

    # Act
    first = paired_bootstrap_gap(a, b, groups=groups, seed=1)
    second = paired_bootstrap_gap(a, b, groups=groups, seed=2)

    # Assert
    assert (first.ci_low, first.ci_high) == (second.ci_low, second.ci_high)


def test_items_of_one_task_move_together_in_a_resample():
    # Arrange: one task's 20 items all favour a, the other's all favour b.
    # Resampling items independently would almost never produce an extreme
    # split; resampling tasks does, so the interval must be wide.
    a = [True] * 20 + [False] * 20
    b = [False] * 20 + [True] * 20
    grouped = ["task-a"] * 20 + ["task-b"] * 20
    ungrouped = [f"task-{i}" for i in range(40)]

    # Act
    by_task = paired_bootstrap_gap(a, b, groups=grouped, seed=3)
    by_item = paired_bootstrap_gap(a, b, groups=ungrouped, seed=3)

    # Assert
    assert (by_task.ci_high - by_task.ci_low) > (by_item.ci_high - by_item.ci_low)


def test_the_default_resample_count_is_the_preregistered_one():
    # Arrange / Act / Assert
    assert BOOTSTRAP_RESAMPLES == 10_000


def test_mismatched_arms_are_refused():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="same length"):
        paired_bootstrap_gap([True], [True, False], groups=["a"], seed=1)


def test_an_empty_sample_is_refused_by_the_bootstrap():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="empty"):
        paired_bootstrap_gap([], [], groups=[], seed=1)


def test_a_non_positive_m_is_refused():
    with pytest.raises(ValueError, match="m must be positive"):
        recall_at([(1,)], [1], 0)


def test_recall_over_an_empty_sample_is_refused():
    with pytest.raises(ValueError, match="empty"):
        recall_at([], [], 1)


def test_a_narrower_confidence_level_gives_a_narrower_interval():
    # Arrange
    a = [True] * 12 + [False] * 8
    b = [True] * 4 + [False] * 16
    groups = [f"t{i // 2}" for i in range(20)]

    # Act
    wide = paired_bootstrap_gap(a, b, groups=groups, seed=1, resamples=500)
    narrow = paired_bootstrap_gap(a, b, groups=groups, seed=1, resamples=500, conf=0.80)

    # Assert
    assert (narrow.ci_high - narrow.ci_low) <= (wide.ci_high - wide.ci_low)


def test_an_interval_entirely_above_zero_is_reported_as_such():
    # Arrange / Act
    gap = paired_bootstrap_gap([True] * 4, [False] * 4, groups=list("abcd"), seed=1)

    # Assert
    assert gap.excludes_zero_above is True
