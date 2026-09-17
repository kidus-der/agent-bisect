"""P5's outputs: committed, payload-free, byte-stable, and replayable."""

from __future__ import annotations

import json

import pytest
from agent_bisect.bench.evaluate import ScoredItem
from agent_bisect.bench.results import (
    ITEMS_JSON,
    SUMMARY_JSON,
    item_rows,
    read_outcome_rows,
    write_results,
)


def _score(item_id="item-1", method="bisect", correct=True) -> ScoredItem:
    return ScoredItem(
        item_id=item_id,
        run_id="run-1",
        task_group="airline:1",
        domain="airline",
        split="test",
        fault_type="wrong_value",
        position_bucket="middle",
        planted_step=4,
        method=method,  # type: ignore[arg-type]
        predicted_step=4 if correct else None,
        verdict="exact" if correct else "none",
        correct=correct,
        ranking=(4, 2),
        shortlist=(4, 2),
        judge_calls=1,
        replay_calls=120,
        reruns=12,
        parse_failed=False,
        note="",
    )


def _rows():
    return [
        {"item_id": "item-1", "method": "bisect", "predicted_step": 4,
         "ranking": [4, 2], "total_calls": 121},
        {"item_id": "item-1", "method": "judge_all_at_once", "predicted_step": 2,
         "ranking": [2], "total_calls": 1},
    ]


def _report():
    return {
        "config": {"split": "test", "n_items": 1},
        "methods": [{"method": "bisect", "accuracy": {"value": 1.0}}],
        "gap": {"value": 1.0, "ci_low": 0.5, "ci_high": 1.0},
        "recall": {},
        "heatmap": [],
        "by_position": [],
        "sankey": [],
        "flaky_ablation": None,
        "failures": [{"item_id": "item-9"}],
        "cost_curve": [{"n": 16, "m": 3}],
    }


def _write(tmp_path, scores=None):
    return write_results(
        scores=scores or [_score()],
        outcome_rows=_rows(),
        report=_report(),
        runs_dir=tmp_path / "runs" / "p5",
        results_dir=tmp_path / "data" / "results",
    )


def test_every_output_is_written(tmp_path):
    # Arrange / Act
    written = _write(tmp_path)

    # Assert
    assert written.outcomes.exists()
    assert written.report.exists()
    assert written.summary.exists()
    assert written.items.exists()


def test_the_committed_summary_keeps_the_numbers_a_gate_needs(tmp_path):
    # Arrange / Act
    written = _write(tmp_path)
    summary = json.loads(written.summary.read_text())

    # Assert
    assert summary["gap"]["ci_low"] == 0.5
    assert summary["config"]["split"] == "test"


def test_the_committed_summary_leaves_the_bulky_parts_in_the_big_file(tmp_path):
    # Arrange / Act
    written = _write(tmp_path)
    summary = json.loads(written.summary.read_text())
    report = json.loads(written.report.read_text())

    # Assert
    assert "failures" not in summary
    assert "cost_curve" not in summary
    assert report["failures"] == [{"item_id": "item-9"}]


def test_the_item_table_carries_the_label_the_answer_and_the_cost(tmp_path):
    # Arrange / Act
    rows = item_rows([_score()])

    # Assert
    assert rows[0]["planted_step"] == 4
    assert rows[0]["predicted_step"] == 4
    assert rows[0]["total_calls"] == 121
    assert rows[0]["shortlist_hit"] is True


def test_the_item_table_carries_no_payload(tmp_path):
    # Arrange / Act
    rows = item_rows([_score()])

    # Assert: no trajectory, no tool result, no rationale
    assert set(rows[0]) == {
        "item_id", "run_id", "task_group", "domain", "split", "fault_type",
        "position_bucket", "planted_step", "method", "predicted_step", "verdict",
        "correct", "shortlist_hit", "judge_calls", "replay_calls", "total_calls",
        "reruns", "parse_failed",
    }


def test_the_item_table_is_sorted_so_a_diff_means_a_number_changed(tmp_path):
    # Arrange
    scores = [_score(method="judge_all_at_once"), _score(method="bisect")]

    # Act
    rows = item_rows(scores)

    # Assert
    assert [row["method"] for row in rows] == ["bisect", "judge_all_at_once"]


def test_writing_twice_produces_byte_identical_files(tmp_path):
    # Arrange
    first = _write(tmp_path).summary.read_bytes()

    # Act
    second = _write(tmp_path).summary.read_bytes()

    # Assert
    assert first == second


def test_the_stored_outcomes_can_be_read_back_for_make_reproduce(tmp_path):
    # Arrange
    written = _write(tmp_path)

    # Act
    rows = read_outcome_rows(written.outcomes.parent)

    # Assert
    assert rows == _rows()


def test_reading_outcomes_that_were_never_written_says_what_to_run(tmp_path):
    # Arrange / Act / Assert
    with pytest.raises(FileNotFoundError, match="bisect eval"):
        read_outcome_rows(tmp_path / "empty")


def test_the_parquet_copy_is_written_beside_the_json(tmp_path):
    # Arrange / Act
    written = _write(tmp_path)

    # Assert
    assert written.parquet is not None
    assert written.parquet.exists()


def test_the_results_directories_are_created_if_missing(tmp_path):
    # Arrange
    target = tmp_path / "deep" / "nested"

    # Act
    written = write_results(
        scores=[_score()], outcome_rows=_rows(), report=_report(),
        runs_dir=target / "runs", results_dir=target / "results",
    )

    # Assert
    assert written.summary.name == SUMMARY_JSON
    assert written.items.name == ITEMS_JSON
