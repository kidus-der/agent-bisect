"""Tests for the resumable batch recorder: checkpoints, resume, infra
aborts, and four runs recorded at once into four clean tapes.
"""

from __future__ import annotations

import json

import pytest
from agent_bisect.adapters.tau2_batch import (
    BatchItem,
    Checkpoint,
    checkpoint_path,
    items_for,
    load_all,
    load_checkpoint,
    pending,
    record_batch,
    record_one,
    save_checkpoint,
    summarise,
    tasks_from_range,
    with_task,
)
from agent_bisect.adapters.tau2_scenarios import AIRLINE_READS
from tests.tau2_offline import Store, quiet_tau2, scripted_session, spec_for

pytestmark = pytest.mark.usefixtures("_no_real_key")


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "runs")


def _spec_for(item: BatchItem):
    return with_task(spec_for(AIRLINE_READS), item)


def _run_batch(store: Store, items, *, concurrency: int = 1):
    with scripted_session(AIRLINE_READS, store.root):
        return record_batch(
            items,
            spec_for=_spec_for,
            store=store.blobs,
            tape=store.tape,
            reader=store.reader,
            root=store.root,
            concurrency=concurrency,
        )


# ---- the work list ----


def test_a_task_range_expands_in_order():
    assert tasks_from_range("0-4") == ["0", "1", "2", "3", "4"]


def test_a_task_list_and_a_single_task_both_work():
    assert tasks_from_range("0,3,7") == ["0", "3", "7"]
    assert tasks_from_range("4") == ["4"]


def test_a_range_and_a_list_can_be_mixed():
    assert tasks_from_range("0-2,9") == ["0", "1", "2", "9"]


def test_trials_multiply_the_task_list():
    items = items_for("airline", ["0", "1"], trials=2)

    assert [(item.task_id, item.trial) for item in items] == [
        ("0", 0), ("0", 1), ("1", 0), ("1", 1)
    ]


def test_a_run_id_names_the_domain_task_and_trial():
    assert BatchItem("airline", "7", 1).base_run_id == "airline-7-t1"


# ---- checkpoints ----


def test_a_finished_run_checkpoints_and_is_not_repeated(store):
    items = items_for("airline", ["0"])

    first = _run_batch(store, items)
    assert checkpoint_path(store.root, items[0]).exists()
    assert pending(store.root, items) == []

    second = _run_batch(store, items)
    assert [checkpoint.run_id for checkpoint in second] == [first[0].run_id]
    assert len(store.reader.get_steps(first[0].run_id)) == first[0].steps


def test_a_resumed_batch_records_only_what_is_missing(store):
    _run_batch(store, items_for("airline", ["0"]))

    both = _run_batch(store, items_for("airline", ["0", "1"]))

    assert sorted(checkpoint.task_id for checkpoint in both) == ["0", "1"]
    assert sorted(checkpoint.task_id for checkpoint in load_all(store.root, "airline")) == [
        "0",
        "1",
    ]


def test_a_checkpoint_records_the_reward_and_termination(store):
    [checkpoint] = _run_batch(store, items_for("airline", ["0"]))

    assert checkpoint.is_done
    assert checkpoint.reward is not None
    assert checkpoint.passed == (checkpoint.reward == 1.0)
    assert checkpoint.termination_reason == "user_stop"
    assert checkpoint.steps > 0


