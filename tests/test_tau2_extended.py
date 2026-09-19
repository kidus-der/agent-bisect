"""Rebuilding items for rejected candidates, from the tape.

`docs/decisions/0021-p3-outcome.md`: the extended set is built from
recordings that already exist, most of which were judged before the
pipeline kept the item on a rejected record. Everything but the mutation's
own account comes back off the tape.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent_bisect.adapters.tau2_extended import extended_items
from agent_bisect.adapters.tau2_fault_injector import FaultSpec, with_injector
from agent_bisect.bench.journal import Journal
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step, TapeWriter

FAULT = FaultSpec(tool_name="get_reservation_details", tool_args={"reservation_id": "HATHAT"},
                  content='{"status": "pending"}', step_idx=4, fault_type="stale_record")


def _tape(root, *, faulted_passes: tuple[bool, ...]):
    store, tape = BlobStore(root), TapeWriter(root)
    ref = store.put_json({"id": "c1", "role": "tool", "requestor": "assistant",
                          "error": False, "content": '{"status": "confirmed"}'})
    tape.start_run(RunManifest(run_id="airline-1-t0", domain="airline", task_id="1",
                               agent_model="a", user_model="u", tau2_commit="x",
                               created_at=datetime.now(UTC)))
    tape.append_step(Step(run_id="airline-1-t0", step_idx=4, actor="tool",
                          tool_name=FAULT.tool_name, tool_args=dict(FAULT.tool_args),
                          tool_result_ref=ref, state_before="a" * 64, state_after="b" * 64,
                          state_hash="c" * 64))
    for index, passed in enumerate(faulted_passes):
        run_id = f"airline-1-t0-k4-stale_record-s{index}"
        tape.start_run(RunManifest(
            run_id=run_id, domain="airline", task_id="1", agent_model="a", user_model="u",
            params=with_injector({}, FAULT), tau2_commit="x", created_at=datetime.now(UTC),
            parent_run_id="airline-1-t0", fork_step=4,
        ))
        tape.record_outcome(Outcome(run_id=run_id, reward=1.0 if passed else 0.0))
    return store


def _journal(root, *, rate: float, status: str = "rejected"):
    journal = Journal(root)
    journal.write("stability", "airline-1-t0", {"stable": True, "rate": 1.0})
    journal.write("candidate", "airline-1-t0-k4", {
        "status": status, "reason_code": "kept" if status == "kept" else "not_flipped",
        "base_run_id": "airline-1-t0", "planted_step": 4,
        "position_bucket": "middle", "fault_type": "stale_record",
        "faulted_pass_rate": rate,
    })
    return journal


def _items(tmp_path, *, rate, faulted_passes=(True, False, True, False), threshold=0.5, **kw):
    runs = tmp_path / "runs"
    store = _tape(runs, faulted_passes=faulted_passes)
    from agent_bisect.core.tape import TapeReader

    return list(extended_items(_journal(tmp_path / "p3", rate=rate, **kw),
                               reader=TapeReader(runs), store=store,
                               runs_dir=runs, threshold=threshold))


def test_a_weaker_fault_is_rebuilt_from_the_tape(tmp_path):
    items = _items(tmp_path, rate=0.5)

    assert len(items) == 1
    item = items[0]
    assert item["planted_step"] == 4
    assert item["fault_type"] == "stale_record"
    assert item["run_id"].endswith("-s1")
    assert item["reconstructed"] is True
    assert item["intervention"]["fields"]["new_result"]["content"] == FAULT.content


def test_a_candidate_above_the_threshold_is_left_out(tmp_path):
    assert _items(tmp_path, rate=0.75) == []


def test_a_kept_candidate_is_the_callers_already(tmp_path):
    assert _items(tmp_path, rate=0.0, status="kept") == []


def test_a_candidate_whose_reruns_all_passed_yields_nothing(tmp_path):
    assert _items(tmp_path, rate=0.5, faulted_passes=(True, True, True, True)) == []


def test_the_oracle_is_the_base_runs_own_recorded_result(tmp_path):
    item = _items(tmp_path, rate=0.5)[0]

    assert item["oracle"]["step_idx"] == 4
    assert len(item["oracle"]["tool_result_ref"]) == 64
