"""The interventions: the one thing changed at the fork step.

Each type implements `core.replay.Intervention` — `name`, plus
`apply(step, payload)` returning the payload to use instead of the
recorded one, or `core.replay.LIVE` to sample fresh. On top of that
protocol every intervention here is

- **frozen** — a dataclass that cannot be edited after construction, so
  the thing a run was labelled with is the thing that ran;
- **serialisable** — `to_ref()` / `from_ref()` round-trip through plain
  JSON, which is what a forked run's `intervention_ref` blob holds;
- **hashed** — `intervention_hash` is a sha256 over `{name, fields}` in
  canonical JSON, stable across processes and across instances, so two
  runs can be compared by what was done to them;
- **described** — `describe()` is one line for the dashboard and the PR
  comment ("tool result replaced · NM1VX1 -> ZFA04Y").

## Two kinds

`ReplaceToolResult`, `ForceAction`, `Resample` and `TruthfulToolResult`
change a *response* at step k, which is exactly what `apply` expresses.

`EditPrompt` and `SwapModel` change the *requests* made from k onward,
which `apply` cannot express on its own: they resample step k (`apply`
returns `LIVE`) and additionally shape every live request through
`shape_request`. `shaped_completion` wraps a live completion callable
with that shaping, so the replay engine needs no change and `core/` stays
unaware of attribution — the fork driver takes its live completion as an
argument already.

## What `ReplaceToolResult` does and does not change

It changes **what the agent sees**. It does not change the world: the
tool already executed (or its recorded result was served and the snapshot
restored), so the database is whatever the real call left behind. That is
deliberate, and it is what makes a planted fault a *perception* fault —
the agent is told the wrong thing about a world that is unchanged — and
what makes the oracle fix well defined: the original tool result.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

from agent_bisect.core.replay import LIVE
from agent_bisect.core.store import canonical_json_bytes, sha256_hex
from agent_bisect.core.tape import Step

#: Fields of a tool-result payload that identify *which* call it answers
#: and when, rather than what the tool said. A replacement never touches
#: them: a `ToolMessage` whose id stopped matching its `ToolCall` is not a
#: counterfactual, it is a broken conversation.
IDENTITY_FIELDS = ("id", "requestor", "turn_idx", "timestamp")

#: Actors whose step carries an LLM response payload.
_LLM_ACTORS = frozenset({"agent", "user", "evaluator"})

#: Longest value rendered into a `describe()` line, per side.
_DESCRIBE_CHARS = 60


class InterventionError(Exception):
    """Base class for everything this module refuses to do."""


class MisappliedInterventionError(InterventionError):
    """An intervention was handed a step it was not built for.

    Silently doing nothing would make the treated arm a second control
    arm and the measured effect zero for a reason nobody could see.
    """


class UnresolvedInterventionError(InterventionError):
    """An intervention that needs a resolver was applied without one."""


@runtime_checkable
class RequestShaper(Protocol):
    """An intervention that also changes the live requests after the fork."""

    def shape_request(self, request: Mapping[str, Any]) -> dict[str, Any]: ...


#: What supplies `TruthfulToolResult` with the true result of a step:
#: re-execute the recorded tool call against the state the step ran on.
TruthProvider = Callable[[Step], Mapping[str, Any]]


def _shorten(value: Any) -> str:
    text = value if isinstance(value, str) else canonical_json_bytes(value).decode("utf-8")
    return text if len(text) <= _DESCRIBE_CHARS else text[:_DESCRIBE_CHARS] + "…"


class InterventionBase:
    """Shared identity: the hash, the ref blob, and the step guard."""

    name: ClassVar[str]

    def fields(self) -> dict[str, Any]:
        """The JSON-native values that define this intervention."""
        raise NotImplementedError

    def describe(self) -> str:
        """One line, for a diff, a tape row or a PR comment."""
        raise NotImplementedError

    @property
    def target_step(self) -> int:
        """The step this intervention is armed at."""
        raise NotImplementedError

    @property
    def intervention_hash(self) -> str:
        """Stable sha256 over `{name, fields}`; equal iff the change is equal."""
        return sha256_hex(canonical_json_bytes({"name": self.name, "fields": self.fields()}))

    def to_ref(self) -> dict[str, Any]:
        """The blob a forked run records to say what was done to it."""
        return {
            "name": self.name,
            "hash": self.intervention_hash,
            "describe": self.describe(),
            "fields": self.fields(),
        }

    def _check(self, step: Step, *, actors: frozenset[str], kind: str) -> None:
        if step.step_idx != self.target_step:
            raise MisappliedInterventionError(
                f"{self.name} is armed at step {self.target_step} but was applied to "
                f"step {step.step_idx}"
            )
        if step.actor not in actors:
            raise MisappliedInterventionError(
                f"{self.name} needs {kind} step; step {step.step_idx} is a {step.actor} step"
            )


# ---- response interventions -------------------------------------------------


@dataclass(frozen=True)
class ReplaceToolResult(InterventionBase):
    """Show the agent a different tool result. The world is untouched."""

    step: int
    new_result: Mapping[str, Any]

    name: ClassVar[str] = "replace_tool_result"

    @property
    def target_step(self) -> int:
        return self.step

    def fields(self) -> dict[str, Any]:
        return {"step": self.step, "new_result": dict(self.new_result)}

    def describe(self) -> str:
        shown = _shorten(self.new_result.get("content"))
        return f"tool result replaced at step {self.step} · {shown}"

    def apply(self, step: Step, payload: Any) -> Any:
        self._check(step, actors=frozenset({"tool"}), kind="a tool")
        return _merged(payload, self.new_result)


@dataclass(frozen=True)
class TruthfulToolResult(InterventionBase):
    """Show the agent what the tool *really* answers at this step.

    The label-free fix: re-execute the recorded tool call against the
    state the step ran on and serve that. At a planted fault it equals the
    oracle (the original result); anywhere else on a deterministic domain
    it equals the recording, so applying it to an innocent step is a
    no-op — which is what makes it usable when no label exists.

    The re-execution itself is domain work, so it arrives as a
    `TruthProvider`. The resolver is not part of the identity: two
    `TruthfulToolResult(k)` are the same intervention however the truth
    was obtained.
    """

    step: int
    truth: TruthProvider | None = field(default=None, compare=False, repr=False)

    name: ClassVar[str] = "truthful_tool_result"

    @property
    def target_step(self) -> int:
        return self.step

    def with_truth(self, truth: TruthProvider) -> TruthfulToolResult:
        """A copy that knows how to re-execute the step."""
        return TruthfulToolResult(step=self.step, truth=truth)

    def fields(self) -> dict[str, Any]:
        return {"step": self.step}

    def describe(self) -> str:
        return f"tool re-executed truthfully at step {self.step}"

    def apply(self, step: Step, payload: Any) -> Any:
        self._check(step, actors=frozenset({"tool"}), kind="a tool")
        if self.truth is None:
            raise UnresolvedInterventionError(
                f"{self.name} at step {self.step} has no truth provider; it cannot "
                "guess what the tool would have answered"
            )
        return _merged(payload, self.truth(step))


@dataclass(frozen=True)
class ForceAction(InterventionBase):
    """Make the agent say or call something it did not.

    Exactly one of `message` (text to the other party) and `tool_call` is
    set: tau2 rejects a message carrying both
    (`Orchestrator._check_communication_error`).
    """

    step: int
    message: str | None = None
    tool_call: Mapping[str, Any] | None = None

    name: ClassVar[str] = "force_action"

    def __post_init__(self) -> None:
        if (self.message is None) == (self.tool_call is None):
            raise ValueError(
                "ForceAction takes exactly one of message or tool_call: an agent turn "
                "carries text or tool calls, never both"
            )

    @property
    def target_step(self) -> int:
        return self.step

    def fields(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "message": self.message,
            "tool_call": None if self.tool_call is None else dict(self.tool_call),
        }

    def describe(self) -> str:
        if self.message is not None:
            return f"action forced at step {self.step} · says {_shorten(self.message)}"
        assert self.tool_call is not None
        return f"action forced at step {self.step} · calls {self.tool_call.get('name')}"

    def apply(self, step: Step, payload: Any) -> Any:
        self._check(step, actors=_LLM_ACTORS, kind="an agent/user/evaluator")
        choice = dict(payload["choices"][0])
        choice["message"] = self._message()
        return {**payload, "choices": [choice, *payload["choices"][1:]]}

    def _message(self) -> dict[str, Any]:
        if self.message is not None:
            return {"role": "assistant", "content": self.message}
        assert self.tool_call is not None
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": self.tool_call.get("id", "forced"),
                    "type": "function",
                    "function": {
                        "name": self.tool_call["name"],
                        "arguments": json.dumps(dict(self.tool_call.get("arguments") or {})),
                    },
                }
            ],
        }


@dataclass(frozen=True)
class Resample(InterventionBase):
    """Change nothing and sample again: bad luck, or bad policy?"""

    step: int

    name: ClassVar[str] = "resample"

    @property
    def target_step(self) -> int:
        return self.step

    def fields(self) -> dict[str, Any]:
        return {"step": self.step}

    def describe(self) -> str:
        return f"resampled at step {self.step} (nothing changed)"

    def apply(self, step: Step, payload: Any) -> Any:
        if step.step_idx != self.target_step:
            raise MisappliedInterventionError(
                f"{self.name} is armed at step {self.target_step} but was applied to "
                f"step {step.step_idx}"
            )
        return LIVE


# ---- request interventions --------------------------------------------------


@dataclass(frozen=True)
class PromptPatch:
    """A find/replace on the system prompt, for a change smaller than a rewrite."""

    find: str
    replace: str

    def applied_to(self, prompt: str) -> str:
        return prompt.replace(self.find, self.replace)

    def matches(self, prompt: str) -> bool:
        return self.find in prompt


@dataclass(frozen=True)
class EditPrompt(InterventionBase):
    """Change the system prompt from `from_step` onward.

    The step itself is resampled — a prompt that changes from k onward
    changes step k's own answer, so the recorded response at k cannot be
    reused — and every live request after it is shaped.
    """

    from_step: int
    new_system_prompt: str | None = None
    patch: PromptPatch | None = None
    model: str | None = None

    name: ClassVar[str] = "edit_prompt"

    def __post_init__(self) -> None:
        if (self.new_system_prompt is None) == (self.patch is None):
            raise ValueError("EditPrompt takes exactly one of new_system_prompt or patch")

    @property
    def target_step(self) -> int:
        return self.from_step

    def fields(self) -> dict[str, Any]:
        return {
            "from_step": self.from_step,
            "new_system_prompt": self.new_system_prompt,
            "patch": None if self.patch is None else {"find": self.patch.find,
                                                      "replace": self.patch.replace},
            "model": self.model,
        }

    def describe(self) -> str:
        what = (
            f"patch {_shorten(self.patch.find)} -> {_shorten(self.patch.replace)}"
            if self.patch is not None
            else f"new system prompt {_shorten(self.new_system_prompt)}"
        )
        scope = "" if self.model is None else f" for {self.model}"
        return f"prompt edited from step {self.from_step}{scope} · {what}"

    def apply(self, step: Step, payload: Any) -> Any:
        _check_step_only(self, step)
        return LIVE

    def shape_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.model is not None and request.get("model") != self.model:
            return dict(request)
        messages = list(request.get("messages") or [])
        edited = [self._edit(message) for message in messages]
        if self.patch is not None and edited == messages:
            raise ValueError(
                f"EditPrompt patch {self.patch.find!r} matched no system prompt in this "
                "request; a patch that changes nothing is a silently empty intervention"
            )
        return {**request, "messages": edited}

    def _edit(self, message: Any) -> Any:
        if not isinstance(message, Mapping) or message.get("role") != "system":
            return message
        if self.new_system_prompt is not None:
            return {**message, "content": self.new_system_prompt}
        assert self.patch is not None
        content = message.get("content") or ""
        return {**message, "content": self.patch.applied_to(content)}


@dataclass(frozen=True)
class SwapModel(InterventionBase):
    """Run a different model from `from_step` onward.

    `replaces` scopes the swap to one participant (tau2 gives the agent,
    the user simulator and the judge different model ids); left unset,
    every live request is swapped.
    """

    from_step: int
    model: str
    replaces: str | None = None

    name: ClassVar[str] = "swap_model"

    @property
    def target_step(self) -> int:
        return self.from_step

    def fields(self) -> dict[str, Any]:
        return {"from_step": self.from_step, "model": self.model, "replaces": self.replaces}

    def describe(self) -> str:
        replaced = self.replaces or "every participant"
        return f"model swapped from step {self.from_step} · {replaced} -> {self.model}"

    def apply(self, step: Step, payload: Any) -> Any:
        _check_step_only(self, step)
        return LIVE

    def shape_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.replaces is not None and request.get("model") != self.replaces:
            return dict(request)
        return {**request, "model": self.model}


def _check_step_only(intervention: InterventionBase, step: Step) -> None:
    if step.step_idx != intervention.target_step:
        raise MisappliedInterventionError(
            f"{intervention.name} is armed at step {intervention.target_step} but was "
            f"applied to step {step.step_idx}"
        )


# ---- shared helpers ---------------------------------------------------------


def _merged(payload: Any, replacement: Mapping[str, Any]) -> dict[str, Any]:
    """`replacement` over `payload`, keeping the live call's identity fields."""
    merged = {**dict(payload), **dict(replacement)}
    for key in IDENTITY_FIELDS:
        if key in payload:
            merged[key] = payload[key]
    return merged


