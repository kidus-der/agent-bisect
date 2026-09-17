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

Responses are built as real `litellm.ModelResponse` objects (that is what
`tau2.utils.llm_utils.generate` unpacks) with deterministic `id`/`created`
fields, so replaying the same script produces byte-identical payloads.
"""

from __future__ import annotations

import json
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
    """A `completion_fn` that answers from a per-model script."""

    def __init__(self, scripts: Mapping[str, Sequence[ScriptedTurn]]) -> None:
        self._scripts = {model: tuple(turns) for model, turns in scripts.items()}
        self._positions: dict[str, int] = dict.fromkeys(self._scripts, 0)
        self._requests: list[dict[str, Any]] = []

    @property
    def calls(self) -> int:
        """Total responses served — asserted to be 0 by every replay test."""
        return len(self._requests)

    @property
    def calls_by_model(self) -> dict[str, int]:
        return {model: position for model, position in self._positions.items() if position}

    @property
    def requests(self) -> list[dict[str, Any]]:
        """Every request received, in order, for assertions about prompts."""
        return list(self._requests)

    def completion(self, *, model: str, messages: Any, **kwargs: Any) -> Any:
        import litellm

        name = _strip_provider(model)
        script = self._scripts.get(name)
        if script is None:
            raise UnscriptedModelError(
                f"no script for model {name!r}; scripted models: {sorted(self._scripts)}"
            )
        position = self._positions[name]
        if position >= len(script):
            raise ScriptExhaustedError(
                f"script for {name!r} has {len(script)} turns; turn {position} was asked for"
            )
        self._positions[name] = position + 1
        self._requests.append({"model": model, "messages": messages, **kwargs})
        return litellm.ModelResponse(
            id=f"fake-{name}-{position}",
            created=_FIXED_CREATED,
            model=name,
            choices=[
                {"index": 0, "finish_reason": "stop", "message": _message(script[position])}
            ],
            usage={
                "prompt_tokens": _FAKE_PROMPT_TOKENS,
                "completion_tokens": _FAKE_COMPLETION_TOKENS,
                "total_tokens": _FAKE_PROMPT_TOKENS + _FAKE_COMPLETION_TOKENS,
            },
        )
