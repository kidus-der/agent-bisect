"""The two Who&When protocols: what they ask, when they stop, how they fail."""

from __future__ import annotations

import json

import pytest
from agent_bisect.attribution.judge import (
    JudgeConfig,
    judge_all_at_once,
    judge_step_by_step,
)
from agent_bisect.attribution.judge_store import JudgeCall
from agent_bisect.attribution.judge_view import JudgeInput, JudgeStepView


class FakeBackend:
    """Answers from a queue and remembers every prompt it was given."""

    model = "fake-judge"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[tuple[str, str]] = []

    def ask(self, *, system: str, user: str, item_id: str, protocol: str) -> JudgeCall:
        self.prompts.append((system, user))
        if not self.replies:
            raise AssertionError("the protocol asked more questions than the test scripted")
        return JudgeCall(content=self.replies.pop(0), paid=True)


def _steps(n: int = 5) -> tuple[JudgeStepView, ...]:
    return tuple(
        JudgeStepView(
            step_idx=idx,
            actor="tool" if idx % 2 else "agent",
            tool_name="get_reservation" if idx % 2 else None,
            tool_args={"id": "ABC"} if idx % 2 else None,
            content=f"content of step {idx}",
        )
        for idx in range(n)
    )


def _input(steps=None) -> JudgeInput:
    return JudgeInput(
        item_id="item-1",
        run_id="run-1",
        domain="airline",
        task_description="Rebook the passenger.",
        policy="Confirm before cancelling.",
        steps=steps if steps is not None else _steps(),
    )


def _all_at_once(decisive: int, ranking: list[int]) -> str:
    return json.dumps(
        {
            "decisive_step": decisive,
            "actor": "tool",
            "reason": "wrong value",
            "ranking": [
                {"step": step, "confidence": 0.9 - 0.1 * i, "reason": "r"}
                for i, step in enumerate(ranking)
            ],
        }
    )


def _yes(confidence: float = 0.8) -> str:
    return json.dumps({"error_here": True, "confidence": confidence, "reason": "here"})


def _no(confidence: float = 0.9) -> str:
    return json.dumps({"error_here": False, "confidence": confidence, "reason": "fine"})


# ---- all at once ----


def test_returns_the_decisive_step_and_the_ranking_from_one_call():
    # Arrange
    backend = FakeBackend([_all_at_once(3, [3, 1, 4])])

    # Act
    verdict = judge_all_at_once(_input(), backend)

    # Assert
    assert verdict.decisive_step == 3
    assert verdict.shortlist(3) == (3, 1, 4)
    assert verdict.calls == 1
    assert verdict.parse_failed is False


def test_repairs_a_malformed_answer_with_exactly_one_more_call():
    # Arrange
    backend = FakeBackend(["I think step three.", _all_at_once(3, [3])])

    # Act
    verdict = judge_all_at_once(_input(), backend)

    # Assert
    assert verdict.decisive_step == 3
    assert verdict.calls == 2


def test_the_repair_prompt_quotes_the_problem_and_differs_from_the_first():
    # Arrange
    backend = FakeBackend(["nonsense", _all_at_once(3, [3])])

    # Act
    judge_all_at_once(_input(), backend)

    # Assert
    first_user, second_user = backend.prompts[0][1], backend.prompts[1][1]
    assert second_user != first_user
    assert "nonsense" in second_user


def test_a_second_malformed_answer_is_a_recorded_wrong_answer_not_a_crash():
    # Arrange
    backend = FakeBackend(["nonsense", "still nonsense"])

    # Act
    verdict = judge_all_at_once(_input(), backend)

    # Assert
    assert verdict.parse_failed is True
    assert verdict.decisive_step is None
    assert verdict.ranking == ()
    assert verdict.calls == 2
    assert verdict.failure_reason


def test_a_step_outside_the_trajectory_is_rejected_and_repaired():
    # Arrange
    backend = FakeBackend([_all_at_once(99, [99]), _all_at_once(1, [1])])

    # Act
    verdict = judge_all_at_once(_input(), backend)

    # Assert
    assert verdict.decisive_step == 1


