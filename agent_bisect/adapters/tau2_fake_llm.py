"""A scripted, deterministic stand-in for a real model, plugged in at the
same seam as the real one.

Rule 2 of `docs/brief/summary.md` §3 is that tests never hit the network.
The recorder and the replay engine are worth nothing unless they are
exercised against tau2's *real* orchestrator, environment and evaluator,
so the only thing that may be faked is the model itself — and it has to be
faked exactly where a real model plugs in: as the `completion_fn` of
`adapters.tau2_llm.route_tau2_llm`, which means the limiter, the ledger,
the retry policy, the purpose tagging and the record-before-use hook are
all still the production ones.

Dispatch is on the **model name**, not on who is calling. tau2 gives the
agent, the user simulator and the NL-assertion judge three different model
names, so a script keyed by model needs no privileged knowledge of the
orchestrator's internals — and a test that scripts the wrong participant
fails loudly instead of quietly serving the other one's turn.

**Which turn to serve is read off the request, not off a call counter.**
A real model at temperature 0 is a function of its request, and so is
this one — which is what makes it usable for a fork: a fork replays its
prefix straight off the tape and only *then* asks the model, so a model
counting its own calls would answer turn 0 in the middle of a
conversation and invent a different run. The position is the number of
assistant messages in the history, ignoring the canned greeting tau2's
orchestrator opens with (`DEFAULT_FIRST_AGENT_MESSAGE`), which costs no
LLM call. The user simulator sees its own past turns as `assistant` too
(`UserState.flip_roles`), so one rule serves both.

Responses are built as real `litellm.ModelResponse` objects (that is what
`tau2.utils.llm_utils.generate` unpacks) with deterministic `id`/`created`
fields, so replaying the same script produces byte-identical payloads.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Fixed `created` on every fabricated response: a wall-clock value would
#: make two runs of the same script differ for no reason.
_FIXED_CREATED = 1_758_000_000
_FAKE_PROMPT_TOKENS = 100
_FAKE_COMPLETION_TOKENS = 20


class ScriptExhaustedError(RuntimeError):
    """The scripted model was asked for a turn the script does not have."""


class UnscriptedModelError(RuntimeError):
    """The scripted model was asked for a model it has no script for."""


@dataclass(frozen=True)
class ScriptedToolCall:
    """One tool call in a scripted turn."""

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScriptedTurn:
    """One model response: text to the other party, or tool calls.

    tau2 rejects a message carrying both
    (`Orchestrator._check_communication_error`), so a turn sets one.
    """

    content: str | None = None
    tool_calls: tuple[ScriptedToolCall, ...] = ()


def _strip_provider(model: str) -> str:
    """`openai/deepseek-ai/x` -> `deepseek-ai/x`.

    `Tau2Router.completion` prefixes the model with litellm's provider
    route before calling out; the script is keyed on the bare name the
    caller asked for.
    """
    return model.split("/", 1)[1] if model.startswith("openai/") else model


def turn_index(messages: Sequence[Any]) -> int:
    """How many turns this participant has already taken in `messages`.

    Assistant messages *before* the first message from anyone else are the
    conversation's canned opening, not something a model produced, so they
    do not count. Everything after it does, whatever its content — an
    intervention may have replaced a turn, and the replacement still
    occupies its place in the conversation.
    """
    index = 0
    others_have_spoken = False
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        if role == "system":
            continue
        if role != "assistant":
            others_have_spoken = True
        elif others_have_spoken:
            index += 1
    return index


def _resampled(turn: ScriptedTurn, repeat: int) -> ScriptedTurn:
    """The same turn, said differently — what a fresh sample looks like.

    Tool calls are left alone: changing which tools a resample calls would
    change what the world does, and these exist to vary the *text*, which
    is what a request hash is mostly made of.
    """
    if turn.content is None:
        return turn
    return ScriptedTurn(content=f"{turn.content} (resampled {repeat})", tool_calls=turn.tool_calls)


def _message(turn: ScriptedTurn) -> dict[str, Any]:
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


class ScriptedLLM:
    """A `completion_fn` that answers from a per-model script.

    `vary_on_resample` makes a *repeat* of a turn this instance has
    already served come back with different text. It is off by default,
    and deliberately so: at temperature 0, which is what tau2 runs and
    what `config/models.toml` pins, asking the same history twice really
    does return the same answer, and the fork tests that check a
    no-op fork reproduces its recording depend on that. Turn it on for
    the tests that need a resample to *differ* — the ones that catch
    control flow which only works while the new answer happens to match
    the old one.
    """

    def __init__(
        self,
        scripts: Mapping[str, Sequence[ScriptedTurn]],
        *,
        vary_on_resample: bool = False,
    ) -> None:
        self._scripts = {model: tuple(turns) for model, turns in scripts.items()}
        self._vary_on_resample = vary_on_resample
        self._served: dict[tuple[str, int], int] = {}
        self._calls_by_model: dict[str, int] = {}
        self._requests: list[dict[str, Any]] = []
        # One instance serves a whole batch, and a batch may record
        # several runs at once in tau2's worker threads. Which turn to
        # serve is read off the request, so only the bookkeeping needs
        # guarding.
        self._lock = threading.Lock()

    @property
    def calls(self) -> int:
        """Total responses served — asserted to be 0 by every replay test."""
        with self._lock:
            return len(self._requests)

    @property
    def calls_by_model(self) -> dict[str, int]:
        with self._lock:
            return dict(self._calls_by_model)

    @property
    def requests(self) -> list[dict[str, Any]]:
        """Every request received, in order, for assertions about prompts."""
        with self._lock:
            return list(self._requests)

    def completion(self, *, model: str, messages: Any, **kwargs: Any) -> Any:
        import litellm

        name = _strip_provider(model)
        script = self._scripts.get(name)
        if script is None:
            raise UnscriptedModelError(
                f"no script for model {name!r}; scripted models: {sorted(self._scripts)}"
            )
        position = turn_index(messages)
        if position >= len(script):
            raise ScriptExhaustedError(
                f"script for {name!r} has {len(script)} turns; turn {position} was asked for"
            )
        with self._lock:
            self._calls_by_model[name] = self._calls_by_model.get(name, 0) + 1
            self._requests.append({"model": model, "messages": messages, **kwargs})
            repeat = self._served.get((name, position), 0)
            self._served[(name, position)] = repeat + 1
        turn = script[position]
        varied = bool(repeat) and self._vary_on_resample
        if varied:
            turn = _resampled(turn, repeat)
        return litellm.ModelResponse(
            # The id moves only when the answer does: a temperature-0
            # model asked the same thing twice returns the same payload,
            # ids and all, and the no-op fork tests rely on that.
            id=f"fake-{name}-{position}-{repeat}" if varied else f"fake-{name}-{position}",
            created=_FIXED_CREATED,
            model=name,
            choices=[{"index": 0, "finish_reason": "stop", "message": _message(turn)}],
            usage={
                "prompt_tokens": _FAKE_PROMPT_TOKENS,
                "completion_tokens": _FAKE_COMPLETION_TOKENS,
                "total_tokens": _FAKE_PROMPT_TOKENS + _FAKE_COMPLETION_TOKENS,
            },
        )
