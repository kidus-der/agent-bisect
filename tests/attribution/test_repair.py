"""Repair proposals: only on real failures, scored on their own."""

from __future__ import annotations

import json

import pytest
from agent_bisect.attribution.judge_store import JudgeCall
from agent_bisect.attribution.judge_view import JudgeStepView
from agent_bisect.attribution.repair import (
    REPAIR_PROTOCOL,
    RepairNotApplicableError,
    RepairProposal,
    propose_repair,
)
from agent_bisect.core.tape import Step


class StubBackend:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.asked: list[tuple[str, str]] = []

    def ask(self, *, system, user, item_id, protocol):
        self.asked.append((protocol, user))
        return JudgeCall(content=self.replies.pop(0), paid=True)


def _view(step_idx=3, actor="tool") -> JudgeStepView:
    return JudgeStepView(
        step_idx=step_idx,
        actor=actor,  # type: ignore[arg-type]
        tool_name="get_reservation_details" if actor == "tool" else None,
        tool_args={"id": "ABC"} if actor == "tool" else None,
        content='{"cabin": "economy"}',
    )


def _step(step_idx=3, actor="tool") -> Step:
    return Step(
        run_id="r1", step_idx=step_idx, actor=actor,  # type: ignore[arg-type]
        tool_name="get_reservation_details" if actor == "tool" else None,
        state_before="s", state_after="s", state_hash="h",
    )


def _reply(kind="tool_result", replacement='{"cabin": "business"}', reason="because"):
    return json.dumps({"kind": kind, "replacement": replacement, "reason": reason})


def _propose(backend, *, step=None, planted=None):
    return propose_repair(
        run_id="r1",
        step=step or _view(),
        trajectory="[step 3] tool",
        task_description="do the thing",
        policy="follow the policy",
        backend=backend,
        planted_step=planted,
    )


# ---- containment ----


def test_a_planted_fault_is_never_offered_for_repair():
    # Arrange / Act / Assert
    with pytest.raises(RepairNotApplicableError, match="planted"):
        _propose(StubBackend([_reply()]), planted=3)


def test_the_refusal_cites_why_proposals_are_scored_separately():
    # Arrange / Act / Assert
    with pytest.raises(RepairNotApplicableError, match="real failures"):
        _propose(StubBackend([]), planted=3)


def test_an_evaluator_step_cannot_be_repaired():
    # Arrange / Act / Assert
    with pytest.raises(RepairNotApplicableError, match="evaluator"):
        _propose(StubBackend([]), step=_view(actor="evaluator"))


# ---- proposing ----


def test_a_tool_step_gets_a_replacement_tool_result():
    # Arrange
    backend = StubBackend([_reply()])

    # Act
    proposal = _propose(backend)

    # Assert
    assert proposal.kind == "tool_result"
    assert proposal.proposed is True
    assert proposal.calls == 1


def test_the_call_is_tagged_as_a_repair_not_a_judgement():
    # Arrange
    backend = StubBackend([_reply()])

    # Act
    _propose(backend)

    # Assert
    assert backend.asked[0][0] == REPAIR_PROTOCOL


def test_an_agent_step_gets_a_replacement_message():
    # Arrange
    backend = StubBackend([_reply(kind="agent_message", replacement="I will check first.")])

    # Act
    proposal = _propose(backend, step=_view(actor="agent"))

    # Assert
    assert proposal.kind == "agent_message"


def test_declining_to_propose_is_a_real_answer_not_a_failure():
    # Arrange
    backend = StubBackend([_reply(kind="none", replacement="", reason="nothing to change")])

    # Act
    proposal = _propose(backend)

    # Assert
    assert proposal.proposed is False
    assert proposal.parse_failed is False
    assert proposal.reason == "nothing to change"


def test_a_malformed_answer_is_repaired_with_one_more_call():
    # Arrange
    backend = StubBackend(["not json at all", _reply()])

    # Act
    proposal = _propose(backend)

    # Assert
    assert proposal.proposed is True
    assert proposal.calls == 2


def test_a_second_malformed_answer_is_recorded_not_raised():
    # Arrange
    backend = StubBackend(["nope", "still nope"])

    # Act
    proposal = _propose(backend)

    # Assert
    assert proposal.parse_failed is True
    assert proposal.proposed is False
    assert proposal.calls == 2
    assert proposal.failure_reason


def test_an_empty_replacement_is_rejected_rather_than_applied():
    # Arrange
    backend = StubBackend([_reply(replacement="   "), _reply()])

    # Act
    proposal = _propose(backend)

    # Assert: the first answer was rejected, the second accepted
    assert proposal.calls == 2
    assert proposal.replacement == '{"cabin": "business"}'


def test_an_unknown_kind_is_rejected():
    # Arrange
    backend = StubBackend([_reply(kind="teleport"), _reply()])

    # Act
    proposal = _propose(backend)

    # Assert
    assert proposal.calls == 2


# ---- applying ----


def test_a_tool_repair_becomes_a_replace_tool_result():
    # Arrange
    proposal = _propose(StubBackend([_reply()]))

    # Act
    intervention = proposal.as_intervention(_step())

    # Assert
    assert intervention.name == "replace_tool_result"


def test_an_agent_repair_becomes_a_force_action():
    # Arrange
    proposal = _propose(
        StubBackend([_reply(kind="agent_message", replacement="check first")]),
        step=_view(actor="agent"),
    )

    # Act
    intervention = proposal.as_intervention(_step(actor="agent"))

    # Assert
    assert intervention.name == "force_action"


def test_a_tool_repair_refuses_to_be_applied_to_an_agent_step():
    # Arrange
    proposal = _propose(StubBackend([_reply()]))

    # Act / Assert
    with pytest.raises(RepairNotApplicableError, match="agent step"):
        proposal.as_intervention(_step(actor="agent"))


def test_a_non_proposal_cannot_be_applied():
    # Arrange
    proposal = RepairProposal(
        run_id="r1", step_idx=3, kind="none", replacement="", reason="nothing",
        calls=1,
    )

    # Act / Assert
    with pytest.raises(RepairNotApplicableError, match="no repair"):
        proposal.as_intervention(_step())
