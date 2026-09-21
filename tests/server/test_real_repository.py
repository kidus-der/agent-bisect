"""`RealRepository` against a small, hand-built real recording (not fixtures)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from agent_bisect.attribution.blame_store import save_blame
from agent_bisect.attribution.estimate import ArmResult, RunEstimate, StepEffect
from agent_bisect.attribution.judge_view import JudgeVerdict, RankedStep
from agent_bisect.attribution.search import BlameConfig, BlameResult, RerunRecord
from agent_bisect.core.budget import BudgetLedger, CallRecord
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step, TapeWriter
from agent_bisect.server.real_repository import RealRepository
from agent_bisect.server.repository import DataNotAvailable, RunFilter

#: Every `RealRepository(...)` built below passes `runs_dir` explicitly
#: but many omit `data_dir` -- this chdirs the whole module into an
#: isolated tmp dir so that relative default can never resolve against
#: this project's own, real `data/manifest.json` (conftest.py).
pytestmark = pytest.mark.usefixtures("isolated_repo_cwd")


@pytest.fixture
def empty_repo(tmp_path) -> RealRepository:
    return RealRepository(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data")


def test_empty_real_repo_never_creates_files(empty_repo, tmp_path):
    runs_dir = tmp_path / "runs"
    with pytest.raises(DataNotAvailable):
        empty_repo.list_runs(RunFilter())
    with pytest.raises(DataNotAvailable):
        empty_repo.live_snapshot()
    with pytest.raises(DataNotAvailable):
        empty_repo.benchmark()
    with pytest.raises(DataNotAvailable):
        empty_repo.dataset(1, 10)
    with pytest.raises(DataNotAvailable):
        empty_repo.pr_checks()
    assert not runs_dir.exists()


def test_unknown_run_detail_is_key_error(empty_repo):
    with pytest.raises(KeyError):
        empty_repo.run_detail("nope")


def test_default_data_dir_is_never_this_repo_s_own(tmp_path):
    """A `RealRepository()` built with no `data_dir` must never resolve
    its relative default (`Path("data")`) against this project's own,
    now-real, frozen `data/manifest.json` -- the exact bug caught when P3
    committed one and `test_empty_real_repo_never_creates_files` (which
    forgot to isolate `data_dir`, same as every other fixture below) went
    from `DataNotAvailable` to a real dataset page. This whole module runs
    chdir'd into an isolated tmp dir (`isolated_repo_cwd`, conftest.py)
    specifically so a fixture that forgets `data_dir=` fails safe rather
    than silently reading real project data."""
    repo = RealRepository(runs_dir=tmp_path / "runs")  # data_dir intentionally omitted
    with pytest.raises(DataNotAvailable):
        repo.dataset(1, 10)


@pytest.fixture
def one_run_dir(tmp_path) -> Path:
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    store = BlobStore(runs_dir)

    manifest = RunManifest(
        run_id="real-run-1",
        domain="airline",
        task_id="refund_after_cancellation",
        agent_model="nvidia/llama-3.1-nemotron-70b-instruct",
        user_model="meta/llama-3.1-8b-instruct",
        tau2_commit="deadbeef",
        created_at=datetime.now(UTC),
    )
    writer.start_run(manifest)

    before_ref = store.put_json({"status": "open"})
    after_ref = store.put_json({"status": "closed"})
    request_ref = store.put_json({"messages": [{"role": "user", "content": "help"}]})
    response_ref = store.put_json({"content": "ok"})
    tool_result_ref = store.put_json({"reservation_id": "AB12CD"})

    step = Step(
        run_id="real-run-1",
        step_idx=0,
        actor="tool",
        request_ref=request_ref,
        response_ref=response_ref,
        tool_name="update_reservation_baggages",
        tool_args={"id": "AB12CD"},
        tool_result_ref=tool_result_ref,
        state_before=before_ref,
        state_after=after_ref,
        state_hash="hash-1",
        latency_ms=120,
        tokens_in=50,
        tokens_out=20,
    )
    writer.append_step(step)
    writer.record_outcome(Outcome(run_id="real-run-1", reward=1.0))

    ledger = BudgetLedger(db_path=runs_dir / "ledger.sqlite")
    ledger.record(
        CallRecord(
            ts=time.time(),
            phase="record",
            model="nvidia/llama-3.1-nemotron-70b-instruct",
            purpose="agent",
            status="ok",
            tokens_in=50,
            tokens_out=20,
            latency_ms=120.0,
        )
    )
    return runs_dir


def test_list_runs_reads_real_recording(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    runs, total = repo.list_runs(RunFilter())
    assert total == 1
    assert runs[0].run_id == "real-run-1"
    assert runs[0].outcome == "pass"
    assert runs[0].fault_type is None
    assert all(cell.tested is False for cell in runs[0].blame_stripe)


def test_list_runs_cost_and_calls_are_unknown_without_attribution(one_run_dir):
    """`one_run_dir`'s one ledger row has `run_id=None` (unattributed), so
    "real-run-1" itself has zero *attributable* rows -- `None`, never a
    fake `0`/`0.0` that would read as "free". `cost_usd` stays `None` even
    once `calls` is attributable (below): there's still no per-model USD
    price anywhere in this codebase to multiply by."""
    repo = RealRepository(runs_dir=one_run_dir)
    runs, _ = repo.list_runs(RunFilter())
    assert runs[0].cost_usd is None
    assert runs[0].calls is None


def test_list_runs_calls_is_real_once_the_ledger_attributes_them(one_run_dir):
    """The ledger's `calls.run_id` column (P1b) lets per-run calls be served
    for real -- no longer the `None` above once there's something to count."""
    ledger = BudgetLedger(db_path=one_run_dir / "ledger.sqlite")
    for _ in range(3):
        ledger.record(
            CallRecord(
                ts=time.time(),
                phase="p1",
                model="nvidia/llama-3.1-nemotron-70b-instruct",
                purpose="agent",
                status="ok",
                tokens_in=10,
                tokens_out=5,
                latency_ms=100.0,
                run_id="real-run-1",
            )
        )
    # A call belonging to no run (a rate-limit ramp, a model probe) must
    # never be attributed to a run it didn't happen for.
    ledger.record(
        CallRecord(
            ts=time.time(),
            phase="p0",
            model="m",
            purpose="probe",
            status="ok",
            tokens_in=1,
            tokens_out=1,
            latency_ms=1.0,
            run_id=None,
        )
    )

    repo = RealRepository(runs_dir=one_run_dir)
    runs, _ = repo.list_runs(RunFilter())
    assert runs[0].calls == 3
    assert runs[0].cost_usd is None  # still no per-model USD price anywhere


