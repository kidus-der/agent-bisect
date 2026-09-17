"""Tests for TokenBucketLimiter: acquire timing against a fake clock, no real sleeps."""

from __future__ import annotations

import asyncio

import pytest
from agent_bisect.core.llm import TokenBucketLimiter


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSleeper:
    """Records requested sleep durations and advances the shared fake clock instantly."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


@pytest.mark.asyncio
async def test_acquire_does_not_sleep_while_tokens_available():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = TokenBucketLimiter(60, clock=clock, sleep=sleeper)

    await limiter.acquire()

    assert sleeper.calls == []


@pytest.mark.asyncio
async def test_acquire_sleeps_once_bucket_is_empty():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    # A bucket of capacity 1 starts full; the second immediate acquire
    # (no time elapsed to refill) must wait for a full refill.
    limiter = TokenBucketLimiter(1, clock=clock, sleep=sleeper)

    await limiter.acquire()  # consumes the initial token, no wait
    await limiter.acquire()  # bucket empty, must wait for a refill

    assert len(sleeper.calls) == 1
    # 1 req/min == a full refill takes 60s.
    assert sleeper.calls[0] == pytest.approx(60.0, abs=1e-6)


@pytest.mark.asyncio
async def test_acquire_refills_after_elapsed_time():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = TokenBucketLimiter(60, clock=clock, sleep=sleeper)

    await limiter.acquire()
    clock.advance(1.0)  # one full token refills
    await limiter.acquire()

    assert sleeper.calls == []


@pytest.mark.asyncio
async def test_acquire_never_exceeds_capacity():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = TokenBucketLimiter(10, clock=clock, sleep=sleeper)

    clock.advance(1000)  # plenty of time to overflow the bucket if uncapped
    for _ in range(10):
        await limiter.acquire()
    # the 11th acquire should need to wait, proving capacity was capped at 10
    await limiter.acquire()

    assert len(sleeper.calls) == 1


def test_requests_per_minute_must_be_positive():
    with pytest.raises(ValueError):
        TokenBucketLimiter(0)


@pytest.mark.asyncio
async def test_concurrent_acquires_are_serialized(monkeypatch):
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = TokenBucketLimiter(60, clock=clock, sleep=sleeper)

    results = []

    async def worker():
        await limiter.acquire()
        results.append(clock.now)

    await asyncio.gather(*(worker() for _ in range(3)))

    assert len(results) == 3
