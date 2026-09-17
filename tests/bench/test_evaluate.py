"""The P5 report: accuracy, the bootstrap gap, recall@m, breakdowns, failures."""

from __future__ import annotations

import pytest
from agent_bisect.bench.baselines import MethodOutcome
from agent_bisect.bench.evaluate import (
    build_report,
    score_outcomes,
)
from agent_bisect.bench.faults import FaultType
from agent_bisect.bench.manifest import DatasetItem, Split
from agent_bisect.bench.strata import PositionBucket


def _item(
    index: int, *, task: str, planted: int = 5,
    fault: FaultType = "wrong_value",
    position: PositionBucket = "middle",
    split: Split = "test",
) -> DatasetItem:
    return DatasetItem(
        item_id=f"item-{index}",
        domain="airline",
        task_id=task,
        split=split,
        base_run_id=f"base-{index}",
        base_pass_rate=1.0,
        run_id=f"run-{index}",
        faulted_pass_rate=0.0,
        planted_step=planted,
        position_bucket=position,
        fault_type=fault,
        mutation={},
        oracle={},
        intervention={},
        seeds=[1],
        n_reruns=4,
    )


def _outcome(index: int, method: str, predicted: int | None, *, ranking=(5, 1, 3),
             judge_calls=1, replay_calls=100) -> MethodOutcome:
    return MethodOutcome(
        item_id=f"item-{index}",
        run_id=f"run-{index}",
        method=method,  # type: ignore[arg-type]
        predicted_step=predicted,
        ranking=tuple(ranking),
        shortlist=tuple(ranking[:3]),
        judge_calls=judge_calls,
        replay_calls=replay_calls,
        reruns=replay_calls // 10,
        control_reruns=16,
        parse_failed=False,
    )


def _dataset(n: int = 6):
    return [_item(i, task=f"task-{i // 2}") for i in range(n)]


def _outcomes(bisect_hits: int, judge_hits: int, n: int = 6):
    outcomes = []
    for i in range(n):
        outcomes.append(_outcome(i, "bisect", 5 if i < bisect_hits else None))
        outcomes.append(
            _outcome(i, "judge_all_at_once", 5 if i < judge_hits else 9,
                     judge_calls=1, replay_calls=0)
        )
        outcomes.append(
            _outcome(i, "judge_step_by_step", 9, judge_calls=8, replay_calls=0)
        )
        outcomes.append(_outcome(i, "rerun_live", 5 if i < 2 else None))
        outcomes.append(_outcome(i, "no_control", 1))
    return outcomes


def _report(bisect_hits=5, judge_hits=2, n=6, **kwargs):
    scores = score_outcomes(_dataset(n), _outcomes(bisect_hits, judge_hits, n))
    return build_report(scores, split="test", seed=1, bootstrap_resamples=200, **kwargs)


# ---- scoring ----


def test_a_hit_is_exact_and_correct():
    # Arrange / Act
    scores = score_outcomes(_dataset(2), [_outcome(0, "bisect", 5), _outcome(1, "bisect", 5)])

    # Assert
    assert all(score.correct and score.verdict == "exact" for score in scores)


def test_blaming_nothing_is_wrong_and_labelled_none():
    # Arrange / Act
    scores = score_outcomes(_dataset(1), [_outcome(0, "bisect", None)])

    # Assert
    assert scores[0].correct is False
    assert scores[0].verdict == "none"


def test_an_outcome_without_a_label_is_refused_not_dropped():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="item-9"):
        score_outcomes(_dataset(1), [_outcome(9, "bisect", 5)])


def test_a_label_with_no_outcome_for_a_method_is_refused_not_dropped():
    # Arrange: two items, an outcome for only one of them
    with pytest.raises(ValueError, match="item-1"):
        score_outcomes(_dataset(2), [_outcome(0, "bisect", 5)])


def test_the_task_group_travels_with_every_score():
    # Arrange / Act
    scores = score_outcomes(_dataset(2), [_outcome(0, "bisect", 5), _outcome(1, "bisect", 5)])

    # Assert
    assert {score.task_group for score in scores} == {"airline:task-0"}


# ---- report ----


def test_every_method_gets_an_accuracy_with_an_interval():
    # Arrange / Act
    report = _report()

    # Assert
    for row in report["methods"]:
        assert row["accuracy"]["ci_low"] <= row["accuracy"]["value"] <= row["accuracy"]["ci_high"]


def test_the_gap_compares_bisect_with_the_better_of_the_two_judges():
    # Arrange: all-at-once gets 2/6, step-by-step gets 0/6
    report = _report(bisect_hits=5, judge_hits=2)

    # Assert
    assert report["gap"]["comparator"] == "judge_all_at_once"
    assert report["gap"]["value"] == pytest.approx(5 / 6 - 2 / 6)


