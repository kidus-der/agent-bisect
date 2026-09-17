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
