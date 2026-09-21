"""`DashboardRepository`: the only thing `app.py`'s routes depend on.

Two implementations: `fixture_repository.FixtureRepository` (reads the
generated JSON under `data/fixtures/`) and `real_repository.RealRepository`
(reads `runs/ledger.sqlite` and the tape/blob store read-only). A route
handler never branches on which one it has — it calls the Protocol and
lets each implementation decide whether a field is available.

Errors: `KeyError` for an unknown id (the route layer turns this into a 404
envelope); `DataNotAvailable` for a field `real_repository` cannot yet serve
at all (the route layer turns this into a 200 envelope whose `data` is a
typed `NotAvailable` payload -- never a fake number); everything else
propagates as a 500 by FastAPI's default exception handling, which is fine
here since a real repository failure is a genuine server bug, not a client
error.
"""

from __future__ import annotations

from typing import Protocol

from agent_bisect.server.schemas_benchmark import BenchmarkSummary, DatasetPage
from agent_bisect.server.schemas_live import LiveSnapshot
from agent_bisect.server.schemas_meta import MetaPayload, SearchResults
from agent_bisect.server.schemas_overview import OverviewPayload
from agent_bisect.server.schemas_pr import PrCheckDetail, PrCheckSummary
from agent_bisect.server.schemas_runs import (
    InterventionDiff,
    RerunPage,
    RunDetail,
    RunSummary,
    StateDiff,
    StepPayload,
    StepView,
)


class DataNotAvailable(Exception):
    """Raised by a repository method for a field it cannot yet serve.

    `real_repository.RealRepository` raises this for every page not yet
    backed by a real recording; `fixture_repository.FixtureRepository`
    never raises it, since the fixture set always has something for every
    page. `app.py` catches it and returns a 200 envelope whose `data` is a
    `schemas_meta.NotAvailable`, not a 404 or 500 -- the query was
    understood, the answer just isn't ready yet.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RunFilter:
    """Filter/sort/pagination parameters for `list_runs`. Immutable; build a new one to change."""

    __slots__ = (
        "domain",
        "outcome",
        "status",
        "model",
        "fault_type",
        "q",
        "kind",
        "sort",
        "page",
        "limit",
    )

    def __init__(
        self,
        domain: str | None = None,
        outcome: str | None = None,
        status: str | None = None,
        model: str | None = None,
        fault_type: str | None = None,
        q: str | None = None,
        kind: str = "top",
        sort: str = "run_id",
        page: int = 1,
        limit: int = 50,
    ) -> None:
        self.domain = domain
        self.outcome = outcome
        self.status = status
        self.model = model
        self.fault_type = fault_type
        self.q = q
        #: `"top"` (default) -- runs with no `parent_run_id`, i.e. not a fork/
        #: re-run; `"reruns"` -- only forks; `"all"` -- no filtering on this
        #: axis at all. Anything else is treated as `"top"` (fail safe to the
        #: narrower, more legible default).
        self.kind = kind
        self.sort = sort
        self.page = page
        self.limit = limit


class DashboardRepository(Protocol):
    """Read-only data access for every dashboard page. See module docstring."""

    def data_source(self) -> str:
        """ "fixture" or "real"."""
        ...

    def meta(self) -> MetaPayload: ...

    def search(self, query: str) -> SearchResults: ...

    def overview(self) -> OverviewPayload:
        """Raises `DataNotAvailable` if nothing backs the headline result yet."""
        ...

    def list_runs(self, filters: RunFilter) -> tuple[tuple[RunSummary, ...], int]:
        """Returns (page of runs, total matching count)."""
        ...

    def run_detail(self, run_id: str) -> RunDetail:
        """Raises `KeyError` if `run_id` is unknown."""
        ...

    def step_payload(self, run_id: str, step_idx: int) -> StepPayload: ...

    def intervention_diff(self, run_id: str, step_idx: int) -> InterventionDiff | None:
        """`None` if the step was never intervened on (not an error)."""
        ...

    def state_diff(self, run_id: str, step_idx: int) -> StateDiff: ...

    def reruns(self, run_id: str) -> RerunPage: ...

    def rerun_steps(self, run_id: str, rerun_id: str) -> tuple[StepView, ...]: ...

    def benchmark(self) -> BenchmarkSummary:
        """Raises `DataNotAvailable` if no evaluation has been run yet."""
        ...

    def dataset(self, page: int, limit: int) -> tuple[DatasetPage, int]: ...

    def live_snapshot(self) -> LiveSnapshot: ...

    def pr_checks(self) -> tuple[PrCheckSummary, ...]: ...

    def pr_check_detail(self, check_id: str) -> PrCheckDetail:
        """Raises `KeyError` if `check_id` is unknown."""
        ...
