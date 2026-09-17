"""A real planted-fault item on a real tau2 environment, with no network.

The end-to-end P5 test needs one thing the scripted scenarios in
`adapters/tau2_scenarios.py` cannot give it: an agent whose behaviour
**depends on what a tool told it**. A script keyed by turn index answers
the same way whether or not a fault was planted, so nothing downstream of
the fault can change and there is no causal step to find.

`ReactiveAirlineAgent` is that agent, on airline task 1 (a cancellation
the policy does not allow):

1. `get_user_details(raj_sanchez_7340)` — reads the user's reservations.
2. `get_reservation_details(<first reservation>)` — reads that booking.
3. **the decision**: if the booking is `business` cabin the agent refuses
   to cancel; otherwise it calls `cancel_reservation`.

That decision is what makes the run pass or fail, for tau2's own reasons
and not ours: refusing leaves the database untouched and the task's DB
check passes (reward 1.0); cancelling moves the database and it fails
(reward 0.0). Measured, not assumed — `test_p5_end_to_end.py` pins both.

So planting a `wrong_value` fault in step 2's result — `business` becomes
`economy` — flips a passing run into a failing one, and the causal step is
exactly that tool step. `TruthfulToolResult` at it re-executes the call
against the restored state, gets `business` back, and the run passes
again. No oracle, no label, no knowledge of what was planted.

Everything here runs tau2's real orchestrator, environment and evaluator
with sockets blocked; only the model is scripted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_bisect.adapters.tau2_fake_llm import (
    ScriptedLLM,
    ScriptedToolCall,
    ScriptedTurn,
)
from agent_bisect.adapters.tau2_scenarios import AGENT_MODEL, STOP
from agent_bisect.attribution.judge_store import JudgeCall
from agent_bisect.attribution.judge_view import Protocol

DOMAIN = "airline"
TASK_ID = "1"
USER_ID = "raj_sanchez_7340"
#: The cabin the real booking is in. Seeing it is what makes the agent refuse.
TRUE_CABIN = "business"
#: What the planted `wrong_value` fault rewrites it to.
FAULTED_CABIN = "economy"


def strip_provider(model: str) -> str:
    """`openai/x` -> `x`; the script is keyed on the bare model name."""
    return model.split("/", 1)[1] if model.startswith("openai/") else model


def _last_tool_content(messages: Sequence[Any]) -> str:
    for message in reversed(list(messages)):
        role = (
            message.get("role") if isinstance(message, Mapping)
            else getattr(message, "role", None)
        )
        if role == "tool":
            content = (
                message.get("content") if isinstance(message, Mapping)
                else getattr(message, "content", "")
            )
            return str(content or "")
    return ""


def _first_reservation(content: str) -> str:
    try:
        reservations = list((json.loads(content) or {}).get("reservations") or [])
    except (TypeError, ValueError):
        reservations = []
    return str(reservations[0]) if reservations else "MISSING"


USER_SCRIPT = (
    ScriptedTurn(content="Hi, I want to cancel my reservation."),
    ScriptedTurn(content="Okay."),
    ScriptedTurn(content=STOP),
    ScriptedTurn(content=STOP),
)


class ReactiveAirlineAgent:
    """A `completion_fn` whose third turn depends on what the tools said."""

    def __init__(self) -> None:
        self.calls = 0
        self.cancelled = False

    def _agent_script(self, messages: Sequence[Any]) -> list[ScriptedTurn]:
        seen = _last_tool_content(messages)
        reservation = _first_reservation(seen)
        refuses = f'"{TRUE_CABIN}"' in seen
        decision = (
            ScriptedTurn(
                content="That booking is business cabin, so I cannot cancel it here."
            )
            if refuses
            else ScriptedTurn(
                tool_calls=(
                    ScriptedToolCall(
                        id="c3", name="cancel_reservation",
                        arguments={"reservation_id": "MZDDS4"},
                    ),
                )
            )
        )
        if not refuses:
            self.cancelled = True
        return [
            ScriptedTurn(
                tool_calls=(
                    ScriptedToolCall(
                        id="c1", name="get_user_details", arguments={"user_id": USER_ID}
                    ),
                )
            ),
            ScriptedTurn(
                tool_calls=(
                    ScriptedToolCall(
                        id="c2", name="get_reservation_details",
                        arguments={"reservation_id": reservation},
                    ),
                )
            ),
            decision,
            ScriptedTurn(content="Thanks for contacting us."),
            ScriptedTurn(content="Goodbye."),
        ]

    def completion(self, *, model: str, messages: Any, **kwargs: Any) -> Any:
        """Build the script this conversation implies, then serve it.

        Delegating to the production `ScriptedLLM` keeps one implementation
        of "which turn does this conversation ask for" and of how a
        response object is built.
        """
        self.calls += 1
        name = strip_provider(model)
        script = (
            self._agent_script(messages) if name == AGENT_MODEL else list(USER_SCRIPT)
        )
        return ScriptedLLM({name: script}).completion(
            model=model, messages=messages, **kwargs
        )


@dataclass
class FakeJudge:
    """A judge with controllable recall, for testing the pipeline's arithmetic.

    `answers` maps an item id to the ranking it should return. An item with
    no entry gets `fallback`, which is how "the judge missed the culprit"
    and "the judge could not answer at all" (an empty ranking) are
    scripted. Nothing here calls a model.
    """

    answers: Mapping[str, Sequence[int]]
    fallback: Sequence[int] = ()
    model: str = "fake-judge"
    step_by_step_yes: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        self.asked: list[tuple[str, Protocol]] = []

    def _ranking(self, item_id: str) -> Sequence[int]:
        return self.answers.get(item_id, self.fallback)

    def ask(
        self, *, system: str, user: str, item_id: str, protocol: Protocol
    ) -> JudgeCall:
        self.asked.append((item_id, protocol))
        if protocol == "all_at_once":
            return JudgeCall(content=self._all_at_once(item_id), paid=True)
        return JudgeCall(content=self._step_by_step(item_id, user), paid=True)

    def _all_at_once(self, item_id: str) -> str:
        ranking = list(self._ranking(item_id))
        if not ranking:
            return "I could not determine which step was at fault."
        return json.dumps(
            {
                "decisive_step": ranking[0],
                "actor": "tool",
                "reason": "the value it returned is wrong",
                "ranking": [
                    {"step": step, "confidence": max(0.05, 0.9 - 0.1 * index),
                     "reason": "suspect"}
                    for index, step in enumerate(ranking)
                ],
            }
        )

    def _step_by_step(self, item_id: str, user: str) -> str:
        """Say yes at the step this item's ranking puts first, else no."""
        target = (self.step_by_step_yes or {}).get(item_id)
        if target is None:
            ranking = list(self._ranking(item_id))
            target = ranking[0] if ranking else -1
        asked_about = _asked_step(user)
        here = asked_about == target
        return json.dumps(
            {
                "error_here": here,
                "confidence": 0.8 if here else 0.7,
                "reason": "looks wrong" if here else "looks fine",
            }
        )


def _asked_step(user_prompt: str) -> int:
    """Which step the step-by-step prompt is asking about."""
    marker = "Is step "
    start = user_prompt.rfind(marker)
    if start < 0:
        return -1
    digits = user_prompt[start + len(marker):].split(" ", 1)[0]
    return int(digits) if digits.isdigit() else -1
