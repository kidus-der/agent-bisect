"""Blame results on disk, in the shape the dashboard's repository reads."""

from __future__ import annotations

import json

import pytest
from agent_bisect.attribution.blame_store import (
    BLAME_SCHEMA_VERSION,
    blame_document,
    blame_path,
    list_blamed_runs,
    load_blame,
    save_blame,
)
from agent_bisect.attribution.estimate import ArmResult, RunEstimate, StepEffect
from agent_bisect.attribution.judge_view import JudgeVerdict, Protocol, RankedStep
from agent_bisect.attribution.search import BlameConfig, BlameResult, RerunRecord


def _verdict(protocol: Protocol = "all_at_once") -> JudgeVerdict:
    return JudgeVerdict(
        item_id="item-1",
        protocol=protocol,
        decisive_step=5,
        ranking=(
            RankedStep(step=5, rank=1, score=0.9, rationale="wrong value"),
            RankedStep(step=3, rank=2, score=0.4, rationale="maybe"),
        ),
        rationale="the lookup was wrong",
        calls=1,
    )


def _estimate() -> RunEstimate:
    effect = StepEffect(
        step=5,
        treated=ArmResult(14, 16),
        control=ArmResult(1, 16),
        effect=0.8125,
        ci_low=0.55,
        ci_high=0.94,
        n_batches=4,
        stop_reason="blameworthy",
        decision_conf=0.95,
        decision_ci_low=0.5,
    )
    return RunEstimate(
        step_effects=(effect,),
        blamed_step=5,
        control_mode="shared",
        control_fork_step=3,
        treated_reruns=16,
        control_reruns=16,
        sampler_calls=5,
    )


def _result(**overrides) -> BlameResult:
    defaults = dict(
        item_id="item-1",
        run_id="run-1",
        method="bisect",
        blamed_step=5,
        estimate=_estimate(),
        reruns=(
            RerunRecord("run-1-t5-abc", "treated", 5, 11, True, 12, 9),
            RerunRecord("run-1-c3-def", "control", 3, 12, False, 12, 9),
        ),
        judge=_verdict(),
        shortlist=(5, 3),
        tested_steps=(5, 3),
        interventions={5: "truthful_tool_result", 3: "resample"},
        untestable=(),
        judge_calls=1,
        replay_calls=18,
        config=BlameConfig(),
    )
    defaults.update(overrides)
    return BlameResult(**defaults)  # type: ignore[arg-type]


def test_a_saved_result_round_trips(tmp_path):
    # Arrange
    result = _result()

    # Act
    save_blame(tmp_path, result)
    loaded = load_blame(tmp_path, "run-1")

    # Assert
    assert loaded["blamed_step"] == 5
    assert loaded["run_id"] == "run-1"


def test_the_document_carries_the_estimator_config_the_dashboard_needs(tmp_path):
    # Arrange / Act
    document = blame_document(_result())

    # Assert
    config = document["estimate"]["config"]
    assert set(config) == {
        "delta", "batch", "max_n", "conf", "efficacy_boundary", "control_mode", "shortlist_m",
    }
    assert config["delta"] == 0.10
    assert config["shortlist_m"] == 3


def test_every_individual_rerun_is_in_the_document(tmp_path):
    # Arrange / Act
    document = blame_document(_result())

    # Assert
    assert [row["rerun_id"] for row in document["reruns"]] == ["run-1-t5-abc", "run-1-c3-def"]
    assert document["reruns"][0]["arm"] == "treated"


def test_the_step_effects_keep_their_intervals_and_stop_reasons():
    # Arrange / Act
    document = blame_document(_result())

    # Assert
    effect = document["estimate"]["step_effects"][0]
    assert effect["ci_low"] == 0.55
    assert effect["stop_reason"] == "blameworthy"
    assert effect["treated"] == {"successes": 14, "n": 16}