def test_an_unreadable_checkpoint_means_the_item_still_owes_a_run(store):
    item = BatchItem("airline", "0")
    path = checkpoint_path(store.root, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")

    assert load_checkpoint(store.root, item) is None


# ---- infra aborts are never scored ----


def test_an_infra_failure_lands_beside_the_checkpoint_not_in_it(store, monkeypatch):
    """An item that died on infrastructure stays outstanding, so the next
    resume retries it instead of scoring it as a failed run."""
    import agent_bisect.adapters.tau2_batch as batch_module

    def explode(*_args, **_kwargs):
        raise TimeoutError("the provider stopped answering")

    monkeypatch.setattr(batch_module, "record_run", explode)
    item = BatchItem("airline", "0")

    checkpoint = record_one(
        item,
        spec_for=_spec_for,
        store=store.blobs,
        tape=store.tape,
        reader=store.reader,
        root=store.root,
    )

    assert not checkpoint.is_done
    assert checkpoint.status == "aborted_infra"
    assert checkpoint.reward is None
    assert not checkpoint_path(store.root, item).exists()
    assert checkpoint_path(store.root, item).with_suffix(".error.json").exists()
    assert pending(store.root, [item]) == [item]


def test_a_later_success_clears_the_error_file(store):
    item = BatchItem("airline", "0")
    save_checkpoint(
        store.root,
        Checkpoint(
            run_id="airline-0-t0",
            domain="airline",
            task_id="0",
            trial=0,
            status="aborted_infra",
            steps=0,
            termination_reason="infrastructure_error",
        ),
    )

    _run_batch(store, [item])

    assert checkpoint_path(store.root, item).exists()
    assert not checkpoint_path(store.root, item).with_suffix(".error.json").exists()


def test_a_crashed_attempt_does_not_block_the_retrys_run_id(store, monkeypatch):
    """The tape is append-only, so a retry after a crash mid-run takes a
    fresh id rather than overwriting the evidence."""
    import agent_bisect.adapters.tau2_batch as batch_module

    item = BatchItem("airline", "0")
    _run_batch(store, [item])
    checkpoint_path(store.root, item).unlink()  # as if the process died after the run

    monkeypatch.setattr(batch_module, "record_run", batch_module.record_run)
    [retried] = _run_batch(store, [item])

    assert retried.run_id == "airline-0-t0-a2"
    assert store.reader.get_manifest("airline-0-t0") is not None


# ---- four at once ----


def test_four_runs_recorded_concurrently_produce_four_clean_tapes(store):
    items = items_for("airline", ["0", "1", "2", "3"])

    checkpoints = _run_batch(store, items, concurrency=4)

    assert len(checkpoints) == 4
    assert all(checkpoint.is_done for checkpoint in checkpoints)
    for checkpoint in checkpoints:
        steps = store.reader.get_steps(checkpoint.run_id)
        assert [step.step_idx for step in steps] == list(range(len(steps)))
        assert len(steps) == checkpoint.steps
        assert store.reader.get_outcome(checkpoint.run_id) is not None


def test_concurrent_runs_do_not_leak_steps_into_each_others_tapes(store):
    items = items_for("airline", ["0", "1", "2", "3"])

    checkpoints = _run_batch(store, items, concurrency=4)

    for checkpoint in checkpoints:
        run_ids = {step.run_id for step in store.reader.get_steps(checkpoint.run_id)}
        assert run_ids == {checkpoint.run_id}


def test_concurrently_recorded_runs_all_replay_step_identically(store):
    """A tape written under concurrency is worth nothing if it does not
    replay; this is the thread-safety check that matters."""
    from agent_bisect.adapters.tau2_replay import replay_run

    checkpoints = _run_batch(store, items_for("airline", ["0", "1", "2", "3"]), concurrency=4)

    for checkpoint in checkpoints:
        result = replay_run(checkpoint.run_id, store=store.blobs, reader=store.reader)
        assert result.steps == checkpoint.steps
        assert result.outcome is not None
        assert result.outcome.reward == checkpoint.reward


# ---- summary ----


def test_summarise_counts_only_finished_runs(store):
    checkpoints = [
        Checkpoint("a", "airline", "0", 0, "done", 10, "user_stop", reward=1.0, passed=True),
        Checkpoint("b", "airline", "1", 0, "done", 12, "user_stop", reward=0.0, passed=False),
        Checkpoint("c", "airline", "2", 0, "aborted_infra", 0, "infrastructure_error"),
    ]

    assert summarise(checkpoints) == {
        "recorded": 2,
        "aborted_infra": 1,
        "passed": 1,
        "pass_rate": 0.5,
        "steps_total": 22,
    }


def test_summarise_reports_no_pass_rate_when_nothing_finished():
    assert summarise([])["pass_rate"] is None


# ---- redaction (f) ----


def test_a_key_in_an_error_never_reaches_the_checkpoint(store, monkeypatch):
    """A synthetic key built at runtime, thrown from inside the recorder,
    must be masked everywhere the batch writes."""
    import agent_bisect.adapters.tau2_batch as batch_module

    key = "nvapi" + "-" + "B" * 64

    def explode(*_args, **_kwargs):
        raise RuntimeError(f"upstream said: Authorization: Bearer {key}")

    monkeypatch.setattr(batch_module, "record_run", explode)
    item = BatchItem("airline", "0")

    checkpoint = record_one(
        item,
        spec_for=_spec_for,
        store=store.blobs,
        tape=store.tape,
        reader=store.reader,
        root=store.root,
    )

    assert key not in (checkpoint.error or "")
    error_file = checkpoint_path(store.root, item).with_suffix(".error.json")
    assert key not in error_file.read_text()
    assert "upstream said" in json.loads(error_file.read_text())["error"]


def test_a_key_in_a_message_and_a_tool_argument_reaches_nothing_the_batch_wrote(store):
    """Rule 5, end to end: the key is built at runtime, spoken by the
    agent and passed as a tool argument, and must then appear in no blob,
    no SQLite file, no log and no checkpoint."""
    from agent_bisect.adapters.tau2_fake_llm import ScriptedToolCall, ScriptedTurn
    from agent_bisect.adapters.tau2_scenarios import Scenario

    key = "nvapi" + "-" + "C" * 64
    leaky = Scenario(
        name="leaky",
        domain="airline",
        task_id="0",
        agent=(
            ScriptedTurn(
                tool_calls=(
                    ScriptedToolCall(id="c1", name="calculate", arguments={"expression": "1 + 1"}),
                )
            ),
            ScriptedTurn(content=f"my credential is Authorization: Bearer {key}"),
            ScriptedTurn(content="Anything else?"),
        ),
        user=(
            ScriptedTurn(content=f"here is my key, keep it safe: {key}"),
            ScriptedTurn(content="###STOP###"),
        ),
    )
    with scripted_session(leaky, store.root):
        record_batch(
            [BatchItem("airline", "0")],
            spec_for=lambda item: with_task(spec_for(leaky), item),
            store=store.blobs,
            tape=store.tape,
            reader=store.reader,
            root=store.root,
        )

    found = [path for path in sorted(store.root.rglob("*")) if _contains(path, key)]

    assert found == []
    assert list(store.root.rglob("*.json")), "the scan must have had something to scan"


def _contains(path, key: str) -> bool:
    from agent_bisect.core.store import BlobStore

    if not path.is_file():
        return False
    if path.suffix == ".zst":
        # <root>/blobs/<aa>/<bb>/<digest>.zst
        return key.encode() in BlobStore(path.parents[3]).get_bytes(path.stem)
    return key.encode() in path.read_bytes()


# ---- per-run call attribution ----


def test_every_call_a_run_makes_is_attributed_to_it(store):
    """The ledger can say what each recorded run cost."""
    from agent_bisect.core.budget import BudgetLedger

    checkpoints = _run_batch(store, items_for("airline", ["0", "1"]))

    ledger = BudgetLedger(store.root / "ledger.sqlite")
    per_run = ledger.totals_per_run()

    assert sorted(per_run) == sorted(checkpoint.run_id for checkpoint in checkpoints)
    assert sum(per_run.values()) == ledger.total_calls()


def test_concurrent_runs_do_not_mix_up_whose_calls_are_whose(store):
    from agent_bisect.core.budget import BudgetLedger

    _run_batch(store, items_for("airline", ["0", "1", "2", "3"]), concurrency=4)

    per_run = BudgetLedger(store.root / "ledger.sqlite").totals_per_run()

    assert len(per_run) == 4
    # Every run of the same script costs the same number of calls, so a
    # thread picking up another thread's run id would show up here.
    assert len(set(per_run.values())) == 1
