"""`GET /api/live/stream`: pushes the same `LiveSnapshot` delta every ~2 s.

Built on `StreamingResponse` -- no new dependency, per the P6a build brief
("do SSE with `StreamingResponse`, no new dependency"). `max_events` bounds
the loop for tests; the real endpoint leaves it `None` and relies on the
client disconnecting (FastAPI cancels the generator when that happens).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent_bisect.server.deps import base_meta
from agent_bisect.server.repository import DashboardRepository, DataNotAvailable
from agent_bisect.server.schemas_common import failed, ok

DEFAULT_INTERVAL_S = 2.0


def _sse_line(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def live_event_stream(
    repository: DashboardRepository,
    interval_s: float = DEFAULT_INTERVAL_S,
    max_events: int | None = None,
) -> AsyncIterator[str]:
    """Yields well-formed `event: ...\\ndata: ...\\n\\n` SSE frames."""
    sent = 0
    while max_events is None or sent < max_events:
        meta = base_meta(repository)
        try:
            snapshot = repository.live_snapshot()
            envelope = ok(snapshot, meta)
            yield _sse_line("snapshot", envelope.model_dump_json())
        except DataNotAvailable as exc:
            envelope = failed("not_available", exc.reason, meta)
            yield _sse_line("not_available", envelope.model_dump_json())
        sent += 1
        if max_events is None or sent < max_events:
            await asyncio.sleep(interval_s)
