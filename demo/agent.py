"""The scripted, seeded, policy-driven agent and user for the demo suite.

Both participants are **reactive**: every call inspects the conversation so
far and decides what to say next, the way `tests/p5_offline.py`'s
`ReactiveAirlineAgent` does and for the same reason -- a fork replays its
prefix from the tape and asks the live model only from the fork step
onward, so a model that counted its own turns would answer turn 0 in the
middle of a conversation. Reading state off the messages instead makes this
agent correct whether it is serving the original recording or a fork's live
suffix, with no separate code path for either.

Where the "policy a PR can edit" lives depends on **which kind of step**
the decision becomes, because that is what determines whether Bisect can
reliably confirm it later (`docs/decisions/0019-gate-rule.md`):

- `use_correct_task_id` on the two "fresh" `update_lookup` scenarios
  (`update_task_from_initialization_data`,
  `update_task_from_initialization_actions`) never slips *here* — the agent
  always takes "the last task in `get_users()`'s answer" at face value.
  Corrupting that answer is `demo/faults.py`'s job, done at the **tool**
  step, which is what makes it confirmable through `TruthfulToolResult`.
- Everywhere else (`use_stated_title`, `set_completed_status`,
  `escalate_impossible_requests`, and `use_correct_task_id` on the two
  *history*-seeded scenarios, whose target task never touched the real
  database and so cannot be looked up truthfully) the slip is drawn right
  here, seeded from the **active run's id**
  (`agent_bisect.adapters.tau2.current_run_id`) rather than from the
  scenario alone. That is what gives a `Resample` confirmation at one of
  these an actual chance to differ from the original draw: a fork's run id
  differs from its parent's by construction (`attribution.search.rerun_id`),
  so it draws again instead of reproducing the same answer forever.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_bisect.adapters.tau2_fake_llm import ScriptedToolCall, ScriptedTurn
from agent_bisect.adapters.tau2_scenarios import STOP
from demo.policy import DemoPolicy, load_policy
from demo.tasks import AGENT_MODEL, USER_MODEL, ScenarioSpec, scenario_of_run_id

_POLICY_PATH = Path(__file__).with_name("agent_policy.yaml")

_FIXED_CREATED = 1_758_100_000

#: The title every "create" scenario's user actually asks for.
CORRECT_TITLES: dict[str, str] = {
    "create_task": "Important Meeting",
    "create_task_env_assertion": "Important Meeting",
}

#: What a title slip substitutes instead.
_WRONG_TITLE = "New Task"

#: What a task-id slip substitutes instead: the pre-existing task, never
#: the one the conversation is actually about.
_WRONG_TASK_ID = "task_1"

#: What a status slip substitutes instead of "completed".
_WRONG_STATUS = "in_progress"

APOLOGY_TEXT = "I'm sorry, I'm not able to do that."
_TRANSFERRED_TEXT = "You have been transferred to someone who can help with that."
_CREATED_TEXT = "Done -- the task has been created."
#: `update_task_from_initialization_data` gates its reward on both of these
#: substrings appearing in an assistant message (`EvaluationCriteria
#: .communicate_info`, matched case-insensitively); every other update
#: scenario's reward does not depend on this text, so saying it always is
#: harmless and one constant serves both.
_UPDATED_TEXT = (
    "The agent acknowledged the previous context. "
    "The agent confirmed the task status was updated successfully."
)

#: The opening (or, for the two history-seeded scenarios, continuing) line
#: each scenario's scripted user sends before `STOP`.
USER_LINES: dict[str, tuple[str, ...]] = {
    "create_task": ("Please create a task called 'Important Meeting' for user_1.",),
    "create_task_env_assertion": (
        "Please create a task called 'Important Meeting' for user_1.",
    ),
    "update_task_fixed_id": ("Please mark task_1 as completed.",),
    "update_task_from_history": ("Yes, please mark it as completed.",),
    "update_task_from_initialization_data": ("Please mark my task as completed.",),
    "update_task_from_initialization_actions": ("Please mark my task as completed.",),
    "update_task_history_env_assertion": ("Yes, please mark it as completed.",),
    "impossible_delete": ("I need to delete all my current tasks, please.",),
}

#: The two `update_lookup` scenarios whose target task lives only in the
#: seeded conversation, never in the real database -- `get_users()` would
#: truthfully answer `["task_1"]` for either, so the agent reads the
#: history instead. `demo/tasks.py` explains why this makes their
#: `use_correct_task_id` slip an agent-decision step, not a tool one.
_HISTORY_SEEDED = frozenset({"update_task_from_history", "update_task_history_env_assertion"})

_TASK_ID_IN_TEXT = re.compile(r'"task_id"\s*:\s*"(task_\d+)"')


@lru_cache(maxsize=1)
def policy() -> DemoPolicy:
    """The shipped `agent_policy.yaml`, loaded once per process."""
    return load_policy(_POLICY_PATH)


class UnscriptedModelError(RuntimeError):
    """The demo completion function was asked for a model it does not serve."""


def _strip_provider(model: str) -> str:
    """`openai/demo/agent-model` -> `demo/agent-model`.

    Mirrors `adapters.tau2_fake_llm._strip_provider`: `Tau2Router.completion`
    prefixes the model with litellm's provider route before calling out.
    """
    return model.split("/", 1)[1] if model.startswith("openai/") else model


def _role(message: Any) -> str | None:
    return message.get("role") if isinstance(message, Mapping) else getattr(message, "role", None)


def _content(message: Any) -> str | None:
    value = (
        message.get("content") if isinstance(message, Mapping) else getattr(message, "content", None)
    )
    return None if value is None else str(value)


def _raw_tool_calls(message: Any) -> Sequence[Any]:
    calls = (
        message.get("tool_calls")
        if isinstance(message, Mapping)
        else getattr(message, "tool_calls", None)
    )
    return calls or ()


def _tool_call_name(call: Any) -> str | None:
    if isinstance(call, Mapping):
        function = call.get("function") or {}
        return function.get("name") if isinstance(function, Mapping) else getattr(function, "name", None)
    function = getattr(call, "function", None)
    return getattr(function, "name", None)


def _assistant_tool_names(messages: Sequence[Any]) -> frozenset[str]:
    names: set[str] = set()
    for message in messages:
        if _role(message) != "assistant":
            continue
        for call in _raw_tool_calls(message):
            name = _tool_call_name(call)
            if name:
                names.add(name)
    return frozenset(names)


def _said(messages: Sequence[Any], text: str) -> bool:
    return any(_role(m) == "assistant" and _content(m) == text for m in messages)


def _last_task_id_in_text(messages: Sequence[Any]) -> str | None:
    """The most recent `"task_id": "task_N"` anywhere in the conversation."""
    found: str | None = None
    for message in messages:
        content = _content(message)
        if not content:
            continue
        for match in _TASK_ID_IN_TEXT.finditer(content):
            found = match.group(1)
    return found


def _last_get_users_task_id(messages: Sequence[Any], *, user_id: str = "user_1") -> str | None:
    """The last task id `get_users()`'s (possibly faulted) answer lists for `user_id`."""
    import json

    result: str | None = None
    for message in messages:
        if _role(message) != "tool":
            continue
        content = _content(message)
        if not content:
            continue
        try:
            users = json.loads(content)
        except (TypeError, ValueError):
            continue
        if not isinstance(users, list):
            continue
        for user in users:
            if isinstance(user, Mapping) and user.get("user_id") == user_id:
                tasks = user.get("tasks") or []
                if tasks:
                    result = str(tasks[-1])
    return result


