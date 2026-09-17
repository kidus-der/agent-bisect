"""FastAPI dependency plumbing and the shared envelope helpers every route module uses."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from agent_bisect.server.repository import DashboardRepository, DataNotAvailable
from agent_bisect.server.schemas_common import Envelope, ResponseMeta, failed, ok
from agent_bisect.server.schemas_meta import NotAvailable

# Path-parameter ids: letters, digits, dash, underscore only -- rejects anything
# that could be a path-traversal or injection attempt before it reaches a
# repository lookup (which itself only ever does a dict/parameterized-SQL
# lookup, but validating at the boundary is the rule regardless).
ID_PATTERN = r"^[A-Za-z0-9_-]+$"
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
_SORT_PATTERN = r"^-?[A-Za-z_]+$"


def get_repository(request: Request) -> DashboardRepository:
    """The single `DashboardRepository` built once in `create_app`, stashed on `app.state`."""
    return request.app.state.repository


# A module-level singleton, per ruff B008: `Depends(...)` in a parameter default
# calls `Depends` at import time either way, but reusing one instance across
# every route avoids re-constructing an (identical) dependency object per route
# declaration and is the pattern ruff's B008 message itself suggests.
RepoDep = Depends(get_repository)


def base_meta(repository: DashboardRepository, **extra: object) -> ResponseMeta:
    source = repository.data_source()
    return ResponseMeta(simulated=source == "fixture", data_source=source, **extra)  # type: ignore[arg-type]


def envelope_ok[T](data: T, repository: DashboardRepository, **meta_extra: object) -> Envelope[T]:
    return ok(data, base_meta(repository, **meta_extra))


def not_found(repository: DashboardRepository, message: str) -> HTTPException:
    payload = failed("not_found", message, base_meta(repository)).model_dump(mode="json")
    return HTTPException(status_code=404, detail=payload)


def not_available_envelope(repository: DashboardRepository, reason: str) -> Envelope[NotAvailable]:
    """A 200 envelope whose `data` is a typed `NotAvailable` -- the query was understood."""
    return ok(NotAvailable(reason=reason), base_meta(repository))


def call_or_not_available(fn):
    """Run a zero-arg repository call, turning `DataNotAvailable` into a typed envelope value."""
    try:
        return fn()
    except DataNotAvailable as exc:
        return NotAvailable(reason=exc.reason)
