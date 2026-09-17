"""`JobStatus` invariants: state and progress/started_at/finished_at/error
must agree -- a job can't be "queued" with 77% progress, or "done" without
a finished_at. Enforced by a pydantic validator so no caller (the fixture
simulator or a parsed real-mode status.json) can construct an impossible
one."""

from __future__ import annotations

from typing import Any

import pytest
from agent_bisect.server.schemas_live import JobStatus
from pydantic import ValidationError


def _job(**overrides: Any) -> JobStatus:
    base: dict[str, Any] = {
        "job_id": "job-1",
        "kind": "record",
        "progress": 0.0,
        "state": "queued",
    }
    base.update(overrides)
    return JobStatus(**base)


def test_queued_must_have_zero_progress():
    with pytest.raises(ValidationError):
        _job(state="queued", progress=0.77)


def test_queued_must_have_no_started_at():
    with pytest.raises(ValidationError):
        _job(state="queued", progress=0.0, started_at="2026-09-17T09:00:00Z")


def test_queued_valid_combo_constructs():
    job = _job(state="queued", progress=0.0)
    assert job.started_at is None


def test_running_progress_must_be_strictly_between_zero_and_one():
    with pytest.raises(ValidationError):
        _job(state="running", progress=0.0, started_at="2026-09-17T09:00:00Z")
    with pytest.raises(ValidationError):
        _job(state="running", progress=1.0, started_at="2026-09-17T09:00:00Z")


def test_running_valid_combo_constructs():
    job = _job(state="running", progress=0.5, started_at="2026-09-17T09:00:00Z")
    assert job.progress == 0.5


def test_done_must_have_full_progress():
    with pytest.raises(ValidationError):
        _job(
            state="done",
            progress=0.9,
            started_at="2026-09-17T09:00:00Z",
            finished_at="2026-09-17T09:05:00Z",
        )


def test_done_must_have_finished_at():
    with pytest.raises(ValidationError):
        _job(state="done", progress=1.0, started_at="2026-09-17T09:00:00Z", finished_at=None)


def test_done_valid_combo_constructs():
    job = _job(
        state="done",
        progress=1.0,
        started_at="2026-09-17T09:00:00Z",
        finished_at="2026-09-17T09:05:00Z",
    )
    assert job.finished_at == "2026-09-17T09:05:00Z"


def test_failed_must_have_an_error_message():
    with pytest.raises(ValidationError):
        _job(state="failed", progress=0.4, started_at="2026-09-17T09:00:00Z", error=None)


def test_failed_valid_combo_constructs():
    job = _job(
        state="failed",
        progress=0.4,
        started_at="2026-09-17T09:00:00Z",
        error="upstream returned a 500",
    )
    assert job.error == "upstream returned a 500"
