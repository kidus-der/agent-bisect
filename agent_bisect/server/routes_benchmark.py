"""Benchmark page endpoints (page group 4)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent_bisect.server.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    RepoDep,
    call_or_not_available,
    envelope_ok,
)
from agent_bisect.server.repository import DashboardRepository, DataNotAvailable
from agent_bisect.server.schemas_benchmark import BenchmarkSummary, DatasetPage
from agent_bisect.server.schemas_common import Envelope
from agent_bisect.server.schemas_meta import NotAvailable

router = APIRouter(prefix="/api", tags=["benchmark"])


@router.get("/benchmark")
def get_benchmark(
    repo: DashboardRepository = RepoDep,
) -> Envelope[BenchmarkSummary | NotAvailable]:
    data = call_or_not_available(repo.benchmark)
    return envelope_ok(data, repo)


@router.get("/dataset")
def get_dataset(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    repo: DashboardRepository = RepoDep,
) -> Envelope[DatasetPage | NotAvailable]:
    try:
        dataset_page, total = repo.dataset(page, limit)
    except DataNotAvailable as exc:
        return envelope_ok(NotAvailable(reason=exc.reason), repo)
    return envelope_ok(dataset_page, repo, total=total, page=page, limit=limit)