def test_the_judge_panel_holds_both_protocols_when_both_ran():
    # Arrange / Act
    document = blame_document(_result(), step_by_step=_verdict("step_by_step"))

    # Assert
    assert [entry["step"] for entry in document["judge"]["all_at_once"]] == [5, 3]
    assert [entry["step"] for entry in document["judge"]["step_by_step"]] == [5, 3]


def test_the_step_by_step_side_is_empty_when_that_protocol_did_not_run():
    # Arrange / Act
    document = blame_document(_result())

    # Assert
    assert document["judge"]["step_by_step"] == []


def test_the_cost_is_split_between_judge_and_replay():
    # Arrange / Act
    document = blame_document(_result())

    # Assert
    assert document["cost"] == {"judge_calls": 1, "replay_calls": 18, "total_calls": 19}


def test_a_judge_that_could_not_answer_is_recorded_as_such():
    # Arrange
    failed = JudgeVerdict(
        item_id="item-1", protocol="all_at_once", decisive_step=None, ranking=(),
        rationale="", calls=2, parse_failed=True, failure_reason="no JSON object",
    )

    # Act
    document = blame_document(_result(estimate=None, reruns=(), judge=failed, blamed_step=None))

    # Assert
    assert document["estimate"] is None
    assert document["judge_parse_failed"] is True
    assert document["judge_failure_reason"] == "no JSON object"


def test_the_document_carries_a_schema_version():
    # Arrange / Act / Assert
    assert blame_document(_result())["schema_version"] == BLAME_SCHEMA_VERSION


def test_the_document_is_json_serialisable_and_byte_stable(tmp_path):
    # Arrange
    result = _result()

    # Act
    save_blame(tmp_path, result)
    first = blame_path(tmp_path, "run-1").read_bytes()
    save_blame(tmp_path, result)
    second = blame_path(tmp_path, "run-1").read_bytes()

    # Assert
    assert first == second
    assert json.loads(first)["method"] == "bisect"


def test_saving_two_methods_for_one_run_keeps_them_apart(tmp_path):
    # Arrange / Act
    save_blame(tmp_path, _result())
    save_blame(tmp_path, _result(method="rerun_live", config=BlameConfig(
        prefix_tools="rerun_live", unsafe_positional=True, method="rerun_live")))

    # Assert
    assert load_blame(tmp_path, "run-1")["method"] == "bisect"
    assert load_blame(tmp_path, "run-1", method="rerun_live")["method"] == "rerun_live"


def test_listing_names_every_run_with_a_primary_result(tmp_path):
    # Arrange
    save_blame(tmp_path, _result())
    save_blame(tmp_path, _result(run_id="run-2"))
    save_blame(tmp_path, _result(method="no_control", config=BlameConfig(
        control_mode="none", method="no_control")))

    # Act
    runs = list_blamed_runs(tmp_path)

    # Assert
    assert runs == ("run-1", "run-2")


def test_loading_a_run_that_was_never_blamed_raises(tmp_path):
    # Arrange / Act / Assert
    with pytest.raises(FileNotFoundError):
        load_blame(tmp_path, "nope")


# ---- reading a store that is empty or partial ----


def test_listing_a_directory_that_has_no_results_is_empty(tmp_path):
    # Arrange / Act / Assert
    assert list_blamed_runs(tmp_path / "nothing") == ()


def test_load_all_returns_only_the_methods_that_were_run(tmp_path):
    # Arrange
    from agent_bisect.attribution.blame_store import load_all

    save_blame(tmp_path, _result())
    save_blame(tmp_path, _result(method="no_control", config=BlameConfig(
        control_mode="none", method="no_control")))

    # Act
    loaded = load_all(tmp_path, ["bisect", "no_control", "rerun_live"])

    # Assert
    assert set(loaded) == {("run-1", "bisect"), ("run-1", "no_control")}


def test_load_all_over_an_empty_store_is_empty(tmp_path):
    # Arrange
    from agent_bisect.attribution.blame_store import load_all

    # Act / Assert
    assert load_all(tmp_path, ["bisect"]) == {}
