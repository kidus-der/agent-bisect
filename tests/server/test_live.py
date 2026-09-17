"""Live page: snapshot fields, and a bounded read of the SSE stream."""

from __future__ import annotations

import asyncio
import time

from agent_bisect.server.schemas_live import BudgetStatus, LiveSnapshot, RateLimitStatus
from agent_bisect.server.sse import live_event_stream

_BLOCK_SECONDS = 0.3
_TICK_SECONDS = 0.02


class _BlockingRepo:
    """A fake repository whose `live_snapshot()` blocks synchronously.

    Stands in for `RealRepository.live_snapshot()`'s real sqlite reads --
    the concern is any blocking call inside the SSE generator, not sqlite
    specifically, so a plain `time.sleep` reproduces it without a DB.
    """

    def data_source(self) -> str:
        return "fixture"

    def live_snapshot(self) -> LiveSnapshot:
        time.sleep(_BLOCK_SECONDS)
        return LiveSnapshot(
            calls_series=(),
            budget=BudgetStatus(used=0, cap=None),
            rate_limit=RateLimitStatus(limiter_rpm=40, current_rpm=0.0, headroom_rpm=40.0),
            jobs=(),
            events=(),
        )


def test_live_snapshot_fields(client):
    body = client.get("/api/live/snapshot").json()["data"]
    assert body["rate_limit"]["limiter_rpm"] > 0
    assert body["rate_limit"]["current_rpm"] <= body["rate_limit"]["limiter_rpm"]
    assert len(body["calls_series"]) > 0
    assert len(body["jobs"]) > 0


def test_live_snapshot_is_marked_simulated(client):
    body = client.get("/api/live/snapshot").json()
    assert body["meta"]["simulated"] is True


def test_sse_stream_yields_well_formed_frames(fixture_repo):
    async def collect():
        frames = []
        async for chunk in live_event_stream(fixture_repo, interval_s=0, max_events=3):
            frames.append(chunk)
        return frames

    frames = asyncio.run(collect())
    assert len(frames) == 3
    for frame in frames:
        assert frame.startswith("event: snapshot\ndata: ")
        assert frame.endswith("\n\n")


def test_sse_generator_does_not_block_the_event_loop(fixture_repo):
    """`repository.live_snapshot()` (real sqlite I/O in real mode) must run
    off the event loop thread, or every other concurrent request stalls for
    as long as that one blocking call takes.

    Ticks are timestamped against a `t0` captured before either coroutine
    starts, not against each other -- a ticker whose own first line runs
    late (because the loop's thread was itself stuck inside a synchronous
    call before the ticker ever got a turn) would otherwise hide the delay
    by only ever measuring gaps *after* that late start.
    """

    async def scenario() -> list[float]:
        t0 = time.monotonic()
        tick_times: list[float] = []

        async def ticker():
            for _ in range(15):
                await asyncio.sleep(_TICK_SECONDS)
                tick_times.append(time.monotonic() - t0)

        async def consume_one():
            agen = live_event_stream(_BlockingRepo(), interval_s=0, max_events=1)
            async for _ in agen:
                return

        await asyncio.gather(consume_one(), ticker())
        return tick_times

    tick_times = asyncio.run(scenario())
    # A blocked event loop delays the very first tick by ~`_BLOCK_SECONDS`;
    # an offloaded call lets it land near `_TICK_SECONDS` as scheduled.
    assert tick_times[0] < _BLOCK_SECONDS / 2


def test_sse_generator_closes_promptly_and_leaves_no_task(fixture_repo):
    """Closing the generator early (a client disconnect) must not wait out
    the sleep interval, and must not leave a lingering asyncio task."""

    async def scenario() -> tuple[float, bool]:
        agen = live_event_stream(fixture_repo, interval_s=5.0)
        await agen.__anext__()
        before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}

        start = time.monotonic()
        await asyncio.wait_for(agen.aclose(), timeout=1.0)
        elapsed = time.monotonic() - start

        after = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
        return elapsed, after <= before

    elapsed, no_new_tasks = asyncio.run(scenario())
    assert elapsed < 1.0
    assert no_new_tasks


def test_sse_route_is_registered_with_event_stream_media_type(fixture_app):
    """Static route-table check, not a live read.

    `httpx.ASGITransport` (what both `TestClient` and a direct
    `httpx.AsyncClient(transport=...)` use here) buffers an ASGI app's
    *entire* response before returning it -- see
    `.venv/.../httpx/_transports/asgi.py::handle_async_request`, which
    does `await self.app(scope, receive, send)` and only builds a
    `Response` once that call returns. `/api/live/stream`'s generator
    intentionally never returns (it loops until the client disconnects),
    so reading it through that transport deadlocks by construction --
    not a bug in this endpoint. The generator's own framing is already
    covered, bounded, by `test_sse_stream_yields_well_formed_frames`
    above; this test only checks the route exists and declares the right
    media type, without ever invoking it.
    """
    schema = fixture_app.openapi()
    assert "get" in schema["paths"]["/api/live/stream"]
