"""End-to-end recorder tests: tau2's real orchestrator, environment and
evaluator, a scripted model, sockets blocked.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from agent_bisect.adapters.tau2 import (
    UNKNOWN_COMMIT,
    Tau2Recorder,
    record_run,
    recording_hook,
    tau2_commit,
)
from agent_bisect.adapters.tau2_scenarios import (
    AGENT_MODEL,
    AIRLINE_READS,
    AIRLINE_WRITES,
    RETAIL_WRITES,
    SCENARIOS,
    USER_MODEL,
)
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
from agent_bisect.core.llm import RecordingError
from agent_bisect.core.tape import canonical_request_hash
from tests.tau2_offline import Store, quiet_tau2, record, scripted_session, spec_for

pytestmark = pytest.mark.usefixtures("_no_real_key")


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "runs")


# ---- one recorded run ----


def test_records_a_manifest_pinning_everything_that_moves(store):
    record(AIRLINE_READS, store, run_id="r1")

    manifest = store.reader.get_manifest("r1")

    assert manifest.domain == "airline"
    assert manifest.task_id == AIRLINE_READS.task_id
    assert manifest.agent_model == AGENT_MODEL
    assert manifest.user_model == USER_MODEL
    assert manifest.seed == 42
    assert manifest.params["temperature"] == 0.0
    assert manifest.tau2_commit != UNKNOWN_COMMIT


def test_records_every_llm_call_and_every_tool_execution(store):
    recorded, llm = record(AIRLINE_READS, store, run_id="r1")

    steps = store.reader.get_steps("r1")
    llm_steps = [step for step in steps if step.actor in {"agent", "user", "evaluator"}]
    tool_steps = [step for step in steps if step.actor == "tool"]

    assert len(llm_steps) == llm.calls
    # Three scripted tool calls: two in one agent turn, one in the next.
    assert len(tool_steps) == 3
    assert recorded.steps == len(steps)


def test_step_indices_are_contiguous_and_in_order(store):
    record(AIRLINE_READS, store, run_id="r1")

    steps = store.reader.get_steps("r1")

    assert [step.step_idx for step in steps] == list(range(len(steps)))


def test_a_multi_tool_agent_turn_becomes_one_row_per_tool(store):
    record(AIRLINE_READS, store, run_id="r1")

    names = [s.tool_name for s in store.reader.get_steps("r1") if s.actor == "tool"]

    assert names[:2] == ["list_all_airports", "get_reservation_details"]


def test_records_the_agent_and_the_user_simulator_separately(store):
    recorded, _ = record(AIRLINE_READS, store, run_id="r1")

    assert recorded.llm_calls_by_actor["agent"] > 0
    assert recorded.llm_calls_by_actor["user"] > 0


def test_records_a_tool_error_as_a_step_not_a_crash(store):
    """A lookup of a reservation that does not exist must be recorded,
    with the environment's error text, like any other step."""
    record(AIRLINE_READS, store, run_id="r1")

    steps = store.reader.get_steps("r1")
    failed = next(s for s in steps if s.tool_name == "get_reservation_details")
    result = store.blobs.get_json(failed.tool_result_ref)

    assert result["error"] is True
    assert "Error" in result["content"]


def test_records_the_request_hash_of_every_llm_step(store):
    record(AIRLINE_READS, store, run_id="r1")

    for step in store.reader.get_steps("r1"):
        if step.actor in {"agent", "user"}:
            recorded_request = store.blobs.get_json(step.request_ref)
            assert step.request_hash == canonical_request_hash(recorded_request)


def test_records_the_response_verbatim(store):
    record(AIRLINE_READS, store, run_id="r1")

    first_llm = next(s for s in store.reader.get_steps("r1") if s.actor == "user")
    response = store.blobs.get_json(first_llm.response_ref)

    assert response["choices"][0]["message"]["content"] == AIRLINE_READS.user[0].content


def test_records_an_outcome_with_the_tau2_reward_and_breakdown(store):
    recorded, _ = record(AIRLINE_READS, store, run_id="r1")

    outcome = store.reader.get_outcome("r1")

    assert outcome is not None
    assert outcome.reward == recorded.outcome.reward
    assert outcome.passed == (outcome.reward == 1.0)
    assert outcome.termination_reason == "user_stop"
    assert "reward_basis" in store.blobs.get_json(outcome.breakdown_ref)


# ---- the world around each step ----


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_every_step_chains_the_world_from_the_previous_one(scenario, tmp_path):
    """`state_hash_before` of step k is `state_hash` of step k-1: the tape
    describes one continuous world, not a series of unrelated snapshots."""
    store = Store(tmp_path / scenario.name)
    record(scenario, store, run_id="r1")

    steps = store.reader.get_steps("r1")

    for previous, current in zip(steps, steps[1:], strict=False):
        assert current.state_hash_before == previous.state_hash


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_llm_steps_leave_the_world_untouched(scenario, tmp_path):
    store = Store(tmp_path / scenario.name)
    record(scenario, store, run_id="r1")

    for step in store.reader.get_steps("r1"):
        if step.actor != "tool":
            assert step.state_hash_before == step.state_hash


def test_write_tools_move_the_recorded_state_hash(store):
    record(AIRLINE_WRITES, store, run_id="r1")

    booked = next(s for s in store.reader.get_steps("r1") if s.tool_name == "book_reservation")

    assert booked.state_hash_before != booked.state_hash