def test_the_gap_carries_a_bootstrap_interval():
    # Arrange / Act
    report = _report()

    # Assert
    gap = report["gap"]
    assert gap["ci_low"] <= gap["value"] <= gap["ci_high"]
    assert gap["resamples"] == 200


def test_the_report_says_whether_the_gap_clears_fifteen_points():
    # Arrange / Act
    report = _report(bisect_hits=6, judge_hits=0)

    # Assert
    assert report["gap"]["points"] == pytest.approx(100.0)
    assert report["gap"]["clears_fifteen_points"] is True


def test_recall_is_reported_for_m_one_to_ten():
    # Arrange / Act
    report = _report()

    # Assert
    curve = report["recall"]["judge_all_at_once"]
    assert sorted(int(m) for m in curve) == list(range(1, 11))


def test_accuracy_is_broken_down_by_fault_type_and_method():
    # Arrange / Act
    report = _report()

    # Assert
    cells = report["heatmap"]
    assert {cell["fault_type"] for cell in cells} == {"wrong_value"}
    assert {cell["method"] for cell in cells} >= {"bisect", "judge_all_at_once"}
    assert all(cell["n"] > 0 for cell in cells)


def test_accuracy_is_broken_down_by_position_bucket():
    # Arrange / Act
    report = _report()

    # Assert
    assert {row["position"] for row in report["by_position"]} == {"middle"}


def test_the_sankey_counts_every_item_once_per_fault_type():
    # Arrange / Act
    report = _report(n=6)

    # Assert
    total = sum(flow["count"] for flow in report["sankey"])
    assert total == 6


def test_the_cost_is_reported_per_method_split_judge_and_replay():
    # Arrange / Act
    report = _report()

    # Assert
    row = next(r for r in report["methods"] if r["method"] == "bisect")
    assert row["mean_judge_calls"] == 1.0
    assert row["mean_replay_calls"] == 100.0
    assert row["mean_calls"] == 101.0


def test_the_judge_only_baselines_are_cheaper_than_bisect():
    # Arrange / Act
    report = _report()

    # Assert
    by_method = {row["method"]: row["mean_calls"] for row in report["methods"]}
    assert by_method["judge_all_at_once"] < by_method["bisect"]


def test_the_failure_cases_name_every_item_bisect_got_wrong():
    # Arrange: 5 of 6 hit, so exactly one failure
    report = _report(bisect_hits=5)

    # Assert
    assert len(report["failures"]) == 1
    assert report["failures"][0]["verdict"] == "none"


def test_a_failure_says_whether_the_shortlist_even_held_the_planted_step():
    # Arrange / Act
    report = _report(bisect_hits=5)

    # Assert
    assert report["failures"][0]["shortlist_hit"] is True


def test_the_report_records_the_configuration_it_was_produced_under():
    # Arrange / Act
    report = _report()

    # Assert
    config = report["config"]
    assert config["split"] == "test"
    assert config["seed"] == 1
    assert config["n_items"] == 6


def test_the_report_is_deterministic_for_the_same_inputs():
    # Arrange / Act
    first, second = _report(), _report()

    # Assert
    assert first == second


def test_the_flaky_comparison_is_reported_when_flaky_scores_are_supplied():
    # Arrange
    flaky = score_outcomes(_dataset(6), _outcomes(6, 2, 6))

    # Act
    report = _report(flaky_scores=flaky)

    # Assert
    ablation = report["flaky_ablation"]
    assert {arm["name"] for arm in ablation["arms"]} == {"snapshot", "no_snapshot"}
    assert "ci_low" in ablation["difference"]


def test_without_flaky_data_the_ablation_is_absent_rather_than_faked():
    # Arrange / Act
    report = _report()

    # Assert
    assert report["flaky_ablation"] is None


def test_a_split_with_no_items_is_refused():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="no items"):
        build_report((), split="test", seed=1)


def test_the_report_says_how_far_recall_was_actually_measured():
    # Arrange / Act
    report = _report()

    # Assert
    provenance = report["recall_provenance"]
    assert provenance["measured_to_m"] == 3
    assert provenance["beyond_is_judge_ranking_only"] is True
    assert "MEASURED" in provenance["note"]


def test_a_different_shortlist_size_moves_the_measured_boundary():
    # Arrange
    scores = score_outcomes(_dataset(6), _outcomes(5, 2, 6))

    # Act
    report = build_report(
        scores, split="test", seed=1, bootstrap_resamples=50, measured_to_m=1
    )

    # Assert
    assert report["recall_provenance"]["measured_to_m"] == 1