def test_list_runs_calls_is_none_for_a_run_with_no_ledger_rows(one_run_dir):
    """A second run recorded before the ledger's run_id column existed (or
    simply never called anything, e.g. still-recording) genuinely has no
    attributable calls -- `None`, not `0`, even though the ledger file
    itself now exists and has rows for a different run."""
    ledger = BudgetLedger(db_path=one_run_dir / "ledger.sqlite")
    ledger.record(
        CallRecord(
            ts=time.time(),
            phase="p1",
            model="m",
            purpose="agent",
            status="ok",
            tokens_in=1,
            tokens_out=1,
            latency_ms=1.0,
            run_id="some-other-run",
        )
    )

    repo = RealRepository(runs_dir=one_run_dir)
    runs, _ = repo.list_runs(RunFilter())
    assert runs[0].run_id == "real-run-1"
    assert runs[0].calls is None


def test_sparkline_latency_and_tokens_are_none_when_the_step_never_recorded_them(tmp_path):
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    writer.start_run(
        RunManifest(
            run_id="no-telemetry-run",
            domain="airline",
            task_id="refund_after_cancellation",
            agent_model="m",
            user_model="u",
            tau2_commit="c",
            created_at=datetime.now(UTC),
        )
    )
    writer.append_step(
        Step(
            run_id="no-telemetry-run",
            step_idx=0,
            actor="agent",
            state_before="a",
            state_after="a",
            state_hash="h",
            # latency_ms / tokens_in / tokens_out deliberately omitted (None).
        )
    )
    writer.record_outcome(Outcome(run_id="no-telemetry-run", reward=1.0))

    repo = RealRepository(runs_dir=runs_dir)
    runs, _ = repo.list_runs(RunFilter())
    point = runs[0].sparkline[0]
    assert point.latency_ms is None
    assert point.tokens is None