def test_restoring_any_steps_recorded_state_reproduces_its_recorded_hash(store):
    """The P1 gate criterion, on one scripted run."""
    from agent_bisect.adapters.tau2 import build_orchestrator

    record(AIRLINE_WRITES, store, run_id="r1")
    steps = store.reader.get_steps("r1")

    for step in steps:
        fresh = build_orchestrator(spec_for(AIRLINE_WRITES), "probe").environment
        snapshotter = Tau2Snapshotter(fresh)
        snapshotter.restore(store.blobs.get_json(step.state_before))
        assert snapshotter.state_hash() == step.state_hash_before
        snapshotter.restore(store.blobs.get_json(step.state_after))
        assert snapshotter.state_hash() == step.state_hash


# ---- the second domain ----


def test_records_a_retail_run_too(store):
    recorded, _ = record(RETAIL_WRITES, store, run_id="r1")

    names = [s.tool_name for s in store.reader.get_steps("r1") if s.actor == "tool"]

    assert names == ["get_user_details", "modify_user_address", "cancel_pending_order"]
    assert recorded.outcome is not None


# ---- record before use ----


def test_a_call_made_outside_a_recording_session_is_refused(store):
    """Record-before-use has no "no recorder, never mind" branch."""
    with pytest.raises(RecordingError, match="outside any recording session"):
        recording_hook({"model": "m", "messages": []}, object(), object())


def test_a_step_that_cannot_be_recorded_is_never_used(store, monkeypatch):
    """The tool wrapper records before returning, so a recording failure
    stops the run rather than letting an unrecorded result through."""
    from agent_bisect.adapters.tau2 import build_orchestrator

    orchestrator = build_orchestrator(spec_for(AIRLINE_READS), "r1")
    recorder = Tau2Recorder("r1", store.blobs, store.tape, orchestrator.environment)
    monkeypatch.setattr(
        store.tape, "append_step", _raising(sqlite3.OperationalError("disk I/O error"))
    )

    with recorder.bind(orchestrator.environment), pytest.raises(RecordingError):
        orchestrator.environment.get_response(_tool_call("list_all_airports", {}))


def _raising(error: Exception):
    def raise_it(*_args, **_kwargs):
        raise error

    return raise_it


def _tool_call(name: str, arguments: dict):
    from tau2.data_model.message import ToolCall

    return ToolCall(id="c1", name=name, arguments=arguments, requestor="assistant")


# ---- no network, ever ----


def test_recording_makes_no_network_call(store):
    """Sockets are blocked suite-wide; this asserts the run still completes,
    which is only possible because every call went to the scripted model."""
    recorded, llm = record(AIRLINE_READS, store, run_id="r1")

    assert llm.calls > 0
    assert recorded.outcome is not None


def test_ledger_counts_one_row_per_scripted_call(store):
    recorded, llm = record(AIRLINE_READS, store, run_id="r1")

    ledger = sqlite3.connect(store.root / "ledger.sqlite")
    total = ledger.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    ledger.close()

    assert total == llm.calls


# ---- the pinned commit ----


def test_tau2_commit_is_the_vendored_checkouts_own_head():
    commit = tau2_commit()

    assert len(commit) == 40
    assert all(character in "0123456789abcdef" for character in commit)


def test_tau2_commit_reports_unknown_rather_than_guessing(tmp_path):
    assert tau2_commit(tmp_path) == UNKNOWN_COMMIT


# ---- redaction ----


def test_a_key_in_a_tool_result_never_reaches_a_blob_or_the_index(store):
    """Rule 5: the key appears in no blob and no log. Built at runtime so
    the literal is not in this file either."""
    key = "nvapi" + "-" + "K" * 64
    record(AIRLINE_READS, store, run_id="r1")
    leaked = store.blobs.put_json({"content": f"Authorization: Bearer {key}"})

    assert key.encode() not in store.blobs.get_bytes(leaked)
    for path in sorted(store.root.glob("index.sqlite*")):
        assert key.encode() not in path.read_bytes()


def test_recorded_blobs_are_json_readable(store):
    """Nothing is stored in a shape only this module can read back."""
    record(AIRLINE_READS, store, run_id="r1")

    for step in store.reader.get_steps("r1"):
        json.loads(store.blobs.get_bytes(step.state_before))


# ---- infra failures ----


def test_an_infrastructure_termination_records_no_outcome(store, monkeypatch):
    """An infra failure is never scored as an agent failure, so it gets no
    outcome row at all rather than a zero reward."""
    import tau2.runner.simulation as simulation_module

    # `record_run` imports run_simulation at call time, so patching the
    # module attribute is enough -- no need to reach into the function.
    monkeypatch.setattr(
        simulation_module, "run_simulation", lambda _orchestrator, **_kwargs: _StubSimulation()
    )

    with scripted_session(AIRLINE_READS, store.root):
        recorded = record_run(
            spec_for(AIRLINE_READS), run_id="r2", store=store.blobs, tape=store.tape
        )

    assert recorded.aborted_infra
    assert recorded.termination_reason == "infrastructure_error"
    assert store.reader.get_outcome("r2") is None


class _StubSimulation:
    termination_reason = "infrastructure_error"
    reward_info = None
