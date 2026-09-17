"""`RealRepository` against a small, hand-built real recording (not fixtures)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from agent_bisect.core.budget import BudgetLedger, CallRecord
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step, TapeWriter
from agent_bisect.server.real_repository import RealRepository
from agent_bisect.server.repository import DataNotAvailable, RunFilter


@pytest.fixture
def empty_repo(tmp_path) -> RealRepository:
    return RealRepository(runs_dir=tmp_path / "runs")


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


def test_list_runs_cost_and_calls_are_unknown_in_real_mode(one_run_dir):
    """The ledger has no run_id column yet (P1b), so per-run cost/calls genuinely
    aren't knowable -- `None`, never a fake `0`/`0.0` that would read as "free"."""
    repo = RealRepository(runs_dir=one_run_dir)
    runs, _ = repo.list_runs(RunFilter())
    assert runs[0].cost_usd is None
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
