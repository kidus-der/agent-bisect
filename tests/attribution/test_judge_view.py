"""What the judge may see and may answer — the invariants the types enforce."""

from __future__ import annotations

import pytest
from agent_bisect.attribution.judge_view import (
    JudgeInput,
    JudgeStepView,
    JudgeVerdict,
    RankedStep,
)


def _view(step_idx: int, actor: str = "tool") -> JudgeStepView:
    return JudgeStepView(step_idx, actor, None, None, "content")  # type: ignore[arg-type]


def _input(steps) -> JudgeInput:
    return JudgeInput(
        item_id="i", run_id="r", domain="airline",
        task_description="t", policy="p", steps=tuple(steps),
    )


def _verdict(steps, **overrides) -> JudgeVerdict:
    defaults = dict(
        item_id="i", protocol="all_at_once",
        decisive_step=steps[0] if steps else None,
        ranking=tuple(
            RankedStep(step=s, rank=i + 1, score=0.5, rationale="r")
            for i, s in enumerate(steps)
        ),
        rationale="", calls=1,
    )
    defaults.update(overrides)
    return JudgeVerdict(**defaults)  # type: ignore[arg-type]


# ---- JudgeInput ----


def test_a_run_with_no_steps_is_refused():
    with pytest.raises(ValueError, match="no steps"):
        _input([])


def test_steps_out_of_tape_order_are_refused():
    with pytest.raises(ValueError, match="tape order"):
        _input([_view(3), _view(1)])


def test_a_duplicated_step_index_is_refused():
    with pytest.raises(ValueError, match="duplicate"):
        _input([_view(1), _view(1)])


def test_only_agent_user_and_tool_steps_are_candidates():
    judge_input = _input([_view(0, "agent"), _view(1, "evaluator"), _view(2, "tool")])
    assert judge_input.candidate_steps == (0, 2)


def test_an_evaluator_step_is_not_a_candidate():
    assert _view(0, "evaluator").is_candidate is False


# ---- JudgeVerdict ----


def test_a_parse_failure_cannot_also_name_a_step():
    with pytest.raises(ValueError, match="parse failure"):
        _verdict([], decisive_step=3, parse_failed=True)


def test_a_ranking_whose_ranks_are_not_one_to_n_is_refused():
    with pytest.raises(ValueError, match="1..n"):
        JudgeVerdict(
            item_id="i", protocol="all_at_once", decisive_step=1,
            ranking=(RankedStep(step=1, rank=2, score=0.5, rationale=""),),
            rationale="", calls=1,
        )


def test_the_shortlist_is_the_first_m_ranked_steps():
    assert _verdict([5, 1, 3, 7]).shortlist(2) == (5, 1)


def test_a_shortlist_longer_than_the_ranking_is_just_the_ranking():
    assert _verdict([5]).shortlist(3) == (5,)


def test_a_non_positive_shortlist_size_is_refused():
    with pytest.raises(ValueError, match="top_m"):
        _verdict([5]).shortlist(0)


def test_rank_of_finds_a_ranked_step():
    assert _verdict([5, 1, 3]).rank_of(1) == 2


def test_rank_of_returns_none_for_a_step_that_was_never_ranked():
    assert _verdict([5, 1, 3]).rank_of(9) is None
