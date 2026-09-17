"""The P0 gate: re-checks every pre-registered threshold from the raw checkpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# `scripts/` is a script directory, not an installed package, so it only joins
# sys.path at runtime (above) -- a static checker cannot resolve it from here.
from gates.p0 import (  # type: ignore[reportMissingImports]  # noqa: E402
    evaluate_criteria,
    evaluate_doctor,
    evaluate_models_doc,
    evaluate_rate_limit,
    evidence_provenance,
    format_evidence,
    format_report,
    invariance_notes,
    load_probe_results,
    probed_models,
    recheck_agent_from_checkpoints,
)

MODELS = {
    "agent": "nvidia/nemotron-3-super-120b-a12b",
    "user_sim": "openai/gpt-oss-20b",
    "judge": "moonshotai/kimi-k3",
}


def _row(task_id: str, *, passed: bool, tool_calls: int = 10, invalid: int = 0) -> dict:
    return {
        "model": MODELS["agent"],
        "task_id": task_id,
        "reward": 1.0 if passed else 0.0,
        "passed": passed,
        "n_steps": 12,
        "n_agent_calls": 8,
        "n_user_calls": 4,
        "n_agent_tool_calls": tool_calls,
        "n_invalid_tool_calls": invalid,
        "invalid_reasons": [],
        "termination_reason": "agent_stop",
        "calls_used": 12,
        "wall_time_s": 30.0,
        "seed": 1,
        "mean_agent_latency_ms": 100.0,
        "n_empty_user_messages": 0,
        "error": None,
    }


def _write_probe(tmp_path: Path, rows: list[dict], model: str = MODELS["agent"]) -> Path:
    rows = [{**row, "model": model} for row in rows]
    directory = tmp_path / model.replace("/", "__")
    directory.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (directory / f"{row['task_id']}.json").write_text(json.dumps(row))
        (directory / f"{row['task_id']}.simulation.json").write_text("{}")
    return tmp_path


# ---- load_probe_results ----


def test_reads_every_checkpoint_and_ignores_the_simulation_siblings(tmp_path):
    _write_probe(tmp_path, [_row("0", passed=True), _row("1", passed=False)])

    rows = load_probe_results(tmp_path, MODELS["agent"])

    assert {r.task_id for r in rows} == {"0", "1"}


def test_returns_nothing_when_the_model_was_never_probed(tmp_path):
    assert load_probe_results(tmp_path, "never/probed") == []


# ---- the agent re-check ----


def test_recheck_passes_when_the_raw_checkpoints_meet_both_thresholds(tmp_path):
    rows = [_row(str(i), passed=i < 11) for i in range(20)]
    _write_probe(tmp_path, rows)

    criteria = recheck_agent_from_checkpoints(tmp_path, MODELS["agent"], n_tasks=20)

    assert all(c.passed for c in criteria), [c.detail for c in criteria]


def test_recheck_fails_when_fewer_than_the_required_tasks_were_run(tmp_path):
    _write_probe(tmp_path, [_row(str(i), passed=True) for i in range(5)])

    criteria = recheck_agent_from_checkpoints(tmp_path, MODELS["agent"], n_tasks=20)

    completeness = next(c for c in criteria if c.name == "probe_complete")
    assert completeness.passed is False
    assert "5" in completeness.detail


def test_recheck_fails_a_pass_rate_outside_the_window(tmp_path):
    _write_probe(tmp_path, [_row(str(i), passed=True) for i in range(20)])

    criteria = recheck_agent_from_checkpoints(tmp_path, MODELS["agent"], n_tasks=20)

    assert next(c for c in criteria if c.name == "airline_pass_rate").passed is False


def test_recheck_fails_a_tool_call_rate_below_the_floor(tmp_path):
    rows = [_row(str(i), passed=i < 11, tool_calls=10, invalid=1) for i in range(20)]
    _write_probe(tmp_path, rows)

    criteria = recheck_agent_from_checkpoints(tmp_path, MODELS["agent"], n_tasks=20)

    tool = next(c for c in criteria if c.name == "valid_tool_call_rate")
    assert tool.passed is False
    assert "0.900" in tool.detail


def test_recheck_is_independent_of_models_toml(tmp_path):
    """The gate must not take models.toml's word for its own numbers."""
    rows = [_row(str(i), passed=True) for i in range(20)]  # 100%, out of window
    _write_probe(tmp_path, rows)

    criteria = recheck_agent_from_checkpoints(tmp_path, MODELS["agent"], n_tasks=20)

    assert next(c for c in criteria if c.name == "airline_pass_rate").passed is False


