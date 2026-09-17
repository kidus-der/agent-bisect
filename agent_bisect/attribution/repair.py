"""Proposing a fix at step k when there is no oracle.

On the planted-fault dataset the fix is known: `TruthfulToolResult` gets
the true answer back by re-executing the call. On a **real** failure there
is no such thing — nobody knows what the tool "should" have said, because
it said the right thing and the agent still failed. So the fix has to be
proposed, and the only honest way to find out whether it works is to apply
it and re-run, exactly as with any other intervention.

Two rules this module exists to keep, from `docs/brief/summary.md` §9:

- **Repair proposals are scored separately from oracle fixes.** A proposed
  fix that works is a weaker claim than a known fix that works, and mixing
  them would let the easy half of the dataset carry the hard half.
  `RepairResult.method` is `"repair"` and never enters the P5 accuracy
  tables.
- **Only on real, un-planted failures.** Proposing a repair for a fault we
  planted would be marking our own homework: the model would be asked to
  reinvent a value we deliberately corrupted, and a hit would say nothing
  about the method. `propose_repair` refuses an item that carries a
  planted label.

The proposal itself is one LLM call through the same machinery as the
judge — ledgered under the `repair` purpose, recorded before use, cached
per prompt so a resume pays for nothing twice — and its output is
validated against a strict schema with one repair retry, after which a
parse failure is a recorded non-proposal rather than an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_bisect.attribution.judge_parse import (
    JudgeParseError,
    extract_json_object,
)
from agent_bisect.attribution.judge_prompts import TruncationPolicy, truncate
from agent_bisect.attribution.judge_store import JudgeCall
from agent_bisect.attribution.judge_view import JudgeStepView
from agent_bisect.core.replay import Intervention
from agent_bisect.core.tape import Step

REPAIR_PROTOCOL = "repair"

#: How much of the step's own payload the proposer is shown.
DEFAULT_TRUNCATION = TruncationPolicy(max_chars_per_step=2_000)


class RepairNotApplicableError(ValueError):
    """This step, or this item, may not be repaired by proposal."""


REPAIR_SYSTEM = """\
You are proposing a single, concrete change to one step of a customer-service \
conversation that failed, to find out whether that step caused the failure.

You are shown the conversation and one step of it. Propose what that step should have \
been instead. Change exactly that step; you are not rewriting the conversation.

- If the step is a `tool` step, propose the tool result the system should have returned: \
give the replacement `content` as a string, in the same shape as the one you were shown.
- If the step is an `agent` step, propose what the agent should have said or done instead: \
give the replacement message text.

Answer with ONE JSON object and nothing else. No prose before or after it, no markdown \
fence.

{
  "kind": "tool_result" | "agent_message",
  "replacement": "<the new content, as a string>",
  "reason": "<one or two sentences on why this would have changed the outcome>"
}

If you cannot propose a concrete change for this step, set "kind" to "none" and say why in \
"reason". That is a real answer; guessing is not.
"""

REPAIR_USER = """\
# The task the agent was given

{task_description}

# The policy the agent had to follow

{policy}

# The conversation, in order, with the step indices as recorded

{trajectory}

# The step to change

[step {step_idx}] {actor}{tool}

{payload}

# Your answer