@dataclass(frozen=True, slots=True)
class RunContext:
    """What one call needs to know about the run it is serving."""

    run_id: str
    scenario: ScenarioSpec


def _context(run_id: str | None) -> RunContext:
    if not run_id:
        raise RuntimeError(
            "the demo agent was asked for a completion outside any recording session; "
            "current_run_id() returned None"
        )
    return RunContext(run_id=run_id, scenario=scenario_of_run_id(run_id))


def _slips(ctx: RunContext, rule_id: str) -> bool:
    """One deterministic draw, seeded by the *active run's own id*.

    Seeding on `ctx.run_id` rather than on the scenario alone is what lets
    a `Resample` confirmation of this decision draw again instead of
    reproducing the original answer forever -- see the module docstring.
    """
    rule = policy().rule(rule_id)
    rng = random.Random(f"{ctx.run_id}:{rule_id}")
    return DemoPolicy.slips(rule, rng)


# ---- per-family agent scripts ------------------------------------------------


def _create_turn(ctx: RunContext, messages: Sequence[Any]) -> ScriptedTurn:
    if "create_task" not in _assistant_tool_names(messages):
        title = CORRECT_TITLES[ctx.scenario.name]
        if _slips(ctx, ctx.scenario.rule_id):
            title = _WRONG_TITLE
        return ScriptedTurn(
            tool_calls=(
                ScriptedToolCall("c1", "create_task", {"user_id": "user_1", "title": title}),
            )
        )
    return ScriptedTurn(content=_CREATED_TEXT)


