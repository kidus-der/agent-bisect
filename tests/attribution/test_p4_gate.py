"""The P4 gate script: determinism, accounting, and the pass/fail criteria."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

# `scripts/` is a script directory, not an installed package, so it only joins
# sys.path at runtime (above) -- a static checker cannot resolve it from here.
from gates.p4 import (  # type: ignore[reportMissingImports]  # noqa: E402
    COVERAGE_WINDOW,
    MIN_FOUND_RATE,
    POWER_CONTROL_RATES,
    POWER_TREATED_RATES,
    classify_outcome,
    detection_power,
    evaluate_criteria,
    evaluate_run,
    format_power_table,
    format_report,
    main,
    run_gate,
    write_report,
)

SMALL_SAMPLE = 8


@pytest.mark.parametrize(
    ("blamed", "planted", "expected"),
    [(7, 7, "found"), (3, 7, "earlier"), (9, 7, "later"), (None, 7, "none")],
)
def test_a_blame_is_classified_against_the_planted_step(
    blamed: int | None, planted: int, expected: str
):
    assert classify_outcome(blamed, planted) == expected


def test_both_criteria_pass_when_the_numbers_sit_inside_their_windows():
    criteria = evaluate_criteria(found_rate=0.97, coverage_fixed=0.95)

    assert all(criterion.passed for criterion in criteria)


@pytest.mark.parametrize("found_rate", [0.0, 0.5, MIN_FOUND_RATE - 1e-9])
def test_the_found_rate_criterion_fails_below_the_pre_registered_bar(found_rate: float):
    found, _ = evaluate_criteria(found_rate=found_rate, coverage_fixed=0.95)

    assert not found.passed


@pytest.mark.parametrize("coverage", [COVERAGE_WINDOW[0] - 1e-9, COVERAGE_WINDOW[1] + 1e-9, 1.0])
def test_the_coverage_criterion_fails_outside_the_pre_registered_window(coverage: float):
    _, coverage_criterion = evaluate_criteria(found_rate=0.99, coverage_fixed=coverage)

    assert not coverage_criterion.passed


def test_the_gate_report_is_identical_when_computed_twice_from_one_master_seed():
    first = run_gate(n_runs=SMALL_SAMPLE, master_seed=99)
    second = run_gate(n_runs=SMALL_SAMPLE, master_seed=99)

    assert first.to_dict() == second.to_dict()


def test_a_different_master_seed_gives_a_different_report():
    first = run_gate(n_runs=SMALL_SAMPLE, master_seed=99)
    second = run_gate(n_runs=SMALL_SAMPLE, master_seed=100)

    assert first.to_dict() != second.to_dict()


def test_every_run_lands_in_exactly_one_bucket_of_the_breakdown():
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)

    assert sum(report.outcome_counts.values()) == SMALL_SAMPLE
    assert report.outcome_counts["found"] == report.n_found


def test_the_report_only_contains_types_that_survive_a_json_round_trip():
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)

    assert json.loads(json.dumps(report.to_dict())) == report.to_dict()


def test_writing_the_report_creates_the_json_file_and_its_parent_directory(tmp_path: Path):
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)
    destination = tmp_path / "nested" / "gate.json"

    write_report(report, destination)

    assert json.loads(destination.read_text())["n_runs"] == SMALL_SAMPLE


def test_the_fixed_design_always_spends_the_full_budget_on_every_step():
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)

    assert report.mean_reruns_fixed > report.mean_reruns_sequential
    assert report.rerun_saving > 0.0


def test_the_report_carries_the_fixed_design_diagnosis_alongside_the_gated_numbers():
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)

    assert sum(report.outcome_counts_fixed.values()) == SMALL_SAMPLE
    assert report.n_found_fixed == report.outcome_counts_fixed["found"]
    assert report.to_dict()["diagnosis_report_only"]["planted_step_found_fixed_n16"]["count"] == (
        report.n_found_fixed
    )


def test_the_null_step_flag_rate_counts_only_steps_before_the_planted_one():
    from agent_bisect.attribution.fakes import sample_run_specs

    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)
    expected = sum(spec.planted_step - 1 for spec in sample_run_specs(SMALL_SAMPLE, master_seed=5))

    assert report.null_step_counts[0] == expected
    assert 0.0 <= report.null_step_flag_rate_sequential <= 1.0


def test_the_exit_code_follows_the_verdict_and_the_json_lands_where_asked(tmp_path: Path):
    # Arrange
    destination = tmp_path / "gate.json"
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)

    # Act
    exit_code = main(["--runs", str(SMALL_SAMPLE), "--seed", "5", "--out", str(destination)])

    # Assert
    assert exit_code == (0 if report.passed else 1)
    assert json.loads(destination.read_text()) == report.to_dict()


def test_the_printed_report_states_a_verdict_for_every_criterion():
    report = run_gate(n_runs=SMALL_SAMPLE, master_seed=5)

    text = format_report(report)

    assert text.count("[PASS]") + text.count("[FAIL]") == len(report.criteria)
    assert "RESULT:" in text


def test_one_run_reports_a_coverage_count_for_every_step_it_tested():
    from agent_bisect.attribution.fakes import sample_run_specs

    spec = sample_run_specs(1, master_seed=5)[0]

    outcome = evaluate_run(spec, index=0, master_seed=5)

    assert outcome.fixed_tested == spec.n_steps
    assert outcome.sequential_tested == spec.n_steps
    assert 0 <= outcome.sequential_covered <= outcome.sequential_tested


def test_detection_power_is_a_probability_for_every_tabulated_cell():
    for control in POWER_CONTROL_RATES:
        for treated in POWER_TREATED_RATES:
            assert 0.0 <= detection_power(treated, control) <= 1.0


def test_detection_power_rises_with_the_treated_rate():
    powers = [detection_power(treated, 0.10) for treated in POWER_TREATED_RATES]

    assert powers == sorted(powers)


def test_detection_power_falls_as_the_control_rate_rises():
    powers = [detection_power(0.70, control) for control in POWER_CONTROL_RATES]

    assert powers == sorted(powers, reverse=True)


def test_an_effect_that_cannot_be_missed_is_detected_with_certainty():
    assert detection_power(1.0, 0.0) == pytest.approx(1.0)


def test_the_stricter_obf_level_never_detects_more_than_the_nominal_one():
    from agent_bisect.attribution.estimate import OBF_CRITICAL_Z, confidence_for_z

    obf_conf = confidence_for_z(OBF_CRITICAL_Z[-1])
    for control in POWER_CONTROL_RATES:
        for treated in POWER_TREATED_RATES:
            assert detection_power(treated, control, conf=obf_conf) <= detection_power(
                treated, control
            )


def test_the_enumeration_covers_the_whole_probability_mass():
    # Power at a delta below every achievable bound must be the total mass, 1.
    assert detection_power(0.7, 0.1, delta=-1.0) == pytest.approx(1.0, abs=1e-12)


def test_the_power_table_names_every_rate_it_tabulates():
    table = format_power_table()

    for treated in POWER_TREATED_RATES:
        assert f"treated {treated:.2f}" in table
    for control in POWER_CONTROL_RATES:
        assert f"{control:.2f} |" in table


def test_the_power_table_flag_exits_zero_and_writes_no_report(tmp_path: Path):
    destination = tmp_path / "unwanted.json"

    exit_code = main(["--power-table", "--out", str(destination)])

    assert exit_code == 0
    assert not destination.exists()
