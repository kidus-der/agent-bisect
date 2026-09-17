"""Overview page endpoint (page group 1)."""

from __future__ import annotations

from fastapi import APIRouter

from agent_bisect.server.deps import RepoDep, call_or_not_available, envelope_ok
from agent_bisect.server.repository import DashboardRepository
from agent_bisect.server.schemas_common import Envelope
from agent_bisect.server.schemas_meta import NotAvailable
from agent_bisect.server.schemas_overview import OverviewPayload

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview")
def get_overview(
    repo: DashboardRepository = RepoDep,
) -> Envelope[OverviewPayload | NotAvailable]:
    data = call_or_not_available(repo.overview)
    return envelope_ok(data, repo)
