"""PR-checks endpoints (page group 6)."""

from __future__ import annotations

from fastapi import APIRouter, Path

from agent_bisect.server.deps import (
    ID_PATTERN,
    RepoDep,
    call_or_not_available,
    envelope_ok,
    not_found,
)
from agent_bisect.server.repository import DashboardRepository, DataNotAvailable
from agent_bisect.server.schemas_common import Envelope
from agent_bisect.server.schemas_meta import NotAvailable
from agent_bisect.server.schemas_pr import PrCheckDetail, PrCheckSummary

router = APIRouter(prefix="/api/pr-checks", tags=["pr-checks"])


@router.get("")
def list_pr_checks(
    repo: DashboardRepository = RepoDep,
) -> Envelope[tuple[PrCheckSummary, ...] | NotAvailable]:
    data = call_or_not_available(repo.pr_checks)
    return envelope_ok(data, repo)


@router.get("/{check_id}")
def get_pr_check_detail(
    check_id: str = Path(pattern=ID_PATTERN),
    repo: DashboardRepository = RepoDep,
) -> Envelope[PrCheckDetail | NotAvailable]:
    try:
        detail = repo.pr_check_detail(check_id)
    except KeyError as exc:
        raise not_found(repo, f"no PR check {check_id!r}") from exc
    except DataNotAvailable as exc:
        return envelope_ok(NotAvailable(reason=exc.reason), repo)
    return envelope_ok(detail, repo)
