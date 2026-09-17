"""Live page endpoints (page group 5): snapshot + SSE stream."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent_bisect.server.deps import RepoDep, call_or_not_available, envelope_ok
from agent_bisect.server.repository import DashboardRepository
from agent_bisect.server.schemas_common import Envelope
from agent_bisect.server.schemas_live import LiveSnapshot
from agent_bisect.server.schemas_meta import NotAvailable
from agent_bisect.server.sse import live_event_stream

router = APIRouter(prefix="/api/live", tags=["live"])


@router.get("/snapshot")
def get_live_snapshot(
    repo: DashboardRepository = RepoDep,
) -> Envelope[LiveSnapshot | NotAvailable]:
    data = call_or_not_available(repo.live_snapshot)
    return envelope_ok(data, repo)


@router.get("/stream")
async def stream_live(repo: DashboardRepository = RepoDep) -> StreamingResponse:
    return StreamingResponse(
        live_event_stream(repo),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
