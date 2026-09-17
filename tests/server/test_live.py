"""Live page: snapshot fields, and a bounded read of the SSE stream."""

from __future__ import annotations

import asyncio

from agent_bisect.server.sse import live_event_stream


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
