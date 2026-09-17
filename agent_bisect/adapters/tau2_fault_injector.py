"""A planted fault that stays planted: one tool call that always lies.

`docs/decisions/0016-persistent-planted-fault.md`. A one-shot replaced
tool result lives only in the recording, so a fork taken before the
planted step re-executes the tool live, gets the truth, and passes — and
the pre-registered *shared* control then measures the base run instead of
the failure, collapsing every effect to zero.

So the fault is installed in the world instead. A `FaultInjector` wraps
`Environment.get_response`, matches exactly one call by
`(tool_name, canonical tool_args)`, and replaces what that call *returns*
with the recorded mutation — every time it executes, for as long as the
run lasts. Everything else passes through untouched, and the **database
is never touched**: the tool really runs, really writes whatever it
writes, and only its answer is corrupted. That is what keeps the oracle
fix well defined ("the original tool result") and the fault one of
perception.

Install it **before** the recorder or the replayer wraps `get_response`,
so the recorder records what the agent was actually shown and a live
suffix reaches it. The spec travels in the faulted run's manifest
`params`, so any later fork or replay reconstructs the same world from
the tape alone.

`attribution.TruthfulToolResult` is unaffected: `tau2_truth` re-executes
on a clean environment of its own, which never carries an injector.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from agent_bisect.adapters.tau2 import wrap_tool_execution
from agent_bisect.core.store import canonical_json_bytes, sha256_hex

#: Where the spec rides in a run manifest's free-form `params`.
MANIFEST_KEY = "fault_injector"


@dataclass(frozen=True)
class FaultSpec:
    """Which call lies, and what it says instead. Serialisable, deterministic."""

    tool_name: str
    tool_args: Mapping[str, Any]
    #: What the call returns instead: the mutated content and error flag.
    content: str
    error: bool = False
    #: The label: the first occurrence of this call in the base run.
    step_idx: int = 0
    fault_type: str = ""

    @property
    def call_key(self) -> str:
        """`(tool, canonical args)` as one comparable string."""
        return canonical_json_bytes(
            {"tool": self.tool_name, "args": dict(self.tool_args)}
        ).decode("utf-8")

    @property
    def fault_hash(self) -> str:
        """Stable identity of this fault, for the manifest and the dataset card."""
        return sha256_hex(canonical_json_bytes(self.as_dict()))

    def matches(self, tool_name: str, tool_args: Mapping[str, Any] | None) -> bool:
        return (
            tool_name == self.tool_name and dict(tool_args or {}) == dict(self.tool_args)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_args": dict(self.tool_args),
            "content": self.content,
            "error": self.error,
            "step_idx": self.step_idx,
            "fault_type": self.fault_type,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FaultSpec:
        return cls(
            tool_name=str(data["tool_name"]),
            tool_args=dict(data.get("tool_args") or {}),
            content=str(data["content"]),
            error=bool(data.get("error", False)),
            step_idx=int(data.get("step_idx", 0)),
            fault_type=str(data.get("fault_type", "")),
        )

    @classmethod
    def from_mutation(
        cls,
        *,
        tool_name: str,
        tool_args: Mapping[str, Any],
        mutated: Mapping[str, Any],
        step_idx: int,
        fault_type: str,
    ) -> FaultSpec:
        """The standing fault equivalent to one `ReplaceToolResult` payload."""
        return cls(
            tool_name=tool_name,
            tool_args=dict(tool_args),
            content=str(mutated.get("content") or ""),
            error=bool(mutated.get("error", False)),
            step_idx=step_idx,
            fault_type=fault_type,
        )


class FaultInjector:
    """Corrupts one call's answer, every time that call is executed."""

    def __init__(self, spec: FaultSpec) -> None:
        self._spec = spec
        self.hits = 0
        self.executions = 0

    @property
    def spec(self) -> FaultSpec:
        return self._spec

    def respond(self, original: Any, tool_call: Any) -> Any:
        """The `get_response` wrapper. The tool still runs; its answer does not.

        A call that already failed is left alone: the fault corrupts an
        *answer*, and a failure is the absence of one. That also makes the
        injector independent of where it sits relative to a flaky world —
        a transient failure stays a transient failure either way.
        """
        message = original(tool_call)
        self.executions += 1
        if message.error and not self._spec.error:
            return message
        if not self._spec.matches(tool_call.name, getattr(tool_call, "arguments", None)):
            return message
        self.hits += 1
        return message.model_copy(
            update={"content": self._spec.content, "error": self._spec.error}
        )


@contextmanager
def fault_injected(environment: Any, spec: FaultSpec) -> Iterator[FaultInjector]:
    """Install `spec` on `environment` for the duration.

    Enter this before the recorder or the replayer wraps `get_response`:
    their wrapper then sits outside this one and records, or serves, the
    corrupted answer rather than the true one.
    """
    injector = FaultInjector(spec)
    with wrap_tool_execution(environment, injector.respond):
        yield injector


# ---- carrying the fault in a run manifest -----------------------------------


def with_injector(params: Mapping[str, Any] | None, spec: FaultSpec) -> dict[str, Any]:
    """`params` plus the fault, for a faulted run's manifest."""
    return {**dict(params or {}), MANIFEST_KEY: spec.as_dict()}


def injector_spec_from(params: Mapping[str, Any] | None) -> FaultSpec | None:
    """The fault a run was made under, or `None` for an ordinary run."""
    recorded = (params or {}).get(MANIFEST_KEY)
    if not isinstance(recorded, Mapping):
        return None
    return FaultSpec.from_dict(recorded)


@contextmanager
def restored_fault(environment: Any, params: Mapping[str, Any] | None) -> Iterator[Any]:
    """Re-install whatever fault this run's manifest records, if any.

    What every consumer of a dataset item — a P5 fork, the P3 gate's
    replay, the PR check — uses, so the item's world is the world it was
    recorded in.
    """
    spec = injector_spec_from(params)
    if spec is None:
        yield None
        return
    with fault_injected(environment, spec) as injector:
        yield injector
