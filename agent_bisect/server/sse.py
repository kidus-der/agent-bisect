"""`GET /api/live/stream`: pushes the same `LiveSnapshot` delta every ~2 s.

Built on `StreamingResponse` -- no new dependency, per the P6a build brief
("do SSE with `StreamingResponse`, no new dependency"). `max_events` bounds
the loop for tests; the real endpoint leaves it `None` and relies on the
client disconnecting (FastAPI cancels the generator when that happens).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Protocol

from agent_bisect.server.repository import DataNotAvailable
from agent_bisect.server.schemas_common import ResponseMeta, failed, ok
from agent_bisect.server.schemas_live import LiveSnapshot

DEFAULT_INTERVAL_S = 2.0


class LiveSource(Protocol):
    """Exactly what this module needs from a repository -- not the full
    `DashboardRepository`, so a test double only has to implement two
    methods, and this module doesn't couple to the other twenty."""

    def data_source(self) -> str: ...
    def live_snapshot(self) -> LiveSnapshot: ...


def _sse_line(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _meta(repository: LiveSource) -> ResponseMeta:
    source = repository.data_source()
    return ResponseMeta(simulated=source == "fixture", data_source=source)  # type: ignore[arg-type]


async def live_event_stream(
    repository: LiveSource,
    interval_s: float = DEFAULT_INTERVAL_S,
    max_events: int | None = None,
) -> AsyncGenerator[str, None]:
    """Yields well-formed `event: ...\\ndata: ...\\n\\n` SSE frames."""
    sent = 0
    while max_events is None or sent < max_events:
        meta = _meta(repository)
        try:
            # `live_snapshot()` does blocking I/O in real mode (sqlite reads
            # in real_repository.py) -- run it in the default threadpool so
            # it can't stall the event loop for every other request.
            snapshot = await asyncio.to_thread(repository.live_snapshot)
            envelope = ok(snapshot, meta)
            yield _sse_line("snapshot", envelope.model_dump_json())
        except DataNotAvailable as exc:
            envelope = failed("not_available", exc.reason, meta)
            yield _sse_line("not_available", envelope.model_dump_json())
        sent += 1
        if max_events is None or sent < max_events:
            await asyncio.sleep(interval_s)