What should step {step_idx} have been? Answer with the JSON object described above.
"""


@dataclass(frozen=True, slots=True)
class RepairProposal:
    """One proposed fix at one step, or a recorded refusal to propose."""

    run_id: str
    step_idx: int
    kind: str
    replacement: str
    reason: str
    calls: int
    parse_failed: bool = False
    failure_reason: str | None = None

    @property
    def proposed(self) -> bool:
        """Whether there is anything to apply. `kind == "none"` is an answer."""
        return not self.parse_failed and self.kind in ("tool_result", "agent_message")

    def as_intervention(self, step: Step) -> Intervention:
        """The proposal as something the fork driver can apply at `step`."""
        from agent_bisect.attribution.interventions import ForceAction, ReplaceToolResult

        if not self.proposed:
            raise RepairNotApplicableError(
                f"no repair was proposed for step {self.step_idx} "
                f"({self.failure_reason or self.reason})"
            )
        if self.kind == "tool_result":
            if step.actor != "tool":
                raise RepairNotApplicableError(
                    f"a tool-result repair cannot be applied to a {step.actor} step"
                )
            return ReplaceToolResult(
                step=self.step_idx, new_result={"content": self.replacement}
            )
        if step.actor == "tool":
            raise RepairNotApplicableError(
                "an agent-message repair cannot be applied to a tool step"
            )
        return ForceAction(step=self.step_idx, message=self.replacement)


def _parse(text: str) -> tuple[str, str, str]:
    payload = extract_json_object(text)
    kind = payload.get("kind")
    if kind not in ("tool_result", "agent_message", "none"):
        raise JudgeParseError(
            f"'kind' must be tool_result, agent_message or none, got {kind!r}"
        )
    replacement = payload.get("replacement", "")
    if kind != "none" and not isinstance(replacement, str):
        raise JudgeParseError("'replacement' must be a string")
    if kind != "none" and not replacement.strip():
        raise JudgeParseError("'replacement' is empty; propose a concrete change or 'none'")
    reason = payload.get("reason", "")
    return str(kind), str(replacement), str(reason if isinstance(reason, str) else "")


def _render_step(view: JudgeStepView, policy: TruncationPolicy) -> str:
    return truncate(view.content, policy)


def propose_repair(
    *,
    run_id: str,
    step: JudgeStepView,
    trajectory: str,
    task_description: str,
    policy: str,
    backend: Any,
    planted_step: int | None = None,
    truncation: TruncationPolicy = DEFAULT_TRUNCATION,
) -> RepairProposal:
    """Ask for one concrete change at `step`. Never for a planted fault."""
    if planted_step is not None:
        raise RepairNotApplicableError(
            f"run {run_id!r} carries a planted label at step {planted_step}; repair "
            "proposals are only scored on real failures "
            "(docs/brief/summary.md §9, fact 5)"
        )
    if not step.is_candidate:
        raise RepairNotApplicableError(
            f"step {step.step_idx} is an {step.actor} step and cannot be repaired"
        )

    user = REPAIR_USER.format(
        task_description=task_description,
        policy=policy,
        trajectory=trajectory,
        step_idx=step.step_idx,
        actor=step.actor,
        tool=f" · {step.tool_name}" if step.tool_name else "",
        payload=_render_step(step, truncation),
    )
    answer: JudgeCall = backend.ask(
        system=REPAIR_SYSTEM, user=user, item_id=run_id, protocol=REPAIR_PROTOCOL
    )
    try:
        kind, replacement, reason = _parse(answer.content)
        return RepairProposal(
            run_id=run_id,
            step_idx=step.step_idx,
            kind=kind,
            replacement=replacement,
            reason=reason,
            calls=1,
        )
    except JudgeParseError as first:
        repaired = backend.ask(
            system=REPAIR_SYSTEM,
            user=(
                f"{user}\n\n---\n\nYour previous answer could not be used.\n\n"
                f"What you sent:\n{answer.content}\n\nWhy it was rejected: {first}\n\n"
                "Send the JSON object again, correctly this time."
            ),
            item_id=run_id,
            protocol=REPAIR_PROTOCOL,
        )
    try:
        kind, replacement, reason = _parse(repaired.content)
    except JudgeParseError as second:
        return RepairProposal(
            run_id=run_id,
            step_idx=step.step_idx,
            kind="none",
            replacement="",
            reason="",
            calls=2,
            parse_failed=True,
            failure_reason=str(second),
        )
    return RepairProposal(
        run_id=run_id,
        step_idx=step.step_idx,
        kind=kind,
        replacement=replacement,
        reason=reason,
        calls=2,
    )
