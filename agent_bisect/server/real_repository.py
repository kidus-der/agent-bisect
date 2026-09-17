"""`DashboardRepository` backed by real, on-disk recordings: `runs/ledger.sqlite`
(read-only) and the tape/blob store under `runs/` (also read-only).

Everything this codebase hasn't built yet -- attribution results persisted
anywhere, a judge-output store, a planted-fault dataset, a PR-check store,
a job queue, an event log -- raises `repository.DataNotAvailable`, which
`app.py` turns into a 200 envelope carrying a typed `NotAvailable` payload.
This module never fabricates a number to fill a gap.

Read-only discipline: every SQLite connection is opened with the `mode=ro`
URI, and nothing here ever calls `core.store.BlobStore()` or reads a table
through `core.tape.TapeReader`/`core.budget.BudgetLedger` unless the
underlying file already exists on disk -- both of those constructors
create their file/directory as a side effect, which this module must not
trigger just by being asked a question.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_bisect.core.limits import load_limiter_settings
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step
from agent_bisect.server.repository import DataNotAvailable, RunFilter
from agent_bisect.server.schemas_benchmark import BenchmarkSummary, DatasetPage
from agent_bisect.server.schemas_live import (
    BudgetStatus,
    CallsPoint,
    LiveSnapshot,
    RateLimitStatus,
)
from agent_bisect.server.schemas_meta import MetaPayload, SearchHit, SearchResults
from agent_bisect.server.schemas_overview import OverviewPayload
from agent_bisect.server.schemas_pr import PrCheckDetail, PrCheckSummary
from agent_bisect.server.schemas_runs import (
    BlameCell,
    InterventionDiff,
    RerunPage,
    RunDetail,
    RunSummary,
    SparkPoint,
    StateDiff,
    StepPayload,
    StepView,
)

PACKAGE_VERSION = "0.1.0"
_LIVE_WINDOW_MINUTES = 30
_RECENT_WINDOW_SECONDS = 60


def _total_tokens(step: Step) -> int | None:
    """`None` only when neither side was ever recorded; otherwise the honest
    sum, treating a genuinely-unrecorded side as 0 rather than the whole
    figure as unknown."""
    if step.tokens_in is None and step.tokens_out is None:
        return None
    return (step.tokens_in or 0) + (step.tokens_out or 0)


def _ro_connect(path: Path) -> sqlite3.Connection | None:
    """A read-only connection to `path`, or `None` if it doesn't exist yet."""
    if not path.exists():
        return None
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