# ---- doctor ----


def test_doctor_criterion_passes_when_every_check_passed():
    payload = [{"name": "nvidia_api_key", "passed": True, "detail": "found"}]

    assert evaluate_doctor(payload, exit_code=0).passed is True


def test_doctor_criterion_fails_and_names_the_failing_checks():
    payload = [
        {"name": "nvidia_api_key", "passed": True, "detail": "found"},
        {"name": "e2e_task_reward", "passed": False, "detail": "nope"},
    ]

    criterion = evaluate_doctor(payload, exit_code=1)

    assert criterion.passed is False
    assert "e2e_task_reward" in criterion.detail


def test_doctor_criterion_fails_on_a_nonzero_exit_even_if_checks_look_fine():
    payload = [{"name": "nvidia_api_key", "passed": True, "detail": "found"}]

    assert evaluate_doctor(payload, exit_code=2).passed is False


# ---- the measured rate limit must be written down ----


def test_rate_limit_criterion_requires_a_measurement_per_model(tmp_path):
    state = {"measured_rpm": {"a": 200, "b": 120}, "windows": [{"sent": 20}]}
    path = tmp_path / "rate_limit.json"
    path.write_text(json.dumps(state))

    criterion = evaluate_rate_limit(path)

    assert criterion.passed is True
    assert "2 model" in criterion.detail


def test_rate_limit_criterion_fails_when_nothing_was_measured(tmp_path):
    path = tmp_path / "rate_limit.json"
    path.write_text(json.dumps({"measured_rpm": {}, "windows": []}))

    assert evaluate_rate_limit(path).passed is False


def test_rate_limit_criterion_fails_when_the_file_is_absent(tmp_path):
    assert evaluate_rate_limit(tmp_path / "absent.json").passed is False


# ---- the decision document ----


def test_models_doc_criterion_requires_the_requests_per_minute_to_be_recorded(tmp_path):
    path = tmp_path / "models.md"
    path.write_text("# Models\n\n| Model | Measured rpm |\n|---|---|\n| a | 200 |\n")

    assert evaluate_models_doc(path, ["a"]).passed is True


def test_models_doc_criterion_fails_when_a_chosen_model_is_not_mentioned(tmp_path):
    path = tmp_path / "models.md"
    path.write_text("# Models\n\nmeasured requests/min: 200\n")

    criterion = evaluate_models_doc(path, ["nvidia/nemotron-3-super-120b-a12b"])

    assert criterion.passed is False
    assert "nemotron" in criterion.detail


def test_models_doc_criterion_fails_when_the_document_does_not_exist(tmp_path):
    assert evaluate_models_doc(tmp_path / "absent.md", ["a"]).passed is False


# ---- overall verdict and report ----


def test_overall_verdict_is_pass_only_when_every_criterion_passes(tmp_path):
    _write_probe(tmp_path, [_row(str(i), passed=i < 11) for i in range(20)])
    doc = tmp_path / "models.md"
    doc.write_text(f"{MODELS['agent']} {MODELS['user_sim']} {MODELS['judge']} 120 rpm")
    rate = tmp_path / "rate_limit.json"
    rate.write_text(json.dumps({"measured_rpm": {"a": 120}, "windows": [{"sent": 1}]}))

    criteria = evaluate_criteria(
        models_config=MODELS,
        doctor_payload=[{"name": "x", "passed": True, "detail": ""}],
        doctor_exit_code=0,
        probe_dir=tmp_path,
        rate_limit_path=rate,
        models_doc_path=doc,
        n_tasks=20,
    )

    assert all(c.passed for c in criteria), [c.detail for c in criteria if not c.passed]


