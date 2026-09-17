"""Live snapshot / SSE response models (page group 5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CallsPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: str
    model: str
    calls_per_minute: float


class BudgetStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    used: int
    cap: int | None


class RateLimitStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    limiter_rpm: int
    current_rpm: float
    headroom_rpm: float


class JobStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    kind: str
    progress: float
    """0..1."""
    state: Literal["queued", "running", "done", "failed"]


class LiveEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: str
    level: Literal["info", "warn", "error"]
    message: str


class LiveSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    calls_series: tuple[CallsPoint, ...]
    budget: BudgetStatus
    rate_limit: RateLimitStatus
    jobs: tuple[JobStatus, ...]
    events: tuple[LiveEvent, ...]
