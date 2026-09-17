"""Serving a recorded run back: `TapeCursor`, `TapeLLM`, `TapeTools`, and
the `Intervention` protocol.

The rule this module exists to enforce is rule 3 of
`docs/brief/summary.md` §3: **divergence is an error, never a silent live
fallback** ("that is how replay tools silently lie"). Nothing here can
reach the network, and no method has a "fall back to a real call" branch —
the only outcome of a mismatch is `DivergenceError`, naming the step.

One cursor is shared by `TapeLLM` and `TapeTools`. That is deliberate: a
tape interleaves LLM and tool steps in the order they happened, so a
replay that makes a tool call where the recording made an agent call is
itself a divergence, and only a shared cursor can see it. A tau2
simulation is strictly sequential within itself
(`tau2.orchestrator.orchestrator.Orchestrator.run`), so a single position
is well defined.

`core/` never imports tau2 (nor `attribution`/`bench`/`gate`), so payloads
here are plain JSON-able values: the caller supplies a `load_json`
callable (in practice `BlobStore.get_json`) and the tau2-specific
rehydration of a payload into a provider response object lives in
`adapters/tau2_replay.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_bisect.core.config import redact
from agent_bisect.core.store import canonical_json_bytes
from agent_bisect.core.tape import Actor, Step, canonical_request_hash

#: Actors whose steps are LLM calls rather than tool executions.
LLM_ACTORS: frozenset[str] = frozenset({"agent", "user", "evaluator"})
#: Longest value rendered into a divergence diff, per side.
DIFF_VALUE_CHARS = 120
#: Most differing keys named in one diff.
DIFF_MAX_ENTRIES = 4


class DivergenceError(Exception):
    """Replay asked for something the recording does not contain.

    Carries everything needed to explain it without re-reading the tape:
    the step index it happened at, the recorded actor, the expected and
    observed identities (a request hash, a tool name, a state hash), and a
    short redacted diff.
    """

    def __init__(self, *, step_idx: int, actor: str, expected: str, got: str, diff: str) -> None:
        self.step_idx = step_idx
        self.actor = actor
        self.expected = expected
        self.got = got
        self.diff = diff
        super().__init__(
            f"replay diverged at step {step_idx} (actor {actor}): "
            f"expected {expected}, got {got}. {diff}"
        )


class TapeExhaustedError(DivergenceError):
    """Replay made a call the recording has no step for.

    A `DivergenceError` subclass because it means the same thing: the run
    being replayed is not the run that was recorded.
    """


def _render(value: Any) -> str:
    text = canonical_json_bytes(value).decode("utf-8")
    if len(text) > DIFF_VALUE_CHARS:
        text = text[:DIFF_VALUE_CHARS] + "…"
    return redact(text)


def _message_diff(expected: Sequence[Any], got: Sequence[Any]) -> list[str]:
    if len(expected) != len(got):
        return [f"messages: {len(expected)} recorded != {len(got)} replayed"]
    return [
        f"messages[{index}]: {_render(old)} != {_render(new)}"
        for index, (old, new) in enumerate(zip(expected, got, strict=True))
        if old != new
    ][:DIFF_MAX_ENTRIES]


def _canonical_parts(request: Mapping[str, Any]) -> dict[str, Any]:
    """The same projection `canonical_request_hash` hashes, key by key."""
    from agent_bisect.core.tape import _SAMPLING_PARAM_KEYS

    parts: dict[str, Any] = {
        "model": request.get("model"),
        "messages": request.get("messages"),
        "tools": request.get("tools"),
    }
    parts.update({key: request[key] for key in _SAMPLING_PARAM_KEYS if key in request})
    return parts


def short_request_diff(
    expected: Mapping[str, Any] | None, got: Mapping[str, Any]
) -> str:
    """A one-line, redacted, truncated account of why two requests differ.

    Compares only what `canonical_request_hash` hashes, so it can never
    blame a field the hash ignores. `expected` is `None` when the recorded
    request blob could not be read, which must still produce a usable
    error rather than a second failure.
    """
    if expected is None:
        return "recorded request unavailable (blob missing)"
    old_parts = _canonical_parts(expected)
    new_parts = _canonical_parts(got)
    entries: list[str] = []
    for key in sorted(set(old_parts) | set(new_parts)):
        old, new = old_parts.get(key), new_parts.get(key)
        if old == new:
            continue
        if key == "messages" and isinstance(old, Sequence) and isinstance(new, Sequence):
            entries.extend(_message_diff(old, new))
        else:
            entries.append(f"{key}: {_render(old)} != {_render(new)}")
    if not entries:
        return "no difference in the hashed fields (hash mismatch without a visible cause)"
    return "; ".join(entries[:DIFF_MAX_ENTRIES])


class TapeCursor:
    """A single position walked through one run's recorded steps."""

    def __init__(self, steps: Sequence[Step]) -> None:
        self._steps = tuple(steps)
        self._position = 0

    @property
    def position(self) -> int:
        """How many steps have been taken — also the index of the next one."""
        return self._position

    @property
    def remaining(self) -> int:
        return len(self._steps) - self._position

    @property
    def at_end(self) -> bool:
        return self._position >= len(self._steps)

    def peek(self) -> Step | None:
        """The next recorded step, or `None` once the tape is spent."""
        return None if self.at_end else self._steps[self._position]

    def take(self, expected_actors: set[str] | frozenset[str]) -> Step:
        """Advance one step, checking it is one of `expected_actors`."""
        if self.at_end:
            raise TapeExhaustedError(
                step_idx=self._position,
                actor="/".join(sorted(expected_actors)),
                expected=f"{len(self._steps)} recorded steps",
                got=f"a {'/'.join(sorted(expected_actors))} call at step {self._position}",
                diff="the tape has no step here; the replayed run is longer than the recording",
            )
        step = self._steps[self._position]
        if step.actor not in expected_actors:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor=step.actor,
                expected=f"actor {step.actor}",
                got=f"actor {'/'.join(sorted(expected_actors))}",
                diff="actor: the recording has a different kind of step here",
            )
        self._position += 1
        return step


