"""`Tau2Snapshotter`: a `core.snapshot.Snapshotter` over a live tau2 `Environment`.

## Capture

`capture()` dumps the full DB state as canonical, JSON-native data via
each toolkit's `db.model_dump(mode="json")` -- the agent-side db
(`environment.tools.db`) always, and the user-side db
(`environment.user_tools.db`) too, when the domain has a separate one
(airline and retail, tau2's currently vendored domains, don't -- see
`tau2.domains.airline.environment.get_environment` /
`tau2.domains.retail.environment.get_environment`, neither of which
passes `user_tools`).

## Restore

`restore()` reconstructs a fresh db instance with
`type(current_db).model_validate(captured_state)` and assigns it directly
onto the toolkit(s), rather than going through
`Environment.set_state()`/`ToolKitBase.update_db()`. Those replay a
message history / dict-merge a patch onto the *existing* db
(`tau2.utils.pydantic_utils.update_pydantic_model_with_dict` does
`AddictDict(current).update(AddictDict(patch))`, which only adds or
overwrites keys present in the patch -- it never removes a key the
current db has and the patch doesn't). Airline's own tools mutate that
way: `book_reservation` adds a new key to `db.reservations`, and paying
with a certificate pops a key from `user.payment_methods`
(`tau2.domains.airline.tools.AirlineTools.book_reservation`). A merge-based
restore to a state *before* such a call would leave the added key in
place (or the popped one restored) -- wrong. Building a whole new model
instance from the captured JSON and assigning it is the only way to get
an exact restore; it's also literally how `DB.load()` itself works
(`tau2.environment.db.DB.load`: `cls.model_validate(data)`), just without
the round trip through a file.

## Hash

`state_hash()` delegates to `Environment.get_db_hash()` (tau2's own
`get_dict_hash(self.tools.db.model_dump())`) instead of hashing this
module's own captured JSON, so a restored state's hash is always directly
comparable to whatever tau2 itself reports for a live run -- the
comparison a step's `state_hash` field exists to make possible.

## Typing

`Tau2Snapshotter` is typed against `_Tau2EnvironmentLike`, a `Protocol`
capturing only the four members this module actually touches
(`tools`/`user_tools`/`get_db_hash`/`sync_tools`), rather than the
concrete `tau2.environment.environment.Environment` class. A real
`Environment` satisfies it structurally with no changes needed on tau2's
side, and it lets tests exercise this module's logic against a small fake
without importing tau2 at all.
"""

from __future__ import annotations

from typing import Any, Protocol


class _ToolkitLike(Protocol):
    db: Any


class _Tau2EnvironmentLike(Protocol):
    # Declared as read-only properties (covariant), not plain attributes
    # (invariant), because this module only ever reads `environment.tools`/
    # `.user_tools` -- it mutates `.db` on what they return, never
    # `environment.tools` itself. Covariance is what lets a fake whose
    # `tools` happens to be typed as a concrete subclass (not `_ToolkitLike`
    # itself) satisfy this protocol structurally.
    @property
    def tools(self) -> _ToolkitLike | None: ...
    @property
    def user_tools(self) -> _ToolkitLike | None: ...

    def get_db_hash(self) -> str | None: ...
    def sync_tools(self) -> None: ...


class Tau2StateUnavailableError(Exception):
    """Raised when the environment has no agent-side db to snapshot or hash."""


class Tau2Snapshotter:
    """Snapshotter over one live tau2 `Environment`'s DB(s)."""

    def __init__(self, environment: _Tau2EnvironmentLike) -> None:
        self._environment = environment

    def capture(self) -> dict[str, Any]:
        tools = self._environment.tools
        if tools is None or tools.db is None:
            raise Tau2StateUnavailableError("environment.tools.db is not set")
        user_tools = self._environment.user_tools
        user_db = user_tools.db if user_tools is not None else None
        shares_agent_db = user_db is not None and user_db is tools.db
        return {
            "agent_db": tools.db.model_dump(mode="json"),
            "user_db": (
                None if user_db is None or shares_agent_db else user_db.model_dump(mode="json")
            ),
        }

    def restore(self, state: dict[str, Any]) -> None:
        tools = self._environment.tools
        if tools is None or tools.db is None:
            raise Tau2StateUnavailableError("environment.tools.db is not set")

        agent_db_class = type(tools.db)
        tools.db = agent_db_class.model_validate(state["agent_db"])

        user_tools = self._environment.user_tools
        if user_tools is not None:
            if state.get("user_db") is not None:
                current_user_db = user_tools.db
                if current_user_db is None:
                    raise Tau2StateUnavailableError("environment.user_tools.db is not set")
                user_db_class = type(current_user_db)
                user_tools.db = user_db_class.model_validate(state["user_db"])
            else:
                # No separately-captured user db means the domain shared one
                # db instance between tools and user_tools at capture time
                # (see Environment.set_state's own sync-after-update_db
                # comment) -- restore that invariant too.
                user_tools.db = tools.db

        self._environment.sync_tools()

    def state_hash(self) -> str:
        db_hash = self._environment.get_db_hash()
        if db_hash is None:
            raise Tau2StateUnavailableError("environment.get_db_hash() returned None")
        return db_hash
