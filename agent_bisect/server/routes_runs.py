"""Runs list + run detail endpoints (page groups 2 and 3)."""

from __future__ import annotations

from fastapi import APIRouter, Path, Query

from agent_bisect.server.deps import (
    DEFAULT_LIMIT,
    ID_PATTERN,
    MAX_LIMIT,
    RepoDep,
    envelope_ok,
    not_found,
)
from agent_bisect.server.repository import DashboardRepository, DataNotAvailable, RunFilter
from agent_bisect.server.schemas_common import Envelope
from agent_bisect.server.schemas_meta import NotAvailable
from agent_bisect.server.schemas_runs import (
    InterventionDiff,
    RerunPage,
    RunDetail,
    RunListPage,
    StateDiff,
    StepPayload,
    StepView,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])

RunIdPath = Path(pattern=ID_PATTERN)
_SortQuery = Query("run_id", pattern=r"^-?[A-Za-z_]+$")


@router.get("")
def list_runs(
    domain: str | None = None,
    outcome: str | None = None,
    status: str | None = None,
    model: str | None = None,
    sort: str = _SortQuery,
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    repo: DashboardRepository = RepoDep,
) -> Envelope[RunListPage | NotAvailable]:
    filters = RunFilter(
        domain=domain,
        outcome=outcome,
        status=status,
        model=model,
        sort=sort,
        page=page,
        limit=limit,
    )
    try:
        runs, total = repo.list_runs(filters)
    except DataNotAvailable as exc:
        return envelope_ok(NotAvailable(reason=exc.reason), repo)
    return envelope_ok(RunListPage(runs=runs), repo, total=total, page=page, limit=limit)


@router.get("/{run_id}")
def get_run_detail(
    run_id: str = RunIdPath, repo: DashboardRepository = RepoDep
) -> Envelope[RunDetail]:
    try:
        detail = repo.run_detail(run_id)
    except KeyError as exc:
        raise not_found(repo, f"no run {run_id!r}") from exc
    return envelope_ok(detail, repo)


@router.get("/{run_id}/steps/{step_idx}")
def get_step_payload(
    run_id: str = RunIdPath,
    step_idx: int = Path(ge=1),
    repo: DashboardRepository = RepoDep,
) -> Envelope[StepPayload]:
    try:
        payload = repo.step_payload(run_id, step_idx)
    except KeyError as exc:
        raise not_found(repo, f"no step {step_idx} on run {run_id!r}") from exc
    return envelope_ok(payload, repo)


@router.get("/{run_id}/steps/{step_idx}/intervention-diff")
def get_intervention_diff(
    run_id: str = RunIdPath,
    step_idx: int = Path(ge=1),
    repo: DashboardRepository = RepoDep,
) -> Envelope[InterventionDiff | None]:
    try:
        diff = repo.intervention_diff(run_id, step_idx)
    except KeyError as exc:
        raise not_found(repo, f"no step {step_idx} on run {run_id!r}") from exc
    return envelope_ok(diff, repo)


@router.get("/{run_id}/steps/{step_idx}/state-diff")
def get_state_diff(
    run_id: str = RunIdPath,
    step_idx: int = Path(ge=1),
    repo: DashboardRepository = RepoDep,
) -> Envelope[StateDiff | NotAvailable]:
    try:
        diff = repo.state_diff(run_id, step_idx)
    except KeyError as exc:
        raise not_found(repo, f"no step {step_idx} on run {run_id!r}") from exc
    except DataNotAvailable as exc:
        return envelope_ok(NotAvailable(reason=exc.reason), repo)
    return envelope_ok(diff, repo)


@router.get("/{run_id}/reruns")
def get_reruns(
    run_id: str = RunIdPath, repo: DashboardRepository = RepoDep
) -> Envelope[RerunPage | NotAvailable]:
    try:
        page = repo.reruns(run_id)
    except KeyError as exc:
        raise not_found(repo, f"no run {run_id!r}") from exc
    except DataNotAvailable as exc:
        return envelope_ok(NotAvailable(reason=exc.reason), repo)
    return envelope_ok(page, repo)


@router.get("/{run_id}/reruns/{rerun_id}/steps")
def get_rerun_steps(
    run_id: str = RunIdPath,
    rerun_id: str = Path(pattern=ID_PATTERN),
    repo: DashboardRepository = RepoDep,
) -> Envelope[tuple[StepView, ...] | NotAvailable]:
    try:
        steps = repo.rerun_steps(run_id, rerun_id)
    except KeyError as exc:
        raise not_found(repo, f"no re-run {rerun_id!r} on run {run_id!r}") from exc
    except DataNotAvailable as exc:
        return envelope_ok(NotAvailable(reason=exc.reason), repo)
    return envelope_ok(steps, repo)
