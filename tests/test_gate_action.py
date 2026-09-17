"""`gate.action`'s pure decision logic: no worktree, no subprocess.

The subprocess/worktree plumbing (`run_demo_runner`, `run_blame_cli`,
`run_gate`) is exercised for real by `scripts/gates/p7.py`'s local layer;
here every function takes fixed JSON documents so a regression in the
comparison or blame-mapping logic fails fast, in milliseconds.
"""

from __future__ import annotations

from pathlib import Path

from agent_bisect.gate.action import (
    GateConfig,
    compare_suites,
    decisive_step_summary,
    diff_lines,
    new_failures,
    to_result_json,
)

REPO = Path(__file__).resolve().parents[1]


def _summary(scenarios: dict[str, list[bool]], *, rule_id: str = "use_correct_task_id") -> dict:
    return {
        "scenarios": [
            {
                "name": name,
                "rule_id": rule_id,
                "runs": [
                    {
                        "run_index": i, "passed": passed,
                        "run_id": f"demo-{name}-{i}", "faulted": False,
                    }
                    for i, passed in enumerate(runs)
                ],
            }
            for name, runs in scenarios.items()
        ]
    }


def test_identical_summaries_compare_as_no_regression():
    base = _summary({"a": [True, True, True, True], "b": [True, True, True, False]})
    head = _summary({"a": [True, True, True, True], "b": [True, True, True, False]})

    suite = compare_suites(base, head)

    assert suite.comparison.is_regression is False
    assert new_failures(suite) == []


def test_a_scenario_that_flips_from_pass_to_fail_is_a_new_failure():
    base = _summary({"a": [True, True, True, True]})
    head = _summary({"a": [True, False, True, True]})

    suite = compare_suites(base, head)
    failures = new_failures(suite)

    assert failures == [
        {
            "scenario_name": "a", "run_index": 1,
            "head_run_id": "demo-a-1", "base_run_id": "demo-a-1",
        }
    ]


def test_a_run_that_fails_on_both_sides_is_not_a_new_failure():
    base = _summary({"a": [True, False, True, True]})
    head = _summary({"a": [True, False, True, True]})

    suite = compare_suites(base, head)

    assert new_failures(suite) == []


def test_a_run_that_improves_is_not_a_new_failure():
    base = _summary({"a": [True, False, True, True]})
    head = _summary({"a": [True, True, True, True]})

    suite = compare_suites(base, head)

    assert new_failures(suite) == []


def test_a_large_reliable_drop_across_scenarios_is_flagged():
    base = _summary({f"s{i}": [True] * 4 for i in range(8)})
    head = _summary(
        {**{f"s{i}": [True] * 4 for i in range(6)}, "s6": [False] * 4, "s7": [False] * 4}
    )

    suite = compare_suites(base, head)

    assert suite.comparison.is_regression is True
    failures = new_failures(suite)
    assert {f["scenario_name"] for f in failures} == {"s6", "s7"}
    assert len(failures) == 8


def test_decisive_step_summary_picks_the_mode_and_counts_sharing_failures():
    blame_summaries = [
        {"blamed_step": 2, "scenario_name": "a"},
        {"blamed_step": 2, "scenario_name": "b"},
        {"blamed_step": 5, "scenario_name": "c"},
    ]

    decisive = decisive_step_summary(
        blame_summaries, total_new_failures=3,
        changed_files={"demo/agent_policy.yaml": ["- x", "+ y"]},
    )

    assert decisive is not None
    assert decisive.step == 2
    assert decisive.sharing_failures == 2
    assert decisive.total_new_failures == 3
    assert decisive.changed_lines == ("- x", "+ y")


def test_decisive_step_summary_breaks_ties_on_the_smaller_step():
    blame_summaries = [{"blamed_step": 5}, {"blamed_step": 2}]

    decisive = decisive_step_summary(blame_summaries, total_new_failures=2, changed_files={})

    assert decisive is not None
    assert decisive.step == 2
    assert decisive.sharing_failures == 1


def test_decisive_step_summary_is_none_when_nothing_was_confirmed():
    decisive = decisive_step_summary(
        [{"blamed_step": None}, {"blamed_step": None}], total_new_failures=2, changed_files={}
    )

    assert decisive is None


def test_to_result_json_carries_the_pool_and_the_comment():
    base = _summary({"a": [True, True]})
    head = _summary({"a": [False, False]})
    suite = compare_suites(base, head)
    config = GateConfig(repo=REPO, base="main", head="main", out=REPO / "runs" / "gate" / "x")

    document = to_result_json(
        config=config, suite=suite, decisive=None, total_calls=0, comment="hello"
    )

    assert document["comment_markdown"] == "hello"
    assert document["base_pass_rate"]["n"] == 2
    assert document["head_pass_rate"]["n"] == 2
    assert document["scenarios"][0]["scenario"] == "a"


def test_diff_lines_reads_a_real_file_change_between_two_commits():
    # Any two commits where docs/decisions changed will do; use the repo's
    # own history so this needs no fixture repo.
    lines = diff_lines(REPO, "HEAD~1", "HEAD", "pyproject.toml")

    assert isinstance(lines, list)


def test_diff_lines_returns_empty_for_an_unresolvable_ref_pair():
    lines = diff_lines(REPO, "not-a-ref", "HEAD", "pyproject.toml")

    assert lines == []
