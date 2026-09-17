"""`gate.comment`: the sticky PR comment's four shapes."""

from __future__ import annotations

from agent_bisect.gate.comment import DecisiveStepSummary, GateReport, render_comment
from agent_bisect.gate.stats import GateComparison


def _clean() -> GateReport:
    return GateReport(
        suite="demo",
        scenario_count=8,
        runs_per_scenario=4,
        comparison=GateComparison(head_passes=29, head_n=32, base_passes=29, base_n=32),
        decisive=None,
        total_calls=0,
    )


def _regressed(decisive: DecisiveStepSummary | None) -> GateReport:
    return GateReport(
        suite="demo",
        scenario_count=8,
        runs_per_scenario=4,
        comparison=GateComparison(head_passes=9, head_n=32, base_passes=29, base_n=32),
        decisive=decisive,
        total_calls=212,
    )


def _decisive() -> DecisiveStepSummary:
    return DecisiveStepSummary(
        step=2,
        actor="tool",
        tool_name="get_users",
        effect=0.75,
        ci_low=0.38,
        ci_high=0.81,
        n=16,
        changed_lines=(
            "- slip_probability: 0.10",
            "+ slip_probability: 0.90",
        ),
        caused_by="demo/agent_policy.yaml L23-L26 (this PR)",
        sharing_failures=3,
        total_new_failures=4,
    )


def test_a_clean_comment_says_no_regression():
    comment = render_comment(_clean())

    assert "unchanged" in comment
    assert "base 0.91" in comment
    assert "head 0.91" in comment
    assert "bisect serve" in comment


def test_a_regressed_comment_with_a_decisive_step_matches_the_brief_shape():
    comment = render_comment(_regressed(_decisive()))

    assert "agent regression detected" in comment
    assert "decisive step      step 2 · tool -> get_users" in comment
    assert "+0.75" in comment
    assert "95% CI [0.38, 0.81]" in comment
    assert "N = 16" in comment
    assert "- slip_probability: 0.10" in comment
    assert "+ slip_probability: 0.90" in comment
    assert "caused by: demo/agent_policy.yaml L23-L26 (this PR)" in comment
    assert "3 of 4 new failures share this step" in comment
    assert "212 calls" in comment


def test_a_regressed_comment_without_a_confirmed_step_says_so():
    comment = render_comment(_regressed(None))

    assert "agent regression detected" in comment
    assert "none of the new failures" in comment


def test_an_error_comment_carries_the_error_text():
    report = GateReport(
        suite="demo", scenario_count=8, runs_per_scenario=4,
        comparison=GateComparison(head_passes=1, head_n=1, base_passes=1, base_n=1),
        decisive=None, total_calls=0, error="base ref does not resolve",
    )

    comment = render_comment(report)

    assert "gate error" in comment
    assert "base ref does not resolve" in comment


def test_the_p_value_is_rendered_to_three_significant_figures():
    comment = render_comment(_regressed(_decisive()))

    assert "p = " in comment
