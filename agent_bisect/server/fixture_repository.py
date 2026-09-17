"""`DashboardRepository` backed entirely by the in-memory generated fixture set.

Builds `fixtures.bundle.build_bundle(seed)` once at construction time and
serves every page from it; the deep per-step payloads (`step_payload`,
`intervention_diff`, `state_diff`) are regenerated on demand from the
`RunPlan` they were derived from, per `fixtures.serialize`'s module
docstring, rather than being held in memory twice.
"""

from __future__ import annotations

from agent_bisect.server.fixtures.bundle import FixtureBundle, build_bundle
from agent_bisect.server.fixtures.pr_checks import to_summary as pr_to_summary
from agent_bisect.server.fixtures.run_builder import RunPlan
from agent_bisect.server.fixtures.serialize import (
    build_intervention_diff,
    build_rerun_steps,
    build_reruns,
    build_state_diff,
    build_step_payload,
    to_run_detail,
)
from agent_bisect.server.fixtures.writer import build_meta
from agent_bisect.server.live_sim import LiveSimulator
from agent_bisect.server.repository import RunFilter
from agent_bisect.server.run_sorting import sort_runs
from agent_bisect.server.schemas_benchmark import BenchmarkSummary, DatasetPage
from agent_bisect.server.schemas_live import LiveSnapshot
from agent_bisect.server.schemas_meta import MetaPayload, SearchHit, SearchResults
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

DEFAULT_FIXTURE_SEED = 20260917

_STATIC_PAGES: tuple[SearchHit, ...] = (
    SearchHit(kind="page", id="overview", title="Overview", href="/overview"),
    SearchHit(kind="page", id="runs", title="Runs", href="/runs"),
    SearchHit(kind="page", id="benchmark", title="Benchmark", href="/benchmark"),
    SearchHit(kind="page", id="live", title="Live", href="/live"),
    SearchHit(kind="page", id="pr-checks", title="PR checks", href="/pr-checks"),
)


class FixtureRepository:
    """Serves every dashboard page from a byte-deterministic in-memory fixture bundle."""

    def __init__(self, seed: int = DEFAULT_FIXTURE_SEED) -> None:
        self._bundle: FixtureBundle = build_bundle(seed)
        self._pr_by_id: dict[str, PrCheckDetail] = {c.check_id: c for c in self._bundle.pr_checks}
        self._live = LiveSimulator(seed)

    def data_source(self) -> str:
        return "fixture"

    def meta(self) -> MetaPayload:
        return build_meta(self._bundle)

    def search(self, query: str) -> SearchResults:
        needle = query.strip().lower()
        hits: list[SearchHit] = []
        if needle:
            hits.extend(page for page in _STATIC_PAGES if needle in page.title.lower())
            for summary in self._bundle.run_summaries:
                haystack = f"{summary.run_id} {summary.task_id} {summary.domain}".lower()
                if needle in haystack:
                    hits.append(
                        SearchHit(
                            kind="run",
                            id=summary.run_id,
                            title=summary.run_id,
                            subtitle=f"{summary.domain} · {summary.task_id}",
                            href=f"/runs/{summary.run_id}",
                        )
                    )
        return SearchResults(query=query, hits=tuple(hits[:25]))

    def overview(self) -> OverviewPayload:
        return self._bundle.overview

    def _plan(self, run_id: str) -> RunPlan:
        return self._bundle.plan_by_id(run_id)

    def list_runs(self, filters: RunFilter) -> tuple[tuple[RunSummary, ...], int]:
        runs = list(self._bundle.run_summaries)
        if filters.domain:
            runs = [r for r in runs if r.domain == filters.domain]
        if filters.outcome:
            runs = [r for r in runs if r.outcome == filters.outcome]
        if filters.model:
            runs = [r for r in runs if r.model == filters.model]

        runs = sort_runs(runs, filters.sort)

        total = len(runs)
        start = (filters.page - 1) * filters.limit
        page = tuple(runs[start : start + filters.limit])
        return page, total

    def run_detail(self, run_id: str) -> RunDetail:
        plan = self._plan(run_id)
        judge = self._bundle.judge_by_run.get(run_id)
        return to_run_detail(plan, judge)

    def step_payload(self, run_id: str, step_idx: int) -> StepPayload:
        return build_step_payload(self._plan(run_id), step_idx)

    def intervention_diff(self, run_id: str, step_idx: int) -> InterventionDiff | None:
        plan = self._plan(run_id)
        if not 1 <= step_idx <= plan.n_steps:
            raise KeyError(f"step {step_idx} outside run {run_id}")
        return build_intervention_diff(plan, step_idx)

    def state_diff(self, run_id: str, step_idx: int) -> StateDiff:
        return build_state_diff(self._plan(run_id), step_idx)

    def reruns(self, run_id: str) -> RerunPage:
        return build_reruns(self._plan(run_id))

    def rerun_steps(self, run_id: str, rerun_id: str) -> tuple[StepView, ...]:
        return build_rerun_steps(self._plan(run_id), rerun_id)

    def benchmark(self) -> BenchmarkSummary:
        return self._bundle.benchmark

    def dataset(self, page: int, limit: int) -> tuple[DatasetPage, int]:
        entries = self._bundle.dataset_entries
        total = len(entries)
        start = (page - 1) * limit
        return DatasetPage(entries=entries[start : start + limit]), total

    def live_snapshot(self) -> LiveSnapshot:
        return self._live.snapshot()

    def pr_checks(self) -> tuple[PrCheckSummary, ...]:
        return tuple(pr_to_summary(c) for c in self._bundle.pr_checks)

    def pr_check_detail(self, check_id: str) -> PrCheckDetail:
        return self._pr_by_id[check_id]