class TapeLLM:
    """Serves recorded LLM responses, in order, to requests that match.

    Never makes a call: `load_json` reads a blob, and a request whose
    `canonical_request_hash` differs from the recorded one raises.
    """

    def __init__(self, cursor: TapeCursor, load_json: Callable[[str], Any]) -> None:
        self._cursor = cursor
        self._load_json = load_json
        self._calls_served = 0

    @property
    def calls_served(self) -> int:
        return self._calls_served

    def serve(self, request: Mapping[str, Any]) -> Any:
        """Return the recorded response payload for `request`."""
        step = self._cursor.take(LLM_ACTORS)
        got_hash = canonical_request_hash(dict(request))
        if got_hash != step.request_hash:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor=step.actor,
                expected=str(step.request_hash),
                got=got_hash,
                diff=short_request_diff(self._recorded_request(step), request),
            )
        if step.response_ref is None:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor=step.actor,
                expected="a recorded response",
                got="no response_ref on the step",
                diff="response: the recording is incomplete for this step",
            )
        self._calls_served += 1
        return self._load_json(step.response_ref)

    def _recorded_request(self, step: Step) -> dict[str, Any] | None:
        if step.request_ref is None:
            return None
        try:
            return self._load_json(step.request_ref)
        except Exception:  # noqa: BLE001 - see below
            # Deliberately broad: this is a diagnostic read, and whatever
            # goes wrong in it (a missing blob, a corrupt one, a loader
            # that raises something else entirely) must not replace the
            # DivergenceError it is being built to explain.
            return None


class TapeTools:
    """The tool half of the same cursor.

    Three uses, all on the caller's side: serve a recorded result without
    executing anything (`recorded_result`, the snapshot prefix), restore
    the world the step left behind (`recorded_state_after`), or execute
    for real and assert the recording is reproduced
    (`check_reexecution`, full-run replay).
    """

    def __init__(self, cursor: TapeCursor, load_json: Callable[[str], Any]) -> None:
        self._cursor = cursor
        self._load_json = load_json
        self._steps_served = 0

    @property
    def steps_served(self) -> int:
        return self._steps_served

    def take(self, tool_name: str, tool_args: Mapping[str, Any]) -> Step:
        """Advance to the next tool step, checking it is this call."""
        step = self._cursor.take(frozenset({"tool"}))
        if step.tool_name != tool_name:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor="tool",
                expected=str(step.tool_name),
                got=tool_name,
                diff=f"tool_name: {step.tool_name!r} != {tool_name!r}",
            )
        recorded_args = step.tool_args or {}
        if recorded_args != dict(tool_args):
            raise DivergenceError(
                step_idx=step.step_idx,
                actor="tool",
                expected=_render(recorded_args),
                got=_render(dict(tool_args)),
                diff=f"tool_args: {_render(recorded_args)} != {_render(dict(tool_args))}",
            )
        self._steps_served += 1
        return step

    def recorded_result(self, step: Step) -> Any:
        if step.tool_result_ref is None:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor="tool",
                expected="a recorded tool result",
                got="no tool_result_ref on the step",
                diff="tool_result: the recording is incomplete for this step",
            )
        return self._load_json(step.tool_result_ref)

    def recorded_state_after(self, step: Step) -> Any:
        """The world snapshot this step left behind, for a snapshot restore."""
        return self._load_json(step.state_after)

    def check_reexecution(self, step: Step, result: Any, state_hash: str) -> None:
        """Assert a live re-execution reproduced the recording exactly."""
        recorded = self.recorded_result(step)
        if recorded != result:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor="tool",
                expected=_render(recorded),
                got=_render(result),
                diff=f"tool_result: {_render(recorded)} != {_render(result)}",
            )
        if step.state_hash != state_hash:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor="tool",
                expected=step.state_hash,
                got=state_hash,
                diff=f"state_hash: {step.state_hash} != {state_hash}",
            )


class _LiveSentinel:
    """Return value meaning "do not use the recording; sample live instead"."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "LIVE"


#: What an `Intervention` returns to force a fresh live call at its step
#: (the `Resample` intervention of `docs/brief/summary.md` §3). Concrete
#: interventions land in `attribution/interventions.py` in P3.
LIVE = _LiveSentinel()


@runtime_checkable
class Intervention(Protocol):
    """The one thing changed at the fork step.

    `apply` receives the step as recorded and the payload about to be used
    at it — an LLM response payload for an agent/user step, a tool result
    payload for a tool step — and returns what should be used instead, or
    `LIVE` to sample fresh.
    """

    name: str

    def apply(self, step: Step, payload: Any) -> Any: ...


class NoOpIntervention:
    """Change nothing: the control arm, and what full-run replay uses."""

    name = "noop"

    def apply(self, step: Step, payload: Any) -> Any:
        return payload


def actor_is_llm(actor: Actor) -> bool:
    return actor in LLM_ACTORS