class RealRepository:
    """Serves what real recordings on disk can answer; everything else is `DataNotAvailable`."""

    def __init__(self, runs_dir: Path = Path("runs")) -> None:
        self._runs_dir = runs_dir
        self._index_path = runs_dir / "index.sqlite"
        self._ledger_path = runs_dir / "ledger.sqlite"
        self._blobs_dir = runs_dir / "blobs"

    def data_source(self) -> str:
        return "real"

    def meta(self) -> MetaPayload:
        return MetaPayload(
            data_source="real",
            simulated=False,
            package_version=PACKAGE_VERSION,
            tau2_commit="unknown",
            agent_model="unknown",
            user_model="unknown",
            generated_at=datetime.now(UTC).isoformat(),
        )

    def search(self, query: str) -> SearchResults:
        needle = query.strip().lower()
        hits: list[SearchHit] = []
        if needle:
            conn = _ro_connect(self._index_path)
            if conn is not None:
                try:
                    rows = conn.execute("SELECT run_id FROM runs").fetchall()
                finally:
                    conn.close()
                for (run_id,) in rows:
                    if needle in run_id.lower():
                        hits.append(
                            SearchHit(kind="run", id=run_id, title=run_id, href=f"/runs/{run_id}")
                        )
        return SearchResults(query=query, hits=tuple(hits[:25]))

    def overview(self) -> OverviewPayload:
        raise DataNotAvailable("no evaluation has been run yet (bench/evaluate.py output)")

    def _all_manifests(self, conn: sqlite3.Connection) -> list[tuple[RunManifest, Outcome | None]]:
        rows = conn.execute("SELECT run_id, manifest_json FROM runs").fetchall()
        results = []
        for run_id, manifest_json in rows:
            manifest = RunManifest.model_validate_json(manifest_json)
            outcome_row = conn.execute(
                "SELECT outcome_json FROM outcomes WHERE run_id = ?", (run_id,)
            ).fetchone()
            outcome = Outcome.model_validate_json(outcome_row[0]) if outcome_row else None
            results.append((manifest, outcome))
        return results

    def _steps_for(self, conn: sqlite3.Connection, run_id: str) -> list[Step]:
        rows = conn.execute(
            "SELECT step_json FROM steps WHERE run_id = ? ORDER BY step_idx", (run_id,)
        ).fetchall()
        return [Step.model_validate_json(row[0]) for row in rows]

    def _run_summary(
        self, manifest: RunManifest, outcome: Outcome, steps: list[Step]
    ) -> RunSummary:
        sparkline = tuple(
            SparkPoint(
                step_idx=step.step_idx,
                actor=step.actor,
                latency_ms=step.latency_ms,
                tokens=_total_tokens(step),
            )
            for step in steps
        )
        blame_stripe = tuple(
            BlameCell(step_idx=step.step_idx, effect=None, tested=False) for step in steps
        )
        return RunSummary(
            run_id=manifest.run_id,
            domain=manifest.domain,
            task_id=manifest.task_id,
            model=manifest.agent_model,
            outcome="pass" if outcome.passed else "fail",
            n_steps=len(steps),
            decisive_step=None,
            fault_type=None,
            planted_step=None,
            # Not 0.0/0: the ledger has no run_id column yet (P1b), so
            # per-run cost/calls genuinely aren't attributable, not free.
            cost_usd=None,
            calls=None,
            sparkline=sparkline,
            blame_stripe=blame_stripe,
        )

    def list_runs(self, filters: RunFilter) -> tuple[tuple[RunSummary, ...], int]:
        conn = _ro_connect(self._index_path)
        if conn is None:
            raise DataNotAvailable("no recordings yet (runs/index.sqlite not found)")
        try:
            summaries = []
            for manifest, outcome in self._all_manifests(conn):
                if outcome is None:
                    continue  # still in progress: nothing honest to report as pass/fail yet
                steps = self._steps_for(conn, manifest.run_id)
                summaries.append(self._run_summary(manifest, outcome, steps))
        finally:
            conn.close()

        if filters.domain:
            summaries = [s for s in summaries if s.domain == filters.domain]
        if filters.outcome:
            summaries = [s for s in summaries if s.outcome == filters.outcome]
        if filters.model:
            summaries = [s for s in summaries if s.model == filters.model]
        summaries.sort(key=lambda s: s.run_id, reverse=filters.sort.startswith("-"))

        total = len(summaries)
        start = (filters.page - 1) * filters.limit
        return tuple(summaries[start : start + filters.limit]), total

    def run_detail(self, run_id: str) -> RunDetail:
        conn = _ro_connect(self._index_path)
        if conn is None:
            raise KeyError(run_id)
        try:
            row = conn.execute(
                "SELECT manifest_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            manifest = RunManifest.model_validate_json(row[0])
            outcome_row = conn.execute(
                "SELECT outcome_json FROM outcomes WHERE run_id = ?", (run_id,)
            ).fetchone()
            outcome = Outcome.model_validate_json(outcome_row[0]) if outcome_row else None
            steps = self._steps_for(conn, run_id)
        finally:
            conn.close()

        step_views = tuple(
            StepView(
                step_idx=step.step_idx,
                actor=step.actor,
                tool_name=step.tool_name,
                text=f"{step.tool_name} call" if step.tool_name else f"{step.actor} turn",
                from_tape=True,
                state_changed=step.state_before != step.state_after,
            )
            for step in steps
        )
        return RunDetail(
            run_id=manifest.run_id,
            domain=manifest.domain,
            task_id=manifest.task_id,
            agent_model=manifest.agent_model,
            user_model=manifest.user_model,
            seed=manifest.seed,
            tau2_commit=manifest.tau2_commit,
            created_at=manifest.created_at.isoformat(),
            outcome="pass" if (outcome and outcome.passed) else "fail",
            # Not 0.0: a run with no outcome row yet is still recording, not failed.
            reward=outcome.reward if outcome else None,
            steps=step_views,
            planted_step=None,
            fault_type=None,
            estimate=None,  # no attribution result has been persisted anywhere yet
            judge=None,  # no judge output has been persisted anywhere yet
        )

    def _blob_store(self) -> BlobStore | None:
        return BlobStore(self._runs_dir) if self._blobs_dir.exists() else None

    def _step(self, run_id: str, step_idx: int) -> Step:
        conn = _ro_connect(self._index_path)
        if conn is None:
            raise KeyError(run_id)
        try:
            row = conn.execute(
                "SELECT step_json FROM steps WHERE run_id = ? AND step_idx = ?",
                (run_id, step_idx),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise KeyError(f"run_id={run_id!r} step_idx={step_idx}")
        return Step.model_validate_json(row[0])

    def step_payload(self, run_id: str, step_idx: int) -> StepPayload:
        step = self._step(run_id, step_idx)
        store = self._blob_store()

        def _get(ref: str | None) -> Any:
            if ref is None or store is None or not store.has(ref):
                return None
            return store.get_json(ref)

        request = _get(step.request_ref)
        response = _get(step.response_ref)
        tool_result = _get(step.tool_result_ref)
        messages = tuple(
            {"role": "raw", "content": str(payload)}
            for payload in (request, response)
            if payload is not None
        )
        return StepPayload(
            step_idx=step_idx,
            messages=messages,
            tool_args={k: str(v) for k, v in (step.tool_args or {}).items()} or None,
            tool_result={k: str(v) for k, v in tool_result.items()}
            if isinstance(tool_result, dict)
            else None,
        )

    def intervention_diff(self, run_id: str, step_idx: int) -> InterventionDiff | None:
        self._step(run_id, step_idx)  # 404s via KeyError if the step doesn't exist
        return None  # no intervention has ever been applied to a real recording yet

    def state_diff(self, run_id: str, step_idx: int) -> StateDiff:
        step = self._step(run_id, step_idx)
        store = self._blob_store()
        if store is None or not (store.has(step.state_before) and store.has(step.state_after)):
            raise DataNotAvailable("world-state snapshots are not in the blob store")
        before = store.get_json(step.state_before)
        after = store.get_json(step.state_after)
        entries = []
        if isinstance(before, dict) and isinstance(after, dict):
            from agent_bisect.server.schemas_runs import DiffEntry

            for key in sorted(set(before) | set(after)):
                if before.get(key) != after.get(key):
                    entries.append(
                        DiffEntry(
                            path=key,
                            kind="changed"
                            if key in before and key in after
                            else ("added" if key not in before else "removed"),
                            before=str(before.get(key)) if key in before else None,
                            after=str(after.get(key)) if key in after else None,
                        )
                    )
        return StateDiff(step_idx=step_idx, entries=tuple(entries))

    def reruns(self, run_id: str) -> RerunPage:
        raise DataNotAvailable("no re-run matrix has been recorded for any run yet")

    def rerun_steps(self, run_id: str, rerun_id: str) -> tuple[StepView, ...]:
        raise DataNotAvailable("no re-run matrix has been recorded for any run yet")

    def benchmark(self) -> BenchmarkSummary:
        raise DataNotAvailable("no benchmark evaluation has been run yet (bench/evaluate.py)")

    def dataset(self, page: int, limit: int) -> tuple[DatasetPage, int]:
        raise DataNotAvailable("no planted-fault dataset has been built yet (bench/inject.py)")

    def _ledger_conn(self) -> sqlite3.Connection | None:
        return _ro_connect(self._ledger_path)

    def live_snapshot(self) -> LiveSnapshot:
        conn = self._ledger_conn()
        if conn is None:
            raise DataNotAvailable("no ledger recorded yet (runs/ledger.sqlite not found)")
        try:
            now = time.time()
            window_start = now - _LIVE_WINDOW_MINUTES * 60
            rows = conn.execute(
                "SELECT ts, model FROM calls WHERE ts >= ? ORDER BY ts", (window_start,)
            ).fetchall()
            total_calls = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            recent = conn.execute(
                "SELECT COUNT(*) FROM calls WHERE ts >= ?", (now - _RECENT_WINDOW_SECONDS,)
            ).fetchone()[0]
        finally:
            conn.close()

        buckets: dict[tuple[int, str], int] = {}
        for ts, model in rows:
            minute = int(ts // 60)
            buckets[(minute, model)] = buckets.get((minute, model), 0) + 1
        calls_series = tuple(
            CallsPoint(
                ts=datetime.fromtimestamp(minute * 60, tz=UTC).isoformat(),
                model=model,
                calls_per_minute=float(count),
            )
            for (minute, model), count in sorted(buckets.items())
        )

        settings = load_limiter_settings()
        current_rpm = recent * (60 / _RECENT_WINDOW_SECONDS)
        return LiveSnapshot(
            calls_series=calls_series,
            budget=BudgetStatus(used=total_calls, cap=None),
            rate_limit=RateLimitStatus(
                limiter_rpm=int(settings.requests_per_minute),
                current_rpm=round(current_rpm, 1),
                headroom_rpm=round(settings.requests_per_minute - current_rpm, 1),
            ),
            jobs=(),
            events=(),
        )

    def pr_checks(self) -> tuple[PrCheckSummary, ...]:
        raise DataNotAvailable("no PR checks have run yet (gate/action.py)")

    def pr_check_detail(self, check_id: str) -> PrCheckDetail:
        raise DataNotAvailable("no PR checks have run yet (gate/action.py)")
