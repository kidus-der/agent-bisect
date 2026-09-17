"""Forking a run with a standing fault installed in its world.

Two things have to happen for a planted fault to survive
(`docs/decisions/0016-persistent-planted-fault.md`):

1. the fault is installed on the environment **before** the recorder and
   the replayer wrap `get_response`, so the tape records what the agent
   was shown rather than what the tool really said. That is exactly what
   `Tau2ForkDriver`'s `environment_hook` is for;
2. the fault is written into the forked run's **manifest**, so any later
   fork or replay of that item rebuilds the same world from the tape
   alone.

The driver builds the fork's manifest itself, with `fork_manifest`, which
copies the *parent's* `params`. So the second half is done by handing the
driver a reader that reports the parent with the fault already in its
params: the fork inherits it, the parent on disk is untouched, and
`core/` needs no change at all.

This file used to be a second fork driver. It is now a factory over the
real one — `FaultedForkDriver(...)` returns a `Tau2ForkDriver` and is
call-compatible with what it replaced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_bisect.adapters.tau2_fault_injector import FaultSpec, fault_injected, with_injector
from agent_bisect.adapters.tau2_replay import Tau2ForkDriver
from agent_bisect.core.runner import ForkSpec
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import RunManifest, TapeReader, TapeWriter


class _FaultedReader(TapeReader):
    """A tape reader that reports one run as carrying a standing fault.

    Only `get_manifest` differs, and only in `params`. Nothing on disk
    changes: the base run really was recorded without the fault, and it
    is the *fork* that must remember being made with one.
    """

    def __init__(self, root: Any, fault: FaultSpec) -> None:
        super().__init__(root)
        self._fault = fault

    def get_manifest(self, run_id: str) -> RunManifest:
        manifest = super().get_manifest(run_id)
        return manifest.model_copy(
            update={"params": with_injector(manifest.params, self._fault)}
        )


def FaultedForkDriver(  # noqa: N802 - kept as a name so callers read as constructors
    spec: ForkSpec,
    *,
    store: BlobStore,
    reader: TapeReader,
    tape: TapeWriter,
    live_completion: Callable[..., Any],
    fault: FaultSpec | None = None,
    unsafe_positional: bool = False,
) -> Tau2ForkDriver:
    """A `Tau2ForkDriver` whose world carries `fault`, and whose fork records it.

    With `fault=None` it is a plain `Tau2ForkDriver`.
    """
    if fault is None:
        return Tau2ForkDriver(
            spec,
            store=store,
            reader=reader,
            tape=tape,
            live_completion=live_completion,
            unsafe_positional=unsafe_positional,
        )
    return Tau2ForkDriver(
        spec,
        store=store,
        reader=_FaultedReader(store.root, fault),
        tape=tape,
        live_completion=live_completion,
        unsafe_positional=unsafe_positional,
        environment_hook=lambda environment: fault_injected(environment, fault),
    )