def test_overall_verdict_fails_when_no_agent_was_chosen(tmp_path):
    criteria = evaluate_criteria(
        models_config=None,
        doctor_payload=[],
        doctor_exit_code=1,
        probe_dir=tmp_path,
        rate_limit_path=tmp_path / "absent.json",
        models_doc_path=tmp_path / "absent.md",
        n_tasks=20,
    )

    assert not all(c.passed for c in criteria)
    assert any("no agent chosen" in c.detail for c in criteria)


@pytest.mark.parametrize("passed,expected", [(True, "PASS"), (False, "FAILED")])
def test_report_states_the_verdict_and_every_criterion(passed, expected):
    from gates.p0 import Criterion  # type: ignore[reportMissingImports]

    report = format_report([Criterion("thing", passed, "because")], commit="abc123")

    assert expected in report
    assert "thing" in report and "because" in report
    assert "abc123" in report


# ---- evidence provenance and the invariance note ----


def test_provenance_names_the_files_that_produced_the_verdict():
    """HEAD in a shared tree is whatever another agent pushed last."""
    provenance = evidence_provenance()

    assert "scripts/gates/p0.py" in provenance
    assert "config/models.toml" in provenance
    assert "docs/decisions/models.md" in provenance


def test_the_evidence_file_records_the_provenance_not_just_head():
    from gates.p0 import Criterion  # type: ignore[reportMissingImports]

    report = format_evidence(
        [Criterion("thing", True, "because")],
        commit="deadbee",
        calls_per_model={"m": 3},
        provenance={"scripts/gates/p0.py": "abc1234 gate script"},
        notes=["a note"],
    )

    assert "abc1234 gate script" in report
    assert "scripts/gates/p0.py" in report
    assert "a note" in report


def test_probed_models_skips_the_user_sim_sanity_directory(tmp_path):
    (tmp_path / "nvidia__nemotron-3-super-120b-a12b").mkdir()
    (tmp_path / "nvidia__nemotron-3-super-120b-a12b#usersim-x").mkdir()

    assert probed_models(tmp_path) == ["nvidia/nemotron-3-super-120b-a12b"]


def test_a_complete_probe_says_no_task_could_have_changed_the_choice(tmp_path):
    _write_probe(tmp_path, [_row(str(i), passed=i < 11) for i in range(20)])

    notes = invariance_notes(tmp_path, n_tasks=20)

    assert any("completed all" in note for note in notes)


def test_an_unfinished_task_that_cannot_change_the_choice_is_called_invariant(tmp_path):
    """One candidate inside the window, one far outside it with a task missing."""
    _write_probe(tmp_path, [_row(str(i), passed=i < 11) for i in range(20)])
    outsider = [
        {**_row(str(i), passed=True), "model": "other/model"} for i in range(19)
    ]
    _write_probe(tmp_path, outsider, model="other/model")

    notes = invariance_notes(tmp_path, n_tasks=20)

    assert any("invariant" in note for note in notes)
    assert any("NOT invariant" not in note for note in notes)


def test_an_unfinished_task_that_could_flip_the_choice_is_reported_as_such(tmp_path):
    """`zzz` at 11/20 is the exact target; at 12/20 it ties `aaa` and loses on order.

    So the missing task genuinely decides the winner, and the gate has to say
    so rather than presenting one scoring convention as settled.
    """
    _write_probe(tmp_path, [_row(str(i), passed=i < 12) for i in range(20)], model="aaa/model")
    _write_probe(tmp_path, [_row(str(i), passed=i < 11) for i in range(19)], model="zzz/model")

    notes = invariance_notes(tmp_path, n_tasks=20)

    assert any("NOT invariant" in note for note in notes)
