"""The `Snapshotter` protocol and an in-memory fake implementation.

`core/` never imports `tau2` (or `attribution`/`bench`/`gate` -- see the
import-linter contract in `pyproject.toml`), so the tau2-specific
snapshotter (`Tau2Snapshotter`, capturing/restoring a live tau2
`Environment`'s DB) lives in `adapters/tau2_snapshot.py`, not here. This
module only defines the shape every domain snapshotter must satisfy, plus
`InMemorySnapshotter`, a fake used by core-level tests (and by anything
building/testing the replay engine before a real adapter is wired in).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from agent_bisect.core.store import canonical_json_bytes, sha256_hex


@runtime_checkable
class Snapshotter(Protocol):
    """World-state capture/restore/hash for one run's replay engine.

    A domain adapter implements this over whatever "world state" means
    for that domain (a tau2 `Environment`'s DB, a mocked external
    service, ...). The replay engine (`core.replay`, `core.runner`) only
    ever talks to a `Snapshotter`, never to the domain directly.
    """

    def capture(self) -> Any:
        """Return a JSON-able snapshot of the current world state."""
        ...

    def restore(self, state: Any) -> None:
        """Replace the current world state with a previously captured one."""
        ...

    def state_hash(self) -> str:
        """A stable hash of the current world state, checked after every restore."""
        ...


class InMemorySnapshotter:
    """A `Snapshotter` fake over a plain JSON-able value, for tests.

    `capture`/`restore` deep-copy on the way in and out, so a caller
    mutating a value it got from `capture()` (or is about to pass to
    `restore()`) can never reach back into this snapshotter's internal
    state. `state_hash` is the sha256 of the state's canonical JSON form.
    """

    def __init__(self, initial_state: Any = None) -> None:
        self._state: Any = deepcopy(initial_state) if initial_state is not None else {}

    def capture(self) -> Any:
        return deepcopy(self._state)

    def restore(self, state: Any) -> None:
        self._state = deepcopy(state)

    def state_hash(self) -> str:
        return sha256_hex(canonical_json_bytes(self._state))