def test_the_prompt_never_carries_a_planted_step():
    # Arrange
    backend = FakeBackend([_all_at_once(3, [3])])

    # Act
    judge_all_at_once(_input(), backend)

    # Assert
    system, user = backend.prompts[0]
    assert "planted" not in (system + user).lower()


# ---- step by step ----


def test_stops_at_the_first_yes():
    # Arrange: no, no, yes at step 2 -- step 3 and 4 must never be asked about
    backend = FakeBackend([_no(), _no(), _yes()])

    # Act
    verdict = judge_step_by_step(_input(), backend)

    # Assert
    assert verdict.decisive_step == 2
    assert verdict.calls == 3
    assert verdict.steps_examined == 3


def test_never_shows_the_judge_a_step_it_has_not_reached():
    # Arrange
    backend = FakeBackend([_no(), _yes()])

    # Act
    judge_step_by_step(_input(), backend)

    # Assert
    assert "[step 1]" not in backend.prompts[0][1]
    assert "[step 2]" not in backend.prompts[1][1]


def test_the_yes_step_is_first_in_the_derived_ranking():
    # Arrange
    backend = FakeBackend([_no(0.1), _no(0.95), _yes()])

    # Act
    verdict = judge_step_by_step(_input(), backend)

    # Assert
    assert verdict.ranking[0].step == 2


def test_an_unconfident_no_outranks_a_confident_no():
    # Arrange: step 0 is a shaky "no", step 1 a firm one, step 2 the yes
    backend = FakeBackend([_no(0.1), _no(0.99), _yes()])

    # Act
    verdict = judge_step_by_step(_input(), backend)

    # Assert
    assert [entry.step for entry in verdict.ranking] == [2, 0, 1]


def test_walking_to_the_end_without_a_yes_blames_no_step_but_still_ranks():
    # Arrange
    backend = FakeBackend([_no(0.9)] * 5)

    # Act
    verdict = judge_step_by_step(_input(), backend)

    # Assert
    assert verdict.decisive_step is None
    assert verdict.parse_failed is False
    assert len(verdict.ranking) == 5


def test_a_parse_failure_mid_walk_is_a_recorded_wrong_answer():
    # Arrange
    backend = FakeBackend([_no(), "nonsense", "still nonsense"])

    # Act
    verdict = judge_step_by_step(_input(), backend)

    # Assert
    assert verdict.parse_failed is True
    assert verdict.decisive_step is None
    assert verdict.calls == 3


def test_the_evaluator_step_is_never_offered_as_a_suspect():
    # Arrange
    steps = (*_steps(3), JudgeStepView(3, "evaluator", None, None, "scored the run"))
    backend = FakeBackend([_no()] * 3)

    # Act
    verdict = judge_step_by_step(_input(steps), backend)

    # Assert
    assert verdict.steps_examined == 3
    assert all(entry.step != 3 for entry in verdict.ranking)


def test_the_walk_stops_at_the_configured_step_budget():
    # Arrange
    backend = FakeBackend([_no()] * 2)
    config = JudgeConfig(max_steps_examined=2)

    # Act
    verdict = judge_step_by_step(_input(), backend, config)

    # Assert
    assert verdict.steps_examined == 2
    assert verdict.decisive_step is None
    assert "budget" in (verdict.failure_reason or "")


def test_the_ranking_is_capped_at_the_ranking_limit():
    # Arrange
    backend = FakeBackend([_no(0.5)] * 8)
    config = JudgeConfig(ranking_limit=3)

    # Act
    verdict = judge_step_by_step(_input(_steps(8)), backend, config)

    # Assert
    assert len(verdict.ranking) == 3


def test_a_run_with_no_candidate_step_is_rejected_loudly():
    # Arrange
    steps = (JudgeStepView(0, "evaluator", None, None, "scored"),)
    backend = FakeBackend([])

    # Act / Assert
    with pytest.raises(ValueError, match="no candidate"):
        judge_step_by_step(_input(steps), backend)