def test_run_detail_reward_is_none_when_no_outcome_is_recorded_yet(tmp_path):
    """A run mid-recording (no outcome row yet) has no honest reward to report."""
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    writer.start_run(
        RunManifest(
            run_id="in-progress-run",
            domain="retail",
            task_id="cancel_before_ship",
            agent_model="m",
            user_model="u",
            tau2_commit="c",
            created_at=datetime.now(UTC),
        )
    )
    # No outcome row written -- the run is still being recorded.

    repo = RealRepository(runs_dir=runs_dir)
    detail = repo.run_detail("in-progress-run")
    assert detail.reward is None


def test_run_detail_reads_real_steps_and_state_change(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    detail = repo.run_detail("real-run-1")
    assert detail.outcome == "pass"
    assert len(detail.steps) == 1
    assert detail.steps[0].state_changed is True
    assert detail.estimate is None
    assert detail.judge is None


def test_step_payload_reads_real_blob_store(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    payload = repo.step_payload("real-run-1", 0)
    assert payload.tool_result is not None
    assert payload.tool_result["reservation_id"] == "AB12CD"


def test_state_diff_reads_real_before_after(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    diff = repo.state_diff("real-run-1", 0)
    assert any(entry.path == "status" for entry in diff.entries)


def test_intervention_diff_is_none_for_real_run(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    assert repo.intervention_diff("real-run-1", 0) is None


def test_reruns_not_available_for_real_run(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    with pytest.raises(DataNotAvailable):
        repo.reruns("real-run-1")


def test_live_snapshot_reflects_real_ledger(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    snapshot = repo.live_snapshot()
    assert snapshot.budget.used == 1
    assert snapshot.budget.cap is None


def test_meta_reports_real_source(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    meta = repo.meta()
    assert meta.data_source == "real"
    assert meta.simulated is False


def test_redacted_secret_never_resurfaces_through_real_repository(tmp_path):
    """`BlobStore.put_bytes` redacts on write; the real repository must never undo that."""
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    store = BlobStore(runs_dir)

    manifest = RunManifest(
        run_id="secret-run",
        domain="retail",
        task_id="return_window_dispute",
        agent_model="m",
        user_model="u",
        tau2_commit="c",
        created_at=datetime.now(UTC),
    )
    writer.start_run(manifest)

    fake_key = "nv" + "api-" + "SHOULDNEVERSURVIVE0000000000"
    tool_result_ref = store.put_json({"note": f"key was {fake_key}"})
    before_ref = store.put_json({})
    after_ref = store.put_json({})
    step = Step(
        run_id="secret-run",
        step_idx=0,
        actor="tool",
        tool_name="get_order_details",
        tool_result_ref=tool_result_ref,
        state_before=before_ref,
        state_after=after_ref,
        state_hash="h",
    )
    writer.append_step(step)
    writer.record_outcome(Outcome(run_id="secret-run", reward=0.0))

    repo = RealRepository(runs_dir=runs_dir)
    payload = repo.step_payload("secret-run", 0)
    assert "SHOULDNEVERSURVIVE" not in str(payload.tool_result)


def _write_run(
    writer: TapeWriter, run_id: str, n_steps: int, *, record_outcome: bool = True
) -> None:
    writer.start_run(
        RunManifest(
            run_id=run_id,
            domain="airline",
            task_id="refund_after_cancellation",
            agent_model="m",
            user_model="u",
            tau2_commit="c",
            created_at=datetime.now(UTC),
        )
    )
    for idx in range(n_steps):
        writer.append_step(
            Step(
                run_id=run_id,
                step_idx=idx,
                actor="agent",
                state_before="a",
                state_after="a",
                state_hash="h",
            )
        )
    if record_outcome:
        writer.record_outcome(Outcome(run_id=run_id, reward=1.0))


def test_list_runs_honours_the_sort_field_in_real_mode(tmp_path):
    """`run_id` order and `n_steps` order deliberately disagree here: `run-a`
    sorts first alphabetically but has *more* steps than `run-b`. A repo
    that (bug) sorts by `run_id` and merely reads the `-` prefix for
    direction -- ignoring which field was actually asked for -- would give
    `["run-b", "run-a"]` (run_id descending) instead of the correct
    `["run-a", "run-b"]` (n_steps descending)."""
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    _write_run(writer, "run-a", n_steps=3)
    _write_run(writer, "run-b", n_steps=1)

    repo = RealRepository(runs_dir=runs_dir)
    runs, _ = repo.list_runs(RunFilter(sort="-n_steps"))
    assert [r.run_id for r in runs] == ["run-a", "run-b"]


@pytest.fixture
def one_complete_one_recording_dir(tmp_path) -> Path:
    """A run with an outcome ("complete") alongside one still being recorded
    (no outcome row) -- the recording run must never be reported as "fail"."""
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    _write_run(writer, "complete-run", n_steps=2)
    _write_run(writer, "recording-run", n_steps=1, record_outcome=False)
    return runs_dir


def test_run_detail_status_is_recording_without_an_outcome_row(one_complete_one_recording_dir):
    repo = RealRepository(runs_dir=one_complete_one_recording_dir)
    detail = repo.run_detail("recording-run")
    assert detail.status == "recording"
    assert detail.outcome is None
    assert detail.reward is None


def test_run_detail_status_is_complete_with_an_outcome_row(one_complete_one_recording_dir):
    repo = RealRepository(runs_dir=one_complete_one_recording_dir)
    detail = repo.run_detail("complete-run")
    assert detail.status == "complete"
    assert detail.outcome == "pass"


def test_list_runs_includes_recording_runs_not_just_complete_ones(
    one_complete_one_recording_dir,
):
    repo = RealRepository(runs_dir=one_complete_one_recording_dir)
    runs, total = repo.list_runs(RunFilter())
    assert total == 2
    by_id = {r.run_id: r for r in runs}
    assert by_id["recording-run"].status == "recording"
    assert by_id["recording-run"].outcome is None
    assert by_id["complete-run"].status == "complete"
    assert by_id["complete-run"].outcome == "pass"


def test_list_runs_outcome_filter_excludes_recording_runs(one_complete_one_recording_dir):
    repo = RealRepository(runs_dir=one_complete_one_recording_dir)
    runs, total = repo.list_runs(RunFilter(outcome="pass"))
    assert total == 1
    assert runs[0].run_id == "complete-run"


def test_list_runs_status_filter_selects_only_recording_runs(one_complete_one_recording_dir):
    repo = RealRepository(runs_dir=one_complete_one_recording_dir)
    runs, total = repo.list_runs(RunFilter(status="recording"))
    assert total == 1
    assert runs[0].run_id == "recording-run"


def test_search_reports_status_for_both_run_kinds(one_complete_one_recording_dir):
    repo = RealRepository(runs_dir=one_complete_one_recording_dir)
    results = repo.search("run")
    by_id = {hit.id: hit for hit in results.hits}
    assert by_id["recording-run"].status == "recording"
    assert by_id["complete-run"].status == "complete"


@pytest.fixture
def two_runs_one_with_a_tool_dir(tmp_path) -> Path:
    """`run-with-tool` calls `book_reservation`; `run-without-tool` has an
    agent-only step -- the q filter's tool-name reach has to distinguish them
    even though neither run's `RunSummary` itself carries a tool name."""
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    _write_run(writer, "run-without-tool", n_steps=1)
    writer.start_run(
        RunManifest(
            run_id="run-with-tool",
            domain="airline",
            task_id="refund_after_cancellation",
            agent_model="m",
            user_model="u",
            tau2_commit="c",
            created_at=datetime.now(UTC),
        )
    )
    writer.append_step(
        Step(
            run_id="run-with-tool",
            step_idx=0,
            actor="tool",
            tool_name="book_reservation",
            state_before="a",
            state_after="a",
            state_hash="h",
        )
    )
    writer.record_outcome(Outcome(run_id="run-with-tool", reward=1.0))
    return runs_dir


def test_q_filter_reaches_tool_names_in_real_mode(two_runs_one_with_a_tool_dir):
    repo = RealRepository(runs_dir=two_runs_one_with_a_tool_dir)
    runs, total = repo.list_runs(RunFilter(q="book_reservation"))
    assert total == 1
    assert runs[0].run_id == "run-with-tool"


def test_q_filter_is_case_insensitive_in_real_mode(two_runs_one_with_a_tool_dir):
    repo = RealRepository(runs_dir=two_runs_one_with_a_tool_dir)
    runs, _ = repo.list_runs(RunFilter(q="BOOK_RESERVATION"))
    assert [r.run_id for r in runs] == ["run-with-tool"]


def test_fault_type_none_matches_every_real_run(two_runs_one_with_a_tool_dir):
    """Real recordings never have a planted fault -- `fault_type=none` must
    match all of them, never zero."""
    repo = RealRepository(runs_dir=two_runs_one_with_a_tool_dir)
    runs, total = repo.list_runs(RunFilter(fault_type="none"))
    assert total == 2


def test_fault_type_specific_value_matches_no_real_run(two_runs_one_with_a_tool_dir):
    repo = RealRepository(runs_dir=two_runs_one_with_a_tool_dir)
    runs, total = repo.list_runs(RunFilter(fault_type="wrong_value"))
    assert total == 0


def test_evaluator_actor_step_is_reported_not_rejected(tmp_path):
    """`core.tape.Actor` includes "evaluator" (judge/evaluation steps); the
    server's own `Actor` type must be able to represent whatever a real
    recording can actually contain."""
    runs_dir = tmp_path / "runs"
    writer = TapeWriter(runs_dir)
    writer.start_run(
        RunManifest(
            run_id="evaluated-run",
            domain="airline",
            task_id="refund_after_cancellation",
            agent_model="m",
            user_model="u",
            tau2_commit="c",
            created_at=datetime.now(UTC),
        )
    )
    writer.append_step(
        Step(
            run_id="evaluated-run",
            step_idx=0,
            actor="evaluator",
            state_before="a",
            state_after="a",
            state_hash="h",
        )
    )
    writer.record_outcome(Outcome(run_id="evaluated-run", reward=1.0))

    repo = RealRepository(runs_dir=runs_dir)
    runs, _ = repo.list_runs(RunFilter())
    assert runs[0].sparkline[0].actor == "evaluator"
    detail = repo.run_detail("evaluated-run")
    assert detail.steps[0].actor == "evaluator"


def test_live_snapshot_has_no_jobs_when_no_status_files_exist(one_run_dir):
    """No `runs/<phase>/status.json` anywhere -- an honest empty tuple, not
    an invented job."""
    repo = RealRepository(runs_dir=one_run_dir)
    assert repo.live_snapshot().jobs == ()


def test_live_snapshot_reads_a_real_job_status_file(one_run_dir):
    """The runs/<phase>/status.json convention (documented in
    docs/design/api-contract.md): a long-running job writes its own
    progress there, and the live snapshot reports exactly that, never a
    fabricated field it didn't provide."""
    phase_dir = one_run_dir / "p1"
    phase_dir.mkdir()
    (phase_dir / "status.json").write_text(
        json.dumps(
            {
                "kind": "record",
                "state": "running",
                "progress": 0.45,
                "label": "tau2 run recording",
                "items_done": 9,
                "items_total": 20,
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "calls_spent": 812,
                "started_at": "2026-09-17T09:00:00Z",
                "last_checkpoint_at": "2026-09-17T09:12:00Z",
                "eta_seconds": 640.0,
            }
        )
    )

    repo = RealRepository(runs_dir=one_run_dir)
    jobs = repo.live_snapshot().jobs
    assert len(jobs) == 1
    job = jobs[0]
    assert job.job_id == "p1"
    assert job.phase == "P1"
    assert job.kind == "record"
    assert job.state == "running"
    assert job.progress == 0.45
    assert job.items_done == 9
    assert job.items_total == 20
    assert job.model == "nvidia/nemotron-3-super-120b-a12b"
    assert job.calls_spent == 812
    assert job.eta_seconds == 640.0
    # Never invented: this status.json had no error field.
    assert job.error is None


def test_live_snapshot_skips_a_malformed_status_file(one_run_dir):
    """A single unreadable/invalid status.json must not take down the
    whole live snapshot -- it's skipped, not fatal."""
    phase_dir = one_run_dir / "p3"
    phase_dir.mkdir()
    (phase_dir / "status.json").write_text("{not valid json")

    repo = RealRepository(runs_dir=one_run_dir)
    assert repo.live_snapshot().jobs == ()


def test_live_snapshot_reads_multiple_phase_status_files(one_run_dir):
    p1 = one_run_dir / "p1"
    p1.mkdir()
    (p1 / "status.json").write_text(
        json.dumps({"kind": "record", "state": "queued", "progress": 0.0})
    )
    p5 = one_run_dir / "p5"
    p5.mkdir()
    (p5 / "status.json").write_text(
        json.dumps(
            {
                "kind": "eval",
                "state": "done",
                "progress": 1.0,
                "finished_at": "2026-09-17T10:00:00Z",
            }
        )
    )

    repo = RealRepository(runs_dir=one_run_dir)
    jobs = {job.job_id: job for job in repo.live_snapshot().jobs}
    assert set(jobs) == {"p1", "p5"}
    assert jobs["p1"].state == "queued"
    assert jobs["p5"].state == "done"


# --- Blame results (P5's `runs/blame/<run_id>.json` convention) -----------


def _blame_result(
    *, run_id: str = "real-run-1", step: int = 5, estimate: bool = True
) -> BlameResult:
    """Field names mirror `schemas_runs` exactly (see `blame_store.py`'s
    docstring), so the repository under test should need no reshaping."""
    verdict = JudgeVerdict(
        item_id="item-1",
        protocol="all_at_once",
        decisive_step=step if estimate else None,
        ranking=(RankedStep(step=step, rank=1, score=0.9, rationale="wrong value"),)
        if estimate
        else (),
        rationale="the lookup was wrong" if estimate else "",
        calls=1,
        parse_failed=not estimate,
        failure_reason=None if estimate else "no JSON object",
    )
    run_estimate = (
        RunEstimate(
            step_effects=(
                StepEffect(
                    step=step,
                    treated=ArmResult(14, 16),
                    control=ArmResult(1, 16),
                    effect=0.8125,
                    ci_low=0.55,
                    ci_high=0.94,
                    n_batches=4,
                    stop_reason="blameworthy",
                    decision_conf=0.95,
                    decision_ci_low=0.5,
                ),
            ),
            blamed_step=step,
            control_mode="shared",
            control_fork_step=max(step - 2, 0),
            treated_reruns=16,
            control_reruns=16,
            sampler_calls=5,
        )
        if estimate
        else None
    )
    return BlameResult(
        item_id="item-1",
        run_id=run_id,
        method="bisect",
        blamed_step=step if estimate else None,
        estimate=run_estimate,
        reruns=(
            RerunRecord(f"{run_id}-t{step}-abc", "treated", step, 11, True, 12, 9),
            RerunRecord(
                f"{run_id}-c{max(step - 2, 0)}-def",
                "control",
                max(step - 2, 0),
                12,
                False,
                12,
                9,
            ),
        )
        if estimate
        else (),
        judge=verdict,
        shortlist=(step,) if estimate else (),
        tested_steps=(step,) if estimate else (),
        interventions={step: "truthful_tool_result"} if estimate else {},
        untestable=(),
        judge_calls=1,
        replay_calls=18 if estimate else 0,
        config=BlameConfig(),
    )


def test_run_detail_reads_a_stored_blame_result(one_run_dir):
    save_blame(one_run_dir, _blame_result())
    repo = RealRepository(runs_dir=one_run_dir)

    detail = repo.run_detail("real-run-1")

    assert detail.estimate is not None
    assert detail.estimate.blamed_step == 5
    assert detail.estimate.step_effects[0].effect == 0.8125
    assert detail.estimate.config.shortlist_m == 3
    assert detail.judge is not None
    assert detail.judge.all_at_once[0].step == 5


def test_run_detail_estimate_is_none_when_the_judge_never_answered(one_run_dir):
    """`estimate` is `null` when the judge answered nothing and no re-run was
    bought -- a real outcome ("no step blamed"), never a fabricated zero."""
    save_blame(one_run_dir, _blame_result(estimate=False))
    repo = RealRepository(runs_dir=one_run_dir)

    detail = repo.run_detail("real-run-1")

    assert detail.estimate is None
    assert detail.judge is not None
    assert detail.judge.all_at_once == ()


def test_run_detail_estimate_stays_none_without_a_stored_blame_result(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    detail = repo.run_detail("real-run-1")
    assert detail.estimate is None
    assert detail.judge is None


def test_list_runs_blame_stripe_reflects_a_stored_result(one_run_dir):
    """`one_run_dir` has exactly one step, at `step_idx=0` -- blame it."""
    save_blame(one_run_dir, _blame_result(step=0))
    repo = RealRepository(runs_dir=one_run_dir)

    runs, _ = repo.list_runs(RunFilter())

    assert runs[0].decisive_step == 0
    assert runs[0].blame_stripe[0].tested is True
    assert runs[0].blame_stripe[0].effect == 0.8125


def test_list_runs_blame_stripe_is_untested_without_a_stored_result(one_run_dir):
    repo = RealRepository(runs_dir=one_run_dir)
    runs, _ = repo.list_runs(RunFilter())
    assert runs[0].decisive_step is None
    assert all(cell.tested is False for cell in runs[0].blame_stripe)


def test_reruns_reads_the_stored_rerun_matrix(one_run_dir):
    save_blame(one_run_dir, _blame_result())
    repo = RealRepository(runs_dir=one_run_dir)

    page = repo.reruns("real-run-1")

    assert [row.rerun_id for row in page.reruns] == ["real-run-1-t5-abc", "real-run-1-c3-def"]
    # (control fork step for `step=5` is `max(5-2, 0) == 3`, matching the id above)
    assert page.reruns[0].arm == "treated"


def test_reruns_is_an_empty_page_when_the_stored_result_bought_none(one_run_dir):
    """A judge that never answered bought no re-runs -- an honest empty
    matrix, not `DataNotAvailable` (the diagnosis did run)."""
    save_blame(one_run_dir, _blame_result(estimate=False))
    repo = RealRepository(runs_dir=one_run_dir)

    page = repo.reruns("real-run-1")

    assert page.reruns == ()


def test_rerun_steps_stay_unavailable_even_with_a_stored_blame_result(one_run_dir):
    """`blame_store` records each re-run's outcome, not its step-by-step
    trace -- there is nothing here yet for `rerun_steps` to read."""
    save_blame(one_run_dir, _blame_result())
    repo = RealRepository(runs_dir=one_run_dir)

    with pytest.raises(DataNotAvailable):
        repo.rerun_steps("real-run-1", "real-run-1-t5-abc")


# --- PR checks (P7's `runs/gate/<check_id>/result.json` convention) -------


def _write_gate_result(
    runs_dir: Path,
    check_id: str,
    *,
    base_ref: str = "main",
    head_ref: str = "feature-x",
    is_regression: bool = True,
    base_value: float = 0.9167,
    base_n: int = 24,
    head_value: float = 0.625,
    head_n: int = 24,
    p_value: float = 0.0162,
    decisive_step_head: int | None = 7,
    scenarios: list[dict] | None = None,
) -> None:
    """`agent_bisect.gate.action.to_result_json`'s documented shape --
    `ci_low`/`ci_high` are `null` on disk today; the repository is expected
    to compute a real Wilson interval from `value`/`n` instead."""
    check_dir = runs_dir / "gate" / check_id
    check_dir.mkdir(parents=True)
    result = {
        "base_ref": base_ref,
        "head_ref": head_ref,
        "suite": "demo",
        "runs_per_scenario": 4,
        "is_regression": is_regression,
        "base_pass_rate": {"value": base_value, "ci_low": None, "ci_high": None, "n": base_n},
        "head_pass_rate": {"value": head_value, "ci_low": None, "ci_high": None, "n": head_n},
        "p_value": p_value,
        "decisive_step_base": None,
        "decisive_step_head": decisive_step_head,
        "scenarios": scenarios
        if scenarios is not None
        else [
            {
                "scenario": "reschedule_flight_change",
                "base_pass_rate": 0.75,
                "head_pass_rate": 0.25,
                "n": 4,
            },
            # a scenario new-in-head: no base run to compare against.
            {
                "scenario": "new_in_head_scenario",
                "base_pass_rate": None,
                "head_pass_rate": 1.0,
                "n": 4,
            },
        ],
        "comment_markdown": "Bisect · agent regression detected\ndetails -> bisect serve",
    }
    (check_dir / "result.json").write_text(json.dumps(result))


def test_pr_checks_lists_stored_gate_results(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_gate_result(runs_dir, "abc123")
    repo = RealRepository(runs_dir=runs_dir)

    checks = repo.pr_checks()

    assert len(checks) == 1
    check = checks[0]
    assert check.check_id == "abc123"
    assert check.pr_number is None
    assert check.title == "main → feature-x"
    assert check.is_regression is True
    assert check.base_pass_rate == 0.9167
    assert check.head_pass_rate == 0.625
    assert check.p_value == 0.0162


def test_pr_check_detail_reads_the_stored_result(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_gate_result(runs_dir, "abc123")
    repo = RealRepository(runs_dir=runs_dir)

    detail = repo.pr_check_detail("abc123")

    assert detail.check_id == "abc123"
    assert detail.pr_number is None
    assert detail.decisive_step_base is None
    assert detail.decisive_step_head == 7
    assert detail.base_pass_rate.value == 0.9167
    assert (
        detail.base_pass_rate.ci_low < detail.base_pass_rate.value < detail.base_pass_rate.ci_high
    )
    assert detail.scenarios[0].base_pass_rate == 0.75
    assert detail.scenarios[1].base_pass_rate is None
    assert "regression detected" in detail.comment_markdown


def test_pr_check_detail_unknown_check_id_is_key_error(tmp_path):
    runs_dir = tmp_path / "runs"
    (runs_dir / "gate").mkdir(parents=True)
    repo = RealRepository(runs_dir=runs_dir)
    with pytest.raises(KeyError):
        repo.pr_check_detail("nope")


def test_pr_checks_skips_a_malformed_result_file(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_gate_result(runs_dir, "good")
    bad_dir = runs_dir / "gate" / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "result.json").write_text("{not json")
    repo = RealRepository(runs_dir=runs_dir)

    checks = repo.pr_checks()

    assert [c.check_id for c in checks] == ["good"]


def _write_p7_local_gate_result(runs_dir: Path, check_id: str) -> None:
    """P7's own demo-suite runs: real `bisect gate` invocations that passed
    a custom `--out runs/p7/local/<check_id>` instead of the documented
    default -- same `result.json` shape, different directory."""
    check_dir = runs_dir / "p7" / "local" / check_id
    check_dir.mkdir(parents=True)
    result = {
        "base_ref": "main",
        "head_ref": f"demo/{check_id}",
        "suite": "demo",
        "runs_per_scenario": 4,
        "is_regression": True,
        "base_pass_rate": {"value": 0.875, "ci_low": None, "ci_high": None, "n": 32},
        "head_pass_rate": {"value": 0.4375, "ci_low": None, "ci_high": None, "n": 32},
        "p_value": 0.0002,
        "decisive_step_base": None,
        "decisive_step_head": 2,
        "scenarios": [],
        "comment_markdown": "Bisect · agent regression detected",
    }
    (check_dir / "result.json").write_text(json.dumps(result))


def test_pr_checks_also_finds_p7s_local_demo_suite_results(tmp_path):
    """`runs/gate/` (the documented convention) is empty until someone runs
    `bisect gate` with no `--out`; P7's own real runs used a custom `--out`
    under `runs/p7/local/` and must still surface as real PR checks."""
    runs_dir = tmp_path / "runs"
    _write_p7_local_gate_result(runs_dir, "demo_p7-id-slip-100")
    repo = RealRepository(runs_dir=runs_dir)

    checks = repo.pr_checks()

    assert [c.check_id for c in checks] == ["demo_p7-id-slip-100"]
    detail = repo.pr_check_detail("demo_p7-id-slip-100")
    assert detail.is_regression is True


def test_pr_checks_prefers_runs_gate_over_p7_local_on_a_check_id_collision(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_gate_result(runs_dir, "same-id", head_ref="from-runs-gate")
    _write_p7_local_gate_result(runs_dir, "same-id")
    repo = RealRepository(runs_dir=runs_dir)

    checks = repo.pr_checks()

    assert len(checks) == 1
    assert checks[0].title == "main → from-runs-gate"