def shaped_completion(
    intervention: Any, completion: Callable[..., Any]
) -> Callable[..., Any]:
    """`completion`, with `intervention`'s request shaping applied to every call.

    Returned unchanged for an intervention that only changes responses, so
    a caller can wire this in unconditionally.
    """
    if not isinstance(intervention, RequestShaper):
        return completion

    def call(**kwargs: Any) -> Any:
        return completion(**intervention.shape_request(kwargs))

    return call


_REGISTRY: dict[str, Callable[[dict[str, Any]], Any]] = {
    ReplaceToolResult.name: lambda f: ReplaceToolResult(
        step=f["step"], new_result=f["new_result"]
    ),
    TruthfulToolResult.name: lambda f: TruthfulToolResult(step=f["step"]),
    ForceAction.name: lambda f: ForceAction(
        step=f["step"], message=f.get("message"), tool_call=f.get("tool_call")
    ),
    Resample.name: lambda f: Resample(step=f["step"]),
    EditPrompt.name: lambda f: EditPrompt(
        from_step=f["from_step"],
        new_system_prompt=f.get("new_system_prompt"),
        patch=None if f.get("patch") is None else PromptPatch(**f["patch"]),
        model=f.get("model"),
    ),
    SwapModel.name: lambda f: SwapModel(
        from_step=f["from_step"], model=f["model"], replaces=f.get("replaces")
    ),
}


def from_ref(ref: Mapping[str, Any]) -> Any:
    """Rebuild an intervention from `to_ref()`. Raises on an unknown name."""
    name = ref.get("name")
    build = _REGISTRY.get(str(name))
    if build is None:
        raise ValueError(f"unknown intervention {name!r}; known: {sorted(_REGISTRY)}")
    return build(dict(ref.get("fields") or {}))
