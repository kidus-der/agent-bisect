"""One bucket, many threads, many event loops.

`asyncio.Lock` binds to the event loop that first awaits it. τ² runs its
tasks in a thread pool and each worker thread sets up its own loop, while
our own scripts call the same limiter from coroutines and from plain
synchronous code. A loop-bound lock raises `RuntimeError: ... attached to
a different loop` there, or silently stops serialising. The bucket's state
is therefore guarded by a `threading.Lock` around pure token arithmetic,
and the lock is never held across a sleep.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from agent_bisect.core.llm import TokenBucketLimiter

RATE_PER_MINUTE = 4  # capacity 4, one token back every 15 simulated seconds
ASYNC_WORKERS = 4
SYNC_WORKERS = 4
TOTAL = ASYNC_WORKERS + SYNC_WORKERS


class SharedFakeClock:
    """A simulated clock several threads can read and advance safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        with self._lock:
            return self.now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)
            self.now += seconds

    async def sleep_async(self, seconds: float) -> None:
        self.advance(seconds)

    def sleep_sync(self, seconds: float) -> None:
        self.advance(seconds)


def _run_mixed_callers(limiter: TokenBucketLimiter, clock: SharedFakeClock) -> list:
    """Half the callers own an event loop; half are plain sync code."""
    grants: list[float] = []
    failures: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(TOTAL)

    def note(exc: BaseException | None) -> None:
        with lock:
            if exc is not None:
                failures.append(exc)
            else:
                grants.append(clock())

    def async_worker() -> None:
        async def main() -> None:
            await limiter.acquire()

        barrier.wait()
        try:
            # Its own loop, as a τ² worker thread would have.
            asyncio.run(main())
            note(None)
        except BaseException as exc:  # noqa: BLE001 - any failure is the finding
            note(exc)

    def sync_worker() -> None:
        barrier.wait()
        try:
            limiter.acquire_sync()
            note(None)
        except BaseException as exc:  # noqa: BLE001 - any failure is the finding
            note(exc)

    threads = [threading.Thread(target=async_worker) for _ in range(ASYNC_WORKERS)]
    threads += [threading.Thread(target=sync_worker) for _ in range(SYNC_WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == [], f"limiter raised for a caller: {failures!r}"
    return grants


def test_async_and_sync_callers_share_one_bucket_without_erroring():
    clock = SharedFakeClock()
    limiter = TokenBucketLimiter(
        RATE_PER_MINUTE, clock=clock, sleep=clock.sleep_async, sleep_sync=clock.sleep_sync
    )

    grants = _run_mixed_callers(limiter, clock)

    assert len(grants) == TOTAL


def test_the_bucket_never_grants_more_than_its_capacity_without_time_passing():
    clock = SharedFakeClock()
    limiter = TokenBucketLimiter(
        RATE_PER_MINUTE, clock=clock, sleep=clock.sleep_async, sleep_sync=clock.sleep_sync
    )

    grants = _run_mixed_callers(limiter, clock)

    immediate = [at for at in grants if at == 0.0]
    assert len(immediate) <= RATE_PER_MINUTE


def test_callers_beyond_the_capacity_actually_waited():
    clock = SharedFakeClock()
    limiter = TokenBucketLimiter(
        RATE_PER_MINUTE, clock=clock, sleep=clock.sleep_async, sleep_sync=clock.sleep_sync
    )

    _run_mixed_callers(limiter, clock)

    assert clock.sleeps, "8 callers through a 4-token bucket must have slept"
    assert all(seconds > 0 for seconds in clock.sleeps)


@pytest.mark.parametrize("workers", [2, 6])
def test_a_second_batch_of_loops_reuses_the_same_bucket(workers):
    """A fresh event loop per batch must not re-bind or reset the limiter."""
    clock = SharedFakeClock()
    limiter = TokenBucketLimiter(
        600, clock=clock, sleep=clock.sleep_async, sleep_sync=clock.sleep_sync
    )

    for _ in range(2):
        threads = [
            threading.Thread(target=lambda: asyncio.run(limiter.acquire()))
            for _ in range(workers)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert limiter.requests_per_minute == 600


async def test_the_async_path_still_works_on_an_already_running_loop():
    limiter = TokenBucketLimiter(600)

    await asyncio.gather(*(limiter.acquire() for _ in range(5)))