def _update_fixed_turn(ctx: RunContext, messages: Sequence[Any]) -> ScriptedTurn:
    if "update_task_status" not in _assistant_tool_names(messages):
        status = "completed"
        if _slips(ctx, ctx.scenario.rule_id):
            status = _WRONG_STATUS
        return ScriptedTurn(
            tool_calls=(
                ScriptedToolCall(
                    "c1", "update_task_status", {"task_id": "task_1", "status": status}
                ),
            )
        )
    return ScriptedTurn(content=_UPDATED_TEXT)


def _update_lookup_turn(ctx: RunContext, messages: Sequence[Any]) -> ScriptedTurn:
    names = _assistant_tool_names(messages)
    if ctx.scenario.name in _HISTORY_SEEDED:
        if "update_task_status" in names:
            return ScriptedTurn(content=_UPDATED_TEXT)
        target = _last_task_id_in_text(messages) or _WRONG_TASK_ID
        if _slips(ctx, ctx.scenario.rule_id):
            target = _WRONG_TASK_ID
        return ScriptedTurn(
            tool_calls=(
                ScriptedToolCall(
                    "c1", "update_task_status", {"task_id": target, "status": "completed"}
                ),
            )
        )
    # A "fresh" scenario: look the task up for real, and never second-guess
    # what the tool says -- a corrupted answer is `demo/faults.py`'s doing,
    # confirmed the label-free way through `TruthfulToolResult`.
    if "get_users" not in names:
        return ScriptedTurn(tool_calls=(ScriptedToolCall("c1", "get_users", {}),))
    if "update_task_status" not in names:
        target = _last_get_users_task_id(messages) or _WRONG_TASK_ID
        return ScriptedTurn(
            tool_calls=(
                ScriptedToolCall(
                    "c2", "update_task_status", {"task_id": target, "status": "completed"}
                ),
            )
        )
    return ScriptedTurn(content=_UPDATED_TEXT)


def _impossible_turn(ctx: RunContext, messages: Sequence[Any]) -> ScriptedTurn:
    names = _assistant_tool_names(messages)
    if "transfer_to_human_agents" in names:
        return ScriptedTurn(content=_TRANSFERRED_TEXT)
    if _said(messages, APOLOGY_TEXT):
        return ScriptedTurn(content=APOLOGY_TEXT)
    if _slips(ctx, ctx.scenario.rule_id):
        return ScriptedTurn(content=APOLOGY_TEXT)
    return ScriptedTurn(
        tool_calls=(
            ScriptedToolCall(
                "c1",
                "transfer_to_human_agents",
                {"summary": "User wants to delete all their tasks; no delete tool exists."},
            ),
        )
    )


_FAMILY_TURN = {
    "create": _create_turn,
    "update_fixed": _update_fixed_turn,
    "update_lookup": _update_lookup_turn,
    "impossible": _impossible_turn,
}


def _agent_turn(ctx: RunContext, messages: Sequence[Any]) -> ScriptedTurn:
    return _FAMILY_TURN[ctx.scenario.family](ctx, messages)


def _user_turn(ctx: RunContext, messages: Sequence[Any]) -> ScriptedTurn:
    for line in USER_LINES[ctx.scenario.name]:
        if not _said(messages, line):
            return ScriptedTurn(content=line)
    return ScriptedTurn(content=STOP)


# ---- the completion_fn --------------------------------------------------


def _message(turn: ScriptedTurn) -> dict[str, Any]:
    import json

    message: dict[str, Any] = {"role": "assistant", "content": turn.content}
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
            }
            for call in turn.tool_calls
        ]
    return message


def _respond(name: str, messages: Sequence[Any], turn: ScriptedTurn) -> Any:
    import litellm

    return litellm.ModelResponse(
        id=f"demo-{name}-{len(messages)}",
        created=_FIXED_CREATED,
        model=name,
        choices=[{"index": 0, "finish_reason": "stop", "message": _message(turn)}],
        usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    )


def demo_completion(*, model: str, messages: Any, **kwargs: Any) -> Any:
    """The `completion_fn` for the whole demo suite: reactive, policy-driven.

    Dispatch is on the model name, exactly like `tau2_fake_llm.ScriptedLLM`;
    unlike it, no per-model turn list is pre-built, because a fork can ask
    for a turn at any position in the conversation, not only the next one
    after the last call this process happened to serve.
    """
    from agent_bisect.adapters.tau2 import current_run_id

    name = _strip_provider(model)
    if name not in (AGENT_MODEL, USER_MODEL):
        raise UnscriptedModelError(f"the demo suite has no script for model {name!r}")
    ctx = _context(current_run_id())
    message_list = list(messages)
    turn = _agent_turn(ctx, message_list) if name == AGENT_MODEL else _user_turn(ctx, message_list)
    return _respond(name, message_list, turn)
