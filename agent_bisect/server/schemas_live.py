"""Live snapshot / SSE response models (page group 5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


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
    """A long-running job's status. `state` and `progress`/`started_at`/
    `finished_at`/`error` must agree -- a job can't be "queued" with 77%
    progress, or "done" without a `finished_at` -- enforced below rather
    than left to whoever constructs one (the fixture simulator, or a
    parsed real-mode `runs/<phase>/status.json`) to get right by hand.

    Every field past `state` is optional/nullable: fixture mode always
    fills what a real job of that kind plausibly would; real mode reports
    exactly what the job's own status file says, `None` for anything it
    doesn't -- never invented.
    """

    model_config = ConfigDict(frozen=True)

    job_id: str
    kind: str
    progress: float
    """0..1."""
    state: Literal["queued", "running", "done", "failed"]
    phase: str | None = None
    """E.g. "P1", "P3", "P5"."""
    label: str | None = None
    """E.g. "planted-fault collection"."""
    items_done: int | None = None
    items_total: int | None = None
    model: str | None = None
    calls_spent: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    eta_seconds: float | None = None
    last_checkpoint_at: str | None = None
    error: str | None = None
    """Set only when `state == "failed"`."""

    @model_validator(mode="after")
    def _check_state_agrees_with_progress_and_timestamps(self) -> JobStatus:
        if self.state == "queued":
            if self.progress != 0.0:
                raise ValueError(f"queued job must have progress=0.0, got {self.progress}")
            if self.started_at is not None:
                raise ValueError("queued job must not have started_at set")
        elif self.state == "running":
            if not 0.0 < self.progress < 1.0:
                raise ValueError(
                    f"running job must have 0 < progress < 1, got {self.progress}"
                )
        elif self.state == "done":
            if self.progress != 1.0:
                raise ValueError(f"done job must have progress=1.0, got {self.progress}")
            if self.finished_at is None:
                raise ValueError("done job must have finished_at set")
        elif self.state == "failed" and self.error is None:
            raise ValueError("failed job must have an error message")
        return self


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
