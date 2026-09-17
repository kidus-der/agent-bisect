"""The P6 gate: e2e, axe, Lighthouse, design score and screenshots, each read
from evidence already on disk rather than re-run as a side effect of grading.
"""

from __future__ import annotations

import json

from scripts.gates.p6 import (
    MIN_ACCESSIBILITY,
    MIN_PERFORMANCE,
    REQUIRED_SCREENSHOTS,
    check_axe,
    check_design_scores,
    check_e2e,
    check_lighthouse,
    check_screenshots,
    run_gate,
    write_report,
)


def _spec(title: str, *, status: str = "expected") -> dict:
    return {"title": title, "tests": [{"status": status}]}


def _e2e_report(specs: list[dict], *, unexpected: int = 0, flaky: int = 0) -> dict:
    expected = sum(1 for spec in specs for test in spec["tests"] if test["status"] == "expected")
    return {
        "suites": [{"title": "overview.spec.ts", "specs": specs}],
        "stats": {"expected": expected, "unexpected": unexpected, "flaky": flaky, "skipped": 0},
    }


def _write(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_e2e_passes_when_every_spec_is_expected(tmp_path):
    report = tmp_path / "e2e-report.json"
    _write(report, _e2e_report([_spec("loads"), _spec("no serious or critical axe violations")]))

    criterion = check_e2e(report)

    assert criterion.passed
    assert "2/2 passed" in criterion.detail


def test_e2e_fails_on_an_unexpected_result(tmp_path):
    report = tmp_path / "e2e-report.json"
    _write(report, _e2e_report([_spec("loads")], unexpected=1))

    criterion = check_e2e(report)

    assert not criterion.passed


def test_e2e_fails_when_the_report_is_missing(tmp_path):
    criterion = check_e2e(tmp_path / "nope.json")

    assert not criterion.passed
    assert "no readable report" in criterion.detail


def test_axe_counts_only_axe_titled_specs_and_requires_all_passing(tmp_path):
    report = tmp_path / "e2e-report.json"
    _write(
        report,
        _e2e_report(
            [
                _spec("Overview has no serious or critical axe violations (dark)"),
                _spec("Overview has no serious or critical axe violations (light)"),
                _spec("an unrelated behavioural test"),
            ]
        ),
    )

    criterion = check_axe(report)

    assert criterion.passed
    assert criterion.data["axe_checks"] == 2


def test_axe_fails_when_a_violation_check_did_not_pass(tmp_path):
    report = tmp_path / "e2e-report.json"
    specs = [_spec("Runs has no serious or critical axe violations (dark)", status="unexpected")]
    payload = _e2e_report(specs)
    # An unexpected result is still counted in `stats.unexpected`, independent of criterion 1.
    payload["stats"]["unexpected"] = 1
    _write(report, payload)

    criterion = check_axe(report)

    assert not criterion.passed
    assert criterion.data["failing"]


def _lighthouse_report(performance: float, accessibility: float) -> dict:
    return {
        "categories": {
            "performance": {"score": performance},
            "accessibility": {"score": accessibility},
        }
    }


def test_lighthouse_passes_on_the_median_of_three_runs(tmp_path):
    for index, (perf, a11y) in enumerate([(0.94, 0.98), (0.94, 0.98), (0.95, 0.98)], start=1):
        _write(tmp_path / f"overview-{index}.report.json", _lighthouse_report(perf, a11y))

    criterion = check_lighthouse(tmp_path, "overview")

    assert criterion.passed
    assert criterion.data["performance_median"] == 94.0
    assert criterion.data["accessibility_median"] == 98.0


def test_lighthouse_fails_below_either_threshold(tmp_path):
    for index in (1, 2, 3):
        _write(tmp_path / f"run-detail-{index}.report.json", _lighthouse_report(0.89, 1.0))

    criterion = check_lighthouse(tmp_path, "run-detail")

    assert not criterion.passed
    assert f"need >= {MIN_PERFORMANCE:.0f}" in criterion.detail


def test_lighthouse_accessibility_threshold_is_stricter_than_performance():
    assert MIN_ACCESSIBILITY > MIN_PERFORMANCE


def test_lighthouse_fails_with_no_reports(tmp_path):
    criterion = check_lighthouse(tmp_path, "overview")

    assert not criterion.passed


REVIEW_LOG_ALL_AT_BAR = """# log

### Final scores

| Page | Score | At the bar | Last scored |
|---|---|---|---|
| Overview | **8.6** | yes | round 5 |
| Runs | **8.5** | yes | round 4 |
"""

REVIEW_LOG_ONE_MISS = """# log

### Final scores

| Page | Score | At the bar | Last scored |
|---|---|---|---|
| Run detail | **8.7** | yes | round 3 |
| PR checks | **8.4** | no | round 6 |
"""


def test_design_scores_pass_when_every_page_is_at_the_bar(tmp_path):
    log = tmp_path / "review-log.md"
    log.write_text(REVIEW_LOG_ALL_AT_BAR)

    criterion = check_design_scores(log)

    assert criterion.passed
    assert len(criterion.data["scores"]) == 2


def test_design_scores_report_a_miss_honestly_rather_than_rounding_up(tmp_path):
    log = tmp_path / "review-log.md"
    log.write_text(REVIEW_LOG_ONE_MISS)

    criterion = check_design_scores(log)

    assert not criterion.passed
    assert "PR checks 8.4" in criterion.detail


def test_design_scores_fail_when_the_table_is_missing(tmp_path):
    log = tmp_path / "review-log.md"
    log.write_text("# log\n\nnothing here.\n")

    criterion = check_design_scores(log)

    assert not criterion.passed


def test_screenshots_pass_when_every_curated_file_exists(tmp_path):
    for name in REQUIRED_SCREENSHOTS:
        (tmp_path / name).write_bytes(b"\x89PNG")

    criterion = check_screenshots(tmp_path)

    assert criterion.passed


def test_screenshots_name_what_is_missing(tmp_path):
    for name in REQUIRED_SCREENSHOTS[:-1]:
        (tmp_path / name).write_bytes(b"\x89PNG")

    criterion = check_screenshots(tmp_path)

    assert not criterion.passed
    assert REQUIRED_SCREENSHOTS[-1] in criterion.data["missing"]


def test_run_gate_is_failed_overall_when_one_criterion_is_failed(tmp_path):
    runs_dir = tmp_path / "runs" / "p6"
    _write(
        runs_dir / "e2e-report.json",
        _e2e_report([_spec("no serious or critical axe violations")]),
    )
    lighthouse_dir = runs_dir / "lighthouse"
    for page in ("overview", "run-detail"):
        for index in (1, 2, 3):
            _write(lighthouse_dir / f"{page}-{index}.report.json", _lighthouse_report(0.95, 0.98))
    review_log = tmp_path / "review-log.md"
    review_log.write_text(REVIEW_LOG_ONE_MISS)
    screenshots_dir = tmp_path / "final"
    screenshots_dir.mkdir()
    for name in REQUIRED_SCREENSHOTS:
        (screenshots_dir / name).write_bytes(b"\x89PNG")

    criteria = run_gate(runs_dir, review_log, screenshots_dir)

    assert any(not c.passed for c in criteria)
    assert any(c.passed for c in criteria)

    report_path = write_report(runs_dir, criteria)
    written = json.loads(report_path.read_text())
    assert written["gate"] == "P6"
    assert written["passed"] is False
    assert {c["name"] for c in written["criteria"]} == {c.name for c in criteria}
