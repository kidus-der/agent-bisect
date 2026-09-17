"""Routing tau2's NL-assertion judge to a model this account has.

`docs/decisions/0018-retail-nl-judge.md`. tau2 runs its judge whenever
`NL_ASSERTION` is in a task's reward basis -- 112 of 114 retail tasks --
against a model constant that 404s on this endpoint.
"""

from __future__ import annotations

from agent_bisect.adapters.tau2_judge import judge_routed
from agent_bisect.adapters.tau2_tasks import needs_a_judge, task_ids


def test_the_judge_model_is_swapped_for_the_duration():
    import tau2.evaluator.evaluator_nl_assertions as nl_assertions

    before = nl_assertions.DEFAULT_LLM_NL_ASSERTIONS

    with judge_routed("nvidia/some-judge") as chosen:
        assert nl_assertions.DEFAULT_LLM_NL_ASSERTIONS == "nvidia/some-judge"
        assert chosen == "nvidia/some-judge"

    assert before == nl_assertions.DEFAULT_LLM_NL_ASSERTIONS


def test_the_original_is_restored_even_when_the_body_raises():
    import tau2.evaluator.evaluator_nl_assertions as nl_assertions

    before = nl_assertions.DEFAULT_LLM_NL_ASSERTIONS

    try:
        with judge_routed("nvidia/some-judge"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert before == nl_assertions.DEFAULT_LLM_NL_ASSERTIONS


def test_a_task_needs_a_judge_on_the_basis_alone():
    """tau2's own condition. An earlier version also required a non-empty
    nl_assertions list and classified 74 retail tasks as judge-free; they
    were not, and every one of them 404'd."""
    assert len(task_ids("retail", judged=True)) == 112
    assert len(task_ids("retail", judged=False)) == 2
    assert task_ids("airline", judged=True) == []


def test_a_task_without_criteria_needs_no_judge():
    assert needs_a_judge(object()) is False
