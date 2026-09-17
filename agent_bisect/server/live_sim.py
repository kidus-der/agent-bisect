"""A seeded, wall-clock-driven traffic simulator for the Live page in fixture mode.

Not part of `agent_bisect.server.fixtures` (which builds the static, byte-
deterministic run/benchmark/PR-check dataset): this module intentionally
changes from one call to the next, driven by the current time bucketed to
the minute/second, so the Live page has something to animate. Every
snapshot it produces is still only ever served with `meta.simulated = true`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import numpy as np

from agent_bisect.server.schemas_live import (
    BudgetStatus,
    CallsPoint,
    JobStatus,
    LiveEvent,
    LiveSnapshot,
    RateLimitStatus,
)

_MODELS = ("nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.3-70b-instruct")
_WINDOW_MINUTES = 30
_LIMITER_RPM = 40
_BUDGET_CAP = 12000
_JOB_KINDS = ("blame", "eval", "record")


def _stable_hash(text: str) -> int:
    """`hash()`-free digest: `hash()` on `str` is per-process salted, `int.from_bytes` isn't."""
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=4).digest(), "big")


def _minute_rng(seed: int, minute_bucket: int, *extra: str) -> np.random.Generator:
    return np.random.default_rng([seed, minute_bucket, *(_stable_hash(e) for e in extra)])


class LiveSimulator:
    """Deterministic-per-minute, evolving-over-time fixture-mode live snapshot."""

    def __init__(self, seed: int) -> None:
        self._seed = seed

    def snapshot(self, now: datetime | None = None) -> LiveSnapshot:
        now = now or datetime.now(UTC)
        minute = int(now.timestamp() // 60)

        series = []
        for offset in range(_WINDOW_MINUTES, 0, -1):
            bucket_minute = minute - offset
            ts = (now - timedelta(minutes=offset)).replace(second=0, microsecond=0).isoformat()
            for model in _MODELS:
                rng = _minute_rng(self._seed, bucket_minute, model)
                series.append(
                    CallsPoint(
                        ts=ts, model=model, calls_per_minute=round(float(rng.uniform(2, 35)), 1)
                    )
                )

        rng_now = _minute_rng(self._seed, minute, "now")
        current_rpm = round(float(rng_now.uniform(5, _LIMITER_RPM - 2)), 1)
        used = int(rng_now.integers(500, _BUDGET_CAP))
        jobs = tuple(
            JobStatus(
                job_id=f"job-{i}",
                kind=_JOB_KINDS[i % len(_JOB_KINDS)],
                progress=round(float((minute * 7 + i * 13) % 100) / 100, 2),
                state=("running", "queued", "done")[(minute + i) % 3],
            )
            for i in range(3)
        )
        events = tuple(
            LiveEvent(
                ts=(now - timedelta(seconds=15 * i)).isoformat(),
                level=("info", "info", "warn")[i % 3],
                message=(
                    f"simulated: {_JOB_KINDS[i % len(_JOB_KINDS)]} "
                    f"batch {minute - i} progressed"
                ),
            )
            for i in range(5)
        )

        return LiveSnapshot(
            calls_series=tuple(series),
            budget=BudgetStatus(used=used, cap=_BUDGET_CAP),
            rate_limit=RateLimitStatus(
                limiter_rpm=_LIMITER_RPM,
                current_rpm=current_rpm,
                headroom_rpm=round(_LIMITER_RPM - current_rpm, 1),
            ),
            jobs=jobs,
            events=events,
        )
