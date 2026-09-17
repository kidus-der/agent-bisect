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

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_bisect.attribution.blame_store import load_blame
from agent_bisect.core.limits import load_limiter_settings
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step
from agent_bisect.server.repository import DataNotAvailable, RunFilter
from agent_bisect.server.run_filtering import RunSearchRow, filter_runs
from agent_bisect.server.run_sorting import sort_runs
from agent_bisect.server.schemas_benchmark import BenchmarkSummary, DatasetPage
from agent_bisect.server.schemas_live import (
    BudgetStatus,
    CallsPoint,
    JobStatus,
    LiveSnapshot,
    RateLimitStatus,
)
from agent_bisect.server.schemas_meta import MetaPayload, SearchHit, SearchResults
from agent_bisect.server.schemas_overview import OverviewPayload
from agent_bisect.server.schemas_pr import PrCheckDetail, PrCheckSummary
from agent_bisect.server.schemas_runs import (
    BlameCell,
    InterventionDiff,
    JudgePanel,
    RerunPage,
    RerunRow,
    RunDetail,
    RunEstimateView,
    RunSummary,
    SparkPoint,
    StateDiff,
    StepPayload,
    StepView,
)

PACKAGE_VERSION = "0.1.0"
_LIVE_WINDOW_MINUTES = 30
_RECENT_WINDOW_SECONDS = 60
#: `runs/<phase>/status.json`: the convention a long-running job can write
#: its own progress to (documented in docs/design/api-contract.md). One
#: object per file, shaped like `JobStatus` minus `job_id` (the phase
#: directory name) and `phase` (defaults to that name, upper-cased).
_STATUS_FILENAME = "status.json"


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
                    rows = conn.execute(
                        "SELECT r.run_id, (o.run_id IS NOT NULL) FROM runs r "
                        "LEFT JOIN outcomes o ON o.run_id = r.run_id"
                    ).fetchall()
                finally:
                    conn.close()
                for run_id, has_outcome in rows:
                    if needle in run_id.lower():
                        status = "complete" if has_outcome else "recording"
                        hits.append(
                            SearchHit(
                                kind="run",
                                id=run_id,
                                title=run_id,
                                href=f"/runs/{run_id}",
                                status=status,
                            )
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
        self,
        manifest: RunManifest,
        outcome: Outcome | None,
        steps: list[Step],
        calls: int | None,
        blame: dict[str, Any] | None,
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
        # `effects` is empty (every cell untested) unless P5 has written a
        # blame result *with* an estimate -- a judge that never answered
        # bought no re-runs, so there is nothing to mark tested either.
        effects: dict[int, float] = {}
        if blame is not None and blame["estimate"] is not None:
            effects = {
                effect["step"]: effect["effect"] for effect in blame["estimate"]["step_effects"]
            }
        blame_stripe = tuple(
            BlameCell(
                step_idx=step.step_idx,
                effect=effects.get(step.step_idx),
                tested=step.step_idx in effects,
            )
            for step in steps
        )
        return RunSummary(
            run_id=manifest.run_id,
            domain=manifest.domain,
            task_id=manifest.task_id,
            model=manifest.agent_model,
            status="complete" if outcome is not None else "recording",
            # `None` while still recording -- never a fabricated "fail".
            outcome=None if outcome is None else ("pass" if outcome.passed else "fail"),
            n_steps=len(steps),
            decisive_step=blame["blamed_step"] if blame is not None else None,
            fault_type=None,
            planted_step=None,
            # cost_usd: not 0.0 -- no per-model USD price exists anywhere in
            # this codebase to multiply the (now real) call count by.
            cost_usd=None,
            calls=calls,
            sparkline=sparkline,
            blame_stripe=blame_stripe,
        )

    def _load_blame_doc(self, run_id: str) -> dict[str, Any] | None:
        """`runs/blame/<run_id>.json` (P5's primary "bisect" result), or
        `None` if that run has never been diagnosed. `blame_store.load_blame`
        only checks the file exists and reads it -- safe read-only access,
        unlike the constructors this module otherwise avoids."""
        try:
            return load_blame(self._runs_dir, run_id)
        except FileNotFoundError:
            return None

    def _calls_per_run(self, conn: sqlite3.Connection) -> dict[str, int]:
        """Real per-run call counts from the ledger's `run_id` column (P1b),
        mirroring `BudgetLedger.totals_per_run()` without ever
        instantiating `BudgetLedger` -- its constructor migrates the schema
        (an `ALTER TABLE`), which this read-only module must never risk
        triggering. A ledger from before the column existed is treated as
        "nothing attributable", not an error."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(calls)")}
        if "run_id" not in columns:
            return {}
        rows = conn.execute(
            "SELECT run_id, COUNT(*) FROM calls WHERE run_id IS NOT NULL GROUP BY run_id"
        ).fetchall()
        return dict(rows)

    def _calls_per_run_or_empty(self) -> dict[str, int]:
        conn = self._ledger_conn()
        if conn is None:
            return {}
        try:
            return self._calls_per_run(conn)
        finally:
            conn.close()

    def list_runs(self, filters: RunFilter) -> tuple[tuple[RunSummary, ...], int]:
        conn = _ro_connect(self._index_path)
        if conn is None:
            raise DataNotAvailable("no recordings yet (runs/index.sqlite not found)")
        calls_by_run = self._calls_per_run_or_empty()
        try:
            rows = []
            for manifest, outcome in self._all_manifests(conn):
                # A run with no outcome yet is still listed -- as
                # status="recording", never silently hidden or shown as
                # "fail" (`_run_summary` handles both null-outcome states).
                steps = self._steps_for(conn, manifest.run_id)
                calls = calls_by_run.get(manifest.run_id)
                blame = self._load_blame_doc(manifest.run_id)
                summary = self._run_summary(manifest, outcome, steps, calls, blame)
                tool_names = tuple(sorted({s.tool_name for s in steps if s.tool_name}))
                rows.append(RunSearchRow(summary=summary, tool_names=tool_names))
        finally:
            conn.close()

        rows = filter_runs(rows, filters)
        summaries = sort_runs([row.summary for row in rows], filters.sort)

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
        estimate, judge = self._blame_views(run_id)
        return RunDetail(
            run_id=manifest.run_id,
            domain=manifest.domain,
            task_id=manifest.task_id,
            agent_model=manifest.agent_model,
            user_model=manifest.user_model,
            seed=manifest.seed,
            tau2_commit=manifest.tau2_commit,
            created_at=manifest.created_at.isoformat(),
            status="complete" if outcome is not None else "recording",
            # Both `None` while recording -- never a fabricated "fail"/`0.0`.
            outcome=None if outcome is None else ("pass" if outcome.passed else "fail"),
            reward=outcome.reward if outcome else None,
            steps=step_views,
            planted_step=None,
            fault_type=None,
            estimate=estimate,
            judge=judge,
        )

    def _blame_views(self, run_id: str) -> tuple[RunEstimateView | None, JudgePanel | None]:
        """`estimate`/`judge` for `RunDetail`, read straight off P5's stored
        document -- its field names mirror these DTOs exactly (see
        `blame_store.py`), so nothing here reshapes or re-derives a
        statistic. `estimate` stays `None` when the judge never answered and
        no re-run was bought: a real outcome ("no step blamed"), not a
        fabricated zero. Both stay `None` when the run has never been
        diagnosed at all."""
        blame = self._load_blame_doc(run_id)
        if blame is None:
            return None, None
        estimate = (
            RunEstimateView.model_validate(blame["estimate"])
            if blame["estimate"] is not None
            else None
        )
        return estimate, JudgePanel.model_validate(blame["judge"])

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
        blame = self._load_blame_doc(run_id)
        if blame is None:
            raise DataNotAvailable("no re-run matrix has been recorded for any run yet")
        # An empty tuple here is honest: the diagnosis ran but the judge
        # never answered, so no re-run was bought -- not "no data".
        return RerunPage(reruns=tuple(RerunRow.model_validate(row) for row in blame["reruns"]))

    def rerun_steps(self, run_id: str, rerun_id: str) -> tuple[StepView, ...]:
        # `blame_store` records each re-run's outcome (arm/step/seed/passed/
        # calls), not its step-by-step trace -- there is nothing yet for
        # this endpoint to read, with or without a stored blame result.
        raise DataNotAvailable("no re-run step trace has been recorded for any run yet")

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
            jobs=self._read_job_statuses(),
            events=(),
        )

    def _read_job_statuses(self) -> tuple[JobStatus, ...]:
        """Reads every `runs/<phase>/status.json` present -- a long-running
        job's own report of its progress. Never invents a job that isn't
        there, and a single malformed/unreadable file is skipped (logged
        nowhere, since this module has no logging story yet, but skipped
        rather than taking down the whole live snapshot over one bad file).
        """
        if not self._runs_dir.is_dir():
            return ()
        statuses = []
        for status_path in sorted(self._runs_dir.glob(f"*/{_STATUS_FILENAME}")):
            phase_name = status_path.parent.name
            try:
                payload = json.loads(status_path.read_text())
                statuses.append(
                    JobStatus(
                        job_id=phase_name,
                        kind=payload["kind"],
                        state=payload["state"],
                        progress=payload["progress"],
                        phase=payload.get("phase", phase_name.upper()),
                        label=payload.get("label"),
                        items_done=payload.get("items_done"),
                        items_total=payload.get("items_total"),
                        model=payload.get("model"),
                        calls_spent=payload.get("calls_spent"),
                        started_at=payload.get("started_at"),
                        finished_at=payload.get("finished_at"),
                        eta_seconds=payload.get("eta_seconds"),
                        last_checkpoint_at=payload.get("last_checkpoint_at"),
                        error=payload.get("error"),
                    )
                )
            except (OSError, json.JSONDecodeError, KeyError, ValidationError):
                continue
        return tuple(statuses)

    def pr_checks(self) -> tuple[PrCheckSummary, ...]:
        raise DataNotAvailable("no PR checks have run yet (gate/action.py)")

    def pr_check_detail(self, check_id: str) -> PrCheckDetail:
        raise DataNotAvailable("no PR checks have run yet (gate/action.py)")
