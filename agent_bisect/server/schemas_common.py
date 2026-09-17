"""Shared response envelope and meta types for every JSON endpoint.

`server/` imports `core/` and `attribution/` but is never imported by them
(`core/` and `attribution/` must never import `server/`). This module is
imported by every route module and by `repository.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

DataSource = Literal["fixture", "real"]


class ErrorInfo(BaseModel):
    """Machine-readable error detail. Never carries a path or secret."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class ResponseMeta(BaseModel):
    """Envelope metadata. `simulated` is `True` for every fixture-backed response."""

    model_config = ConfigDict(frozen=True)

    simulated: bool
    data_source: DataSource
    total: int | None = None
    page: int | None = None
    limit: int | None = None
    next_cursor: str | None = None


class Envelope[T](BaseModel):
    """The response shape every endpoint in `agent_bisect.server` returns."""

    model_config = ConfigDict(frozen=True)

    success: bool
    data: T | None
    error: ErrorInfo | None
    meta: ResponseMeta


def ok[T](data: T, meta: ResponseMeta) -> Envelope[T]:
    """Build a successful envelope."""
    return Envelope[T](success=True, data=data, error=None, meta=meta)


def failed(code: str, message: str, meta: ResponseMeta) -> Envelope[None]:
    """Build a failed envelope. `message` must never leak a filesystem path or secret."""
    error = ErrorInfo(code=code, message=message)
    return Envelope[None](success=False, data=None, error=error, meta=meta)
