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

# One simulated lifecycle per job slot: minute 0 = queued, minutes
# 1..CYCLE-2 = running (progress climbs), minute CYCLE-1 = done, then the
# cycle repeats. Staggering each slot's start keeps them from all queuing
# on the same minute. Numbers pulled from the brief's own pre-registered
# quantities, not arbitrary: 20 airline probe tasks, max_n=16, the >=120
# labelled-failure dataset target.
_CYCLE_MINUTES = 12
_SLOT_STAGGER_MINUTES = 4
_FAIL_PROBABILITY = 0.15
_CALLS_PER_ITEM = 8

_JOB_PHASE: dict[str, str] = {"record": "P1", "blame": "P5", "eval": "P5"}
_JOB_LABEL: dict[str, str] = {
    "record": "tau2 run recording",
    "blame": "step-by-step blame search",
    "eval": "baseline evaluation",
}
_JOB_ITEMS_TOTAL: dict[str, int] = {"record": 20, "blame": 16, "eval": 120}


def _stable_hash(text: str) -> int:
    """`hash()`-free digest: `hash()` on `str` is per-process salted, `int.from_bytes` isn't."""
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=4).digest(), "big")


def _minute_rng(seed: int, minute_bucket: int, *extra: str) -> np.random.Generator:
    return np.random.default_rng([seed, minute_bucket, *(_stable_hash(e) for e in extra)])


def _job_status(seed: int, slot: int, now: datetime, minute: int) -> JobStatus:
    """One job slot's status at `now`. State and progress/timestamps/error
    are derived from a single position in a deterministic lifecycle, never
    computed independently -- that independence was the bug: a job could
    previously land on "queued" with any progress, or "done" with any
    progress, because nothing tied the two together.
    """
    kind = _JOB_KINDS[slot % len(_JOB_KINDS)]
    job_id = f"job-{slot}"
    phase = _JOB_PHASE[kind]
    label = _JOB_LABEL[kind]
    items_total = _JOB_ITEMS_TOTAL[kind]
    model = _MODELS[slot % len(_MODELS)]

    global_elapsed = minute + slot * _SLOT_STAGGER_MINUTES
    cycle_number = global_elapsed // _CYCLE_MINUTES
    elapsed = global_elapsed % _CYCLE_MINUTES

    if elapsed == 0:
        return JobStatus(
            job_id=job_id,
            kind=kind,
            progress=0.0,
            state="queued",
            phase=phase,
            label=label,
            items_total=items_total,
        )

    started_at = (now - timedelta(minutes=elapsed)).isoformat()

    # Whether *this* cycle instance ends in failure, and at which minute --
    # decided once per (slot, cycle), not re-rolled every tick within it, so
    # polling the same job repeatedly mid-cycle doesn't flicker between
    # outcomes.
    outcome_rng = _minute_rng(seed, cycle_number, f"job-outcome-{slot}")
    will_fail = outcome_rng.random() < _FAIL_PROBABILITY
    fail_at = int(outcome_rng.integers(2, _CYCLE_MINUTES - 1)) if will_fail else None

    if will_fail and fail_at is not None and elapsed >= fail_at:
        progress = round(fail_at / (_CYCLE_MINUTES - 1), 2)
        items_done = round(progress * items_total)
        checkpoint_at = (now - timedelta(minutes=elapsed - fail_at)).isoformat()
        return JobStatus(
            job_id=job_id,
            kind=kind,
            progress=progress,
            state="failed",
            phase=phase,
            label=label,
            items_done=items_done,
            items_total=items_total,
            model=model,
            calls_spent=items_done * _CALLS_PER_ITEM,
            started_at=started_at,
            last_checkpoint_at=checkpoint_at,
            error=f"simulated: {kind} job failed after {items_done}/{items_total} items",
        )

    if elapsed == _CYCLE_MINUTES - 1:
        finished_at = now.isoformat()
        return JobStatus(
            job_id=job_id,
            kind=kind,
            progress=1.0,
            state="done",
            phase=phase,
            label=label,
            items_done=items_total,
            items_total=items_total,
            model=model,
            calls_spent=items_total * _CALLS_PER_ITEM,
            started_at=started_at,
            finished_at=finished_at,
            last_checkpoint_at=finished_at,
        )

    progress = round(elapsed / (_CYCLE_MINUTES - 1), 2)
    items_done = round(progress * items_total)
    rate_per_minute = progress / elapsed
    eta_seconds = (
        round(((1.0 - progress) / rate_per_minute) * 60, 1) if rate_per_minute > 0 else None
    )
    return JobStatus(
        job_id=job_id,
        kind=kind,
        progress=progress,
        state="running",
        phase=phase,
        label=label,
        items_done=items_done,
        items_total=items_total,
        model=model,
        calls_spent=items_done * _CALLS_PER_ITEM,
        started_at=started_at,
        eta_seconds=eta_seconds,
        last_checkpoint_at=now.isoformat(),
    )


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
        jobs = tuple(_job_status(self._seed, slot, now, minute) for slot in range(3))
        events = tuple(
            LiveEvent(
                ts=(now - timedelta(seconds=15 * i)).isoformat(),
                level=("info", "info", "warn")[i % 3],
                message=(
                    f"simulated: {_JOB_KINDS[i % len(_JOB_KINDS)]} batch {minute - i} progressed"
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
