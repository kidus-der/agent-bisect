"""A scripted agent that actually *reads* its tool results.

The P1/P2 offline scenarios script a fixed sequence of turns, which is
exactly right for proving a recording replays. It is not enough for P3:
a planted fault changes what the agent is shown, and a model that answers
by turn index would say the same thing anyway, so every candidate would
be rejected and the funnel would never be exercised.

So this model has one rule on top of the script: if a tool it depends on
answers with something other than what that tool answered the first time
it was called, the agent panics and books a flight nobody asked for. The
booking moves the airline database, the task's DB check fails, and the
run's reward drops to 0 — a planted fault that flips the run, which is
what the KEEP rule is looking for.

"The first time it was called" is learned during the base recording and
is the truth for the rest of the collection: a fork replays its prefix
from the tape, so the prefix always shows the true answers, and only the
faulted step can differ.

`REACTIVE_TOOLS` is deliberately a subset, so one tool step per run is
faultable-but-harmless and the dry run exercises the rejection path too.
Everything else — the orchestrator, the environment, the evaluator, the
domain — is the real tau2.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from agent_bisect.adapters.tau2_fake_llm import (
    ScriptedToolCall,
    ScriptedTurn,
    _message,
    _strip_provider,
    turn_index,
)
from agent_bisect.adapters.tau2_scenarios import STOP, Scenario

AGENT_MODEL = "fake/reactive-agent"
USER_MODEL = "fake/reactive-user"

#: Tools whose answer the agent acts on. A fault in anything else is
#: plantable but harmless, which is what a rejected candidate looks like.
REACTIVE_TOOLS = frozenset({"get_user_details", "search_direct_flight"})

_FIXED_CREATED = 1_758_000_001
_FAKE_PROMPT_TOKENS = 100
_FAKE_COMPLETION_TOKENS = 20

#: The panic: a booking nobody asked for. Valid arguments, so it succeeds
#: and the database moves -- which is what makes the task fail.
PANIC_BOOKING = ScriptedToolCall(
    id="panic-1",
    name="book_reservation",
    arguments={
        "user_id": "mia_li_3668",
        "origin": "PHL",
        "destination": "LGA",
        "flight_type": "one_way",
        "cabin": "economy",
        "flights": [{"flight_number": "HAT001", "date": "2024-05-16"}],
        "passengers": [{"first_name": "Mia", "last_name": "Li", "dob": "1990-04-05"}],
        "payment_methods": [{"payment_id": "credit_card_4421486", "amount": 122}],
        "total_baggages": 1,
        "nonfree_baggages": 0,
        "insurance": "no",
    },
)

#: Task 0 of airline requires no actions and checks no communicated facts,
#: so a run that only reads and then ends scores reward 1.0.
AIRLINE_INJECT = Scenario(
    name="airline-inject",
    domain="airline",
    task_id="0",
    agent=(
        ScriptedTurn(
            tool_calls=(ScriptedToolCall("c1", "get_user_details",
                                         {"user_id": "mia_li_3668"}),)
        ),
        ScriptedTurn(
            tool_calls=(ScriptedToolCall("c2", "search_direct_flight",
                                         {"origin": "PHL", "destination": "LGA",
                                          "date": "2024-05-16"}),)
        ),
        ScriptedTurn(tool_calls=(ScriptedToolCall("c3", "list_all_airports", {}),)),
        ScriptedTurn(content="Here is what I found. Anything else?"),
        ScriptedTurn(content="Thanks for contacting us."),
    ),
    user=(
        ScriptedTurn(content="Hi, I would like some information about my account."),
        ScriptedTurn(content="No, that is all."),
        ScriptedTurn(content=STOP),
    ),
)

#: A second task, so the dry run has more than one base run and the split
#: has more than one group to work with.
AIRLINE_INJECT_2 = Scenario(
    name="airline-inject-2",
    domain="airline",
    task_id="10",
    agent=AIRLINE_INJECT.agent,
    user=AIRLINE_INJECT.user,
)

AIRLINE_INJECT_3 = Scenario(
    name="airline-inject-3", domain="airline", task_id="26",
    agent=AIRLINE_INJECT.agent, user=AIRLINE_INJECT.user,
)

AIRLINE_INJECT_4 = Scenario(
    name="airline-inject-4", domain="airline", task_id="31",
    agent=AIRLINE_INJECT.agent, user=AIRLINE_INJECT.user,
)

DRY_RUN_TASKS: tuple[tuple[str, str], ...] = (
    ("airline", "0"),
    ("airline", "10"),
    ("airline", "26"),
    ("airline", "31"),
)


def _role_of(message: Any) -> str | None:
    if isinstance(message, Mapping):
        return message.get("role")
    return getattr(message, "role", None)


def _content_of(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def _tool_calls_of(message: Any) -> list[Any]:
    if isinstance(message, Mapping):
        return list(message.get("tool_calls") or [])
    return list(getattr(message, "tool_calls", None) or [])


def _called_names(messages: Sequence[Any]) -> set[str]:
    names: set[str] = set()
    for message in messages:
        for call in _tool_calls_of(message):
            function = call.get("function") if isinstance(call, Mapping) else None
            if isinstance(function, Mapping):
                names.add(str(function.get("name")))
    return names


class ReactiveLLM:
    """A `completion_fn` that answers from a script until a tool lies to it."""

    def __init__(self, scenario: Scenario) -> None:
        self._agent = tuple(scenario.agent)
        self._user = tuple(scenario.user)
        self._truth: dict[str, str] = {}
        self._lock = threading.Lock()
        self.calls = 0
        self.panics = 0

    # -- the seam ----------------------------------------------------------

    def completion(self, *, model: str, messages: Any, **_kwargs: Any) -> Any:
        import litellm

        name = _strip_provider(model)
        with self._lock:
            self.calls += 1
        turn = self._turn(name, list(messages))
        return litellm.ModelResponse(
            id=f"reactive-{name}-{turn_index(messages)}",
            created=_FIXED_CREATED,
            model=name,
            choices=[{"index": 0, "finish_reason": "stop", "message": _message(turn)}],
            usage={"prompt_tokens": _FAKE_PROMPT_TOKENS,
                   "completion_tokens": _FAKE_COMPLETION_TOKENS,
                   "total_tokens": _FAKE_PROMPT_TOKENS + _FAKE_COMPLETION_TOKENS},
        )

    def _turn(self, model: str, messages: list[Any]) -> ScriptedTurn:
        if model == USER_MODEL:
            return self._scripted(self._user, messages, model)
        self._learn(messages)
        if self._lied_to(messages):
            return self._panic(messages)
        return self._scripted(self._agent, messages, model)

    def _scripted(self, script: Sequence[ScriptedTurn], messages: list[Any], model: str):
        position = turn_index(messages)
        if position >= len(script):
            raise AssertionError(
                f"the {model} script has {len(script)} turns; turn {position} was asked for"
            )
        return script[position]

    # -- the one rule on top of the script ---------------------------------

    def _learn(self, messages: list[Any]) -> None:
        """Remember what each reactive tool answered the first time."""
        with self._lock:
            for tool_name, content in _tool_answers(messages):
                if tool_name in REACTIVE_TOOLS and tool_name not in self._truth:
                    self._truth[tool_name] = content

    def _lied_to(self, messages: list[Any]) -> bool:
        with self._lock:
            truth = dict(self._truth)
        return any(
            tool_name in REACTIVE_TOOLS and truth.get(tool_name, content) != content
            for tool_name, content in _tool_answers(messages)
        )

    def _panic(self, messages: list[Any]) -> ScriptedTurn:
        if "book_reservation" not in _called_names(messages):
            with self._lock:
                self.panics += 1
            return ScriptedTurn(tool_calls=(PANIC_BOOKING,))
        spoken = sum(
            1
            for message in messages
            if _role_of(message) == "assistant" and _content_of(message)
        )
        if spoken <= 1:
            return ScriptedTurn(content="I have made a booking to sort this out.")
        return ScriptedTurn(content="Thanks for contacting us.")


def _tool_answers(messages: Sequence[Any]) -> list[tuple[str, str]]:
    """`(tool_name, content)` for every tool message, in order.

    The name is taken from the assistant tool call the message answers,
    matched by id, because a tau2 `ToolMessage` carries no tool name.
    """
    names_by_id: dict[str, str] = {}
    answers: list[tuple[str, str]] = []
    for message in messages:
        for call in _tool_calls_of(message):
            if not isinstance(call, Mapping):
                continue
            function = call.get("function")
            if isinstance(function, Mapping):
                names_by_id[str(call.get("id"))] = str(function.get("name"))
        if _role_of(message) != "tool":
            continue
        call_id = (
            message.get("tool_call_id") if isinstance(message, Mapping)
            else getattr(message, "id", None)
        )
        answers.append((names_by_id.get(str(call_id), ""), _content_of(message)))
    return answers


def scripts_for(scenario: Scenario) -> dict[str, list[ScriptedTurn]]:
    return {AGENT_MODEL: list(scenario.agent), USER_MODEL: list(scenario.user)}


def as_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
