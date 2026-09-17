"""The P5 gate: every criterion, and a missing input that fails rather than skips."""

from __future__ import annotations

import json

import pytest
from scripts.gates.p5 import (
    REQUIRED_POINTS,
    format_report,
    load_summary,
    main,
    run_gate,
)


def _summary(
    *,
    bisect=0.70,
    judge=0.40,
    gap_low=0.15,
    gap_high=0.45,
    flaky_low=0.10,
    flaky_high=0.40,
    split="test",
    with_flaky=True,
):
    document = {
        "config": {"split": split, "n_items": 80},
        "methods": [
            {"method": "bisect", "accuracy": {"value": bisect, "ci_low": 0.6, "ci_high": 0.8}},
            {
                "method": "judge_all_at_once",
                "accuracy": {"value": judge, "ci_low": 0.3, "ci_high": 0.5},
            },
        ],
        "gap": {
            "comparator": "judge_all_at_once",
            "value": bisect - judge,
            "ci_low": gap_low,
            "ci_high": gap_high,
            "resamples": 10_000,
        },
        "flaky_ablation": None,
        "integrity": {"bisect_unguarded_calls": 0},
    }
    if with_flaky:
        document["flaky_ablation"] = {
            "arms": [
                {"name": "snapshot", "accuracy": {"value": 0.72, "ci_low": 0.6, "ci_high": 0.8}},
                {
                    "name": "no_snapshot",
                    "accuracy": {"value": 0.45, "ci_low": 0.35, "ci_high": 0.55},
                },
            ],
            "difference": {
                "value": 0.27, "ci_low": flaky_low, "ci_high": flaky_high, "resamples": 10_000
            },
        }
    return document


def _names(criteria):
    return {criterion.name: criterion.passed for criterion in criteria}


# ---- criteria ----


def test_a_clean_result_passes_every_criterion():
    # Arrange / Act
    criteria = run_gate(_summary())

    # Assert
    assert all(criterion.passed for criterion in criteria)


def test_a_gap_below_fifteen_points_fails_the_accuracy_criterion():
    # Arrange: 10 points
    criteria = run_gate(_summary(bisect=0.50, judge=0.40))

    # Assert
    assert _names(criteria)["accuracy gap"] is False


def test_a_gap_of_exactly_fifteen_points_passes():
    # Arrange
    criteria = run_gate(_summary(bisect=0.55, judge=0.40))

    # Assert
    assert _names(criteria)["accuracy gap"] is True


def test_an_interval_touching_zero_fails():
    # Arrange
    criteria = run_gate(_summary(gap_low=0.0))

    # Assert
    assert _names(criteria)["gap interval"] is False


def test_an_interval_below_zero_fails():
    # Arrange
    criteria = run_gate(_summary(gap_low=-0.05))

    # Assert
    assert _names(criteria)["gap interval"] is False


def test_a_flaky_difference_that_could_be_zero_fails():
    # Arrange
    criteria = run_gate(_summary(flaky_low=-0.02))

    # Assert
    assert _names(criteria)["flaky ablation"] is False


def test_a_missing_flaky_ablation_fails_rather_than_being_skipped():
    # Arrange
    criteria = run_gate(_summary(with_flaky=False))

    # Assert
    assert _names(criteria)["flaky ablation"] is False


def test_a_dev_split_summary_cannot_satisfy_the_gate():
    # Arrange
    criteria = run_gate(_summary(split="dev"))

    # Assert
    assert _names(criteria)["split"] is False


def test_every_criterion_reports_the_numbers_that_decided_it():
    # Arrange / Act
    report = format_report(run_gate(_summary()))

    # Assert
    assert "0.700" in report
    assert f"{REQUIRED_POINTS:.0f}" in report
    assert "GATE PASS" in report


# ---- the command ----


def test_the_command_exits_zero_on_a_passing_summary(tmp_path, capsys):
    # Arrange
    path = tmp_path / "p5_summary.json"
    path.write_text(json.dumps(_summary()))

    # Act
    code = main(["--summary", str(path)])

    # Assert
    assert code == 0
    assert "GATE PASS" in capsys.readouterr().out


def test_the_command_exits_non_zero_on_a_failing_summary(tmp_path, capsys):
    # Arrange
    path = tmp_path / "p5_summary.json"
    path.write_text(json.dumps(_summary(bisect=0.42)))

    # Act
    code = main(["--summary", str(path)])

    # Assert
    assert code == 1
    assert "GATE FAIL" in capsys.readouterr().out


def test_a_missing_summary_fails_loudly_rather_than_passing_quietly(tmp_path, capsys):
    # Arrange / Act
    code = main(["--summary", str(tmp_path / "absent.json")])

    # Assert
    assert code == 1
    assert "GATE FAIL" in capsys.readouterr().out


def test_an_unreadable_summary_is_named_in_the_failure(tmp_path):
    # Arrange
    path = tmp_path / "broken.json"
    path.write_text("{not json")

    # Act
    result = load_summary(path)

    # Assert
    assert isinstance(result, str)
    assert "readable JSON" in result


def test_the_gate_never_writes_anything(tmp_path):
    # Arrange
    path = tmp_path / "p5_summary.json"
    path.write_text(json.dumps(_summary()))
    before = sorted(entry.name for entry in tmp_path.iterdir())

    # Act
    main(["--summary", str(path)])

    # Assert
    assert sorted(entry.name for entry in tmp_path.iterdir()) == before


def test_a_bisect_arm_that_ran_past_the_hash_guard_fails_the_gate():
    # Arrange
    summary = _summary()
    summary["integrity"]["bisect_unguarded_calls"] = 3

    # Act / Assert
    assert _names(run_gate(summary))["replay integrity"] is False


def test_a_summary_that_cannot_show_the_guard_was_on_fails_the_gate():
    # Arrange
    summary = _summary()
    del summary["integrity"]

    # Act / Assert
    assert _names(run_gate(summary))["replay integrity"] is False


@pytest.mark.parametrize(
    "criterion",
    ["split", "accuracy gap", "gap interval", "flaky ablation", "replay integrity"],
)
def test_all_four_criteria_are_always_reported(criterion):
    # Arrange / Act
    criteria = run_gate(_summary())

    # Assert
    assert criterion in _names(criteria)
