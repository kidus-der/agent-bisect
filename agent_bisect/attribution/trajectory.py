"""A recorded run, as the judge is allowed to see it.

Reads the tape and the blob store and produces a `JudgeInput`: one entry
per agent / user / tool step, carrying the step's own `step_idx` so the
judge's answer is directly comparable with a planted label and with the
step the estimator blames.

Two containment rules are enforced here rather than trusted to a prompt:

1. **Evaluator steps are dropped.** tau2's NL-assertion judge runs after
   the loop and says whether the run satisfied the task. That is grading
   information the agent never had, and showing it to the failure judge
   would hand it the outcome it is supposed to infer. Dropping the step
   does not renumber anything: the remaining steps keep their recorded
   indices, so a trajectory can legitimately read 0, 1, 3.
2. **Nothing else is read.** The manifest's task/policy text is passed in
   by the caller (the tau2 wiring lives in `adapters/`), and no outcome,
   reward breakdown, parent run or intervention reference is touched.

A step whose payload blob is missing renders as `MISSING_PAYLOAD` rather
than raising: a recording gap is a fact about the item, and an item the
judge answers badly because of one is an item the judge got wrong. It is
never silently skipped, because a skipped step is a step the judge cannot
name.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from agent_bisect.attribution.judge_view import (
    CANDIDATE_ACTORS,
    JudgeInput,
    JudgeStepView,
)
from agent_bisect.core.store import BlobStore, canonical_json_bytes
from agent_bisect.core.tape import Step, TapeReader

#: Rendered in place of a step whose payload blob is absent or unreadable.
MISSING_PAYLOAD = "(no recorded payload for this step)"

#: Prefix on a tool result the environment flagged as an error, so the
#: judge sees the failure rather than having to infer it from wording.
TOOL_ERROR_PREFIX = "error: "


def _load(store: BlobStore, ref: str | None) -> Any | None:
    if ref is None:
        return None
    try:
        return store.get_json(ref)
    except Exception:  # noqa: BLE001 - a gap in the recording, not a crash
        # Deliberately broad. Whatever went wrong reading one payload (a
        # missing blob, a corrupt one, a store that raises something of its
        # own) must not abort the whole trajectory: the step still exists,
        # and the judge must still be able to name it.
        return None


def _render_tool_calls(message: dict[str, Any]) -> list[str]:
    calls = message.get("tool_calls") or []
    rendered: list[str] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        name = function.get("name", "?")
        arguments = function.get("arguments", "")
        rendered.append(f"calls {name}({arguments})")
    return rendered


def _llm_content(payload: Any) -> str:
    """The text and tool calls of one recorded LLM response."""
    if not isinstance(payload, dict):
        return MISSING_PAYLOAD
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return MISSING_PAYLOAD
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        return MISSING_PAYLOAD
    parts = [str(message.get("content"))] if message.get("content") else []
    parts.extend(_render_tool_calls(message))
    return "\n".join(parts) if parts else MISSING_PAYLOAD


def _tool_content(payload: Any) -> str:
    """The result of one recorded tool execution, error flag included."""
    if not isinstance(payload, dict):
        return MISSING_PAYLOAD
    content = payload.get("content")
    if content is None:
        body = canonical_json_bytes(payload).decode("utf-8")
    elif isinstance(content, str):
        body = content
    else:
        body = json.dumps(content, sort_keys=True)
    return f"{TOOL_ERROR_PREFIX}{body}" if payload.get("error") else body


def _view(step: Step, store: BlobStore) -> JudgeStepView:
    if step.actor == "tool":
        content = _tool_content(_load(store, step.tool_result_ref))
    else:
        content = _llm_content(_load(store, step.response_ref))
    return JudgeStepView(
        step_idx=step.step_idx,
        actor=step.actor,
        tool_name=step.tool_name,
        tool_args=dict(step.tool_args) if step.tool_args else None,
        content=content,
    )


def tool_steps_of(steps: Sequence[Step]) -> tuple[int, ...]:
    """The indices of the tool steps in `steps` -- the only plantable ones."""
    return tuple(step.step_idx for step in steps if step.actor == "tool")


def build_judge_input(
    run_id: str,
    *,
    reader: TapeReader,
    store: BlobStore,
    item_id: str,
    task_description: str,
    policy: str,
    load_steps: Callable[[str], Sequence[Step]] | None = None,
) -> JudgeInput:
    """The judge's view of `run_id`: agent, user and tool steps only."""
    steps = (load_steps or reader.get_steps)(run_id)
    views = tuple(_view(step, store) for step in steps if step.actor in CANDIDATE_ACTORS)
    if not views:
        raise ValueError(f"run {run_id!r} has no candidate step for the judge to name")
    return JudgeInput(
        item_id=item_id,
        run_id=run_id,
        domain=_domain_of(reader, run_id),
        task_description=task_description,
        policy=policy,
        steps=views,
    )


def _domain_of(reader: TapeReader, run_id: str) -> str:
    """The run's domain, or an empty string when the manifest is unreadable.

    The domain is context for the judge, not evidence; a run whose manifest
    cannot be read is still judgeable from its trajectory.
    """
    try:
        return reader.get_manifest(run_id).domain
    except Exception:  # noqa: BLE001 - see docstring
        return ""
