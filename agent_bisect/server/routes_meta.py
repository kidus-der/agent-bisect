"""Global endpoints (page group 7): health, build meta, search."""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent_bisect.server.deps import RepoDep, envelope_ok
from agent_bisect.server.repository import DashboardRepository
from agent_bisect.server.schemas_common import Envelope
from agent_bisect.server.schemas_meta import HealthPayload, MetaPayload, SearchResults

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def get_health(repo: DashboardRepository = RepoDep) -> Envelope[HealthPayload]:
    return envelope_ok(HealthPayload(status="ok"), repo)


@router.get("/meta")
def get_meta(repo: DashboardRepository = RepoDep) -> Envelope[MetaPayload]:
    return envelope_ok(repo.meta(), repo)


@router.get("/search")
def search(
    q: str = Query("", max_length=200),
    repo: DashboardRepository = RepoDep,
) -> Envelope[SearchResults]:
    return envelope_ok(repo.search(q), repo)
