"""The whole P3 pipeline, offline, against tau2's real environments.

The main stage-A test: record base runs, check them for stability, plant
faults at stratified tool steps, re-run each four times, keep the ones
that flip, and freeze a manifest — all with sockets blocked and only the
model scripted. Everything else is the real thing: tau2's orchestrator,
its airline domain, its evaluator, our recorder, our replay engine, our
snapshots.

It is slow (a hundred-odd simulations) and it is the test that would
catch a pipeline that looks right on fakes and does nothing real.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from agent_bisect.adapters.tau2_fault_injector import injector_spec_from
from agent_bisect.adapters.tau2_inject import Tau2InjectRunner
from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
from agent_bisect.attribution.interventions import TruthfulToolResult, from_ref
from agent_bisect.bench.inject import InjectConfig, Journal, collect
from agent_bisect.bench.manifest import freeze, load_frozen
from agent_bisect.bench.strata import POSITION_BUCKETS
from tests.inject_offline import (
    AGENT_MODEL,
    AIRLINE_INJECT,
    DRY_RUN_TASKS,
    REACTIVE_TOOLS,
    USER_MODEL,
    ReactiveLLM,
)
from tests.tau2_offline import (
    UNUSED_API_BASE,
    UNUSED_API_KEY,
    Store,
    ledger_for,
    no_limiter,
    quiet_tau2,
)

quiet_tau2()

CONFIG = InjectConfig(attempts_per_bucket=1, target_items=100, seed=4242)


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory) -> dict:
    """One pass of the whole pipeline, shared by every assertion below."""
    from agent_bisect.adapters.tau2 import recording_session

    root = tmp_path_factory.mktemp("p3-dry-run")
    store = Store(root / "runs")
    journal = Journal(root / "p3")
    llm = ReactiveLLM(AIRLINE_INJECT)
    with recording_session(
        ledger=ledger_for(root),
        phase="P3",
        completion_fn=llm.completion,
        api_key=UNUSED_API_KEY,
        api_base=UNUSED_API_BASE,
        limiter_for=no_limiter,
    ):
        runner = Tau2InjectRunner(
            store=store.blobs, tape=store.tape, reader=store.reader,
            agent_model=AGENT_MODEL, user_model=USER_MODEL, seed=42,
        )
        result = collect(runner, tasks=DRY_RUN_TASKS, journal=journal, config=CONFIG)
    return {"root": root, "store": store, "journal": journal, "result": result, "llm": llm}


# ---- the funnel ----


def test_the_dry_run_keeps_the_faults_that_flip_and_rejects_the_rest(dry_run):
    counts = dry_run["result"].counts

    assert counts["base_recorded"] == len(DRY_RUN_TASKS)
    assert counts["rejected_base_failed"] == 0
    assert counts["stable"] == len(DRY_RUN_TASKS)
    assert counts["kept"] > 0
    assert counts["rejected_not_flipped"] > 0
    assert counts["candidates"] == counts["kept"] + counts["rejected_not_flipped"]


def test_a_fault_is_only_kept_where_the_agent_actually_reads_the_answer(dry_run):
    """The scripted agent acts on two of the three tools it calls. A fault
    in the third is a real mutation of a real result that changes nothing,
    which is exactly what a rejected candidate is."""
    store = dry_run["store"]
    kept_tools = {
        _tool_name_at(store, item["base_run_id"], item["planted_step"])
        for item in dry_run["result"].items
    }

    assert kept_tools <= REACTIVE_TOOLS


def test_every_candidate_verdict_is_on_the_record(dry_run):
    verdicts = [event for event in dry_run["journal"].events() if event["kind"] == "candidate"]

    assert len(verdicts) == dry_run["result"].counts["candidates"]
    assert all(event.get("reason") for event in verdicts if event["status"] == "rejected")


def test_the_faults_cover_more_than_one_type_and_more_than_one_position(dry_run):
    items = dry_run["result"].items

    assert len({item["fault_type"] for item in items}) >= 2
    assert {item["position_bucket"] for item in items} <= set(POSITION_BUCKETS)


# ---- each item is a real, failed recording ----


def test_each_item_is_a_complete_failed_recording_on_the_tape(dry_run):
    store = dry_run["store"]

    for item in dry_run["result"].items:
        outcome = store.reader.get_outcome(item["run_id"])
        assert outcome is not None, item["run_id"]
        assert outcome.passed is False
        manifest = store.reader.get_manifest(item["run_id"])
        assert manifest.parent_run_id == item["base_run_id"]
        assert manifest.fork_step == item["planted_step"]


def test_the_planted_step_is_a_tool_step_of_the_base_run(dry_run):
    store = dry_run["store"]

    for item in dry_run["result"].items:
        step = store.reader.get_step(item["base_run_id"], item["planted_step"])
        assert step.actor == "tool"
        assert step.tool_result_ref == item["oracle"]["tool_result_ref"]


def test_the_faulted_recording_shows_the_agent_the_mutation(dry_run):
    store = dry_run["store"]

    for item in dry_run["result"].items:
        shown = store.blobs.get_json(
            _ref(store.reader.get_step(item["run_id"], item["planted_step"]).tool_result_ref)
        )
        planted = from_ref(item["intervention"])
        assert shown["content"] == planted.new_result["content"]
        assert shown["content"] != store.blobs.get_json(item["oracle"]["tool_result_ref"])[
            "content"
        ]


def test_the_world_is_not_mutated_by_the_fault(dry_run):
    """`ReplaceToolResult` changes what the agent sees, never the database:
    the faulted run's state at the planted step is the base run's."""
    store = dry_run["store"]

    for item in dry_run["result"].items:
        base = store.reader.get_step(item["base_run_id"], item["planted_step"])
        faulted = store.reader.get_step(item["run_id"], item["planted_step"])
        assert faulted.state_hash == base.state_hash


def test_what_was_done_to_each_fork_is_stored(dry_run):
    store = dry_run["store"]

    for item in dry_run["result"].items:
        stored = store.blobs.get_json(item["intervention_ref"])
        assert stored["hash"] == item["intervention"]["hash"]


# ---- the label-free fix agrees with the oracle ----


def test_the_truthful_result_equals_the_oracle_at_the_planted_step(dry_run):
    """`TruthfulToolResult` re-executes the call against the state it ran
    on. At a planted fault that is the original answer — the oracle — so
    P5 can propose the fix without ever reading the label."""
    store = dry_run["store"]
    item = dry_run["result"].items[0]
    resolver = Tau2TruthResolver(item["domain"], item["task_id"], store.blobs)
    step = store.reader.get_step(item["run_id"], item["planted_step"])

    shown = store.blobs.get_json(_ref(step.tool_result_ref))
    truthful = TruthfulToolResult(step=item["planted_step"]).with_truth(resolver)
    fixed = truthful.apply(step, shown)

    oracle = store.blobs.get_json(item["oracle"]["tool_result_ref"])
    # Compared parsed, not as text: a restored snapshot comes back through
    # the blob store's canonical JSON, so its dicts are key-sorted while
    # the live database kept insertion order. The data is the same and
    # tau2's own db hash (`get_dict_hash`, sort_keys=True) agrees; only
    # the spelling differs.
    assert json.loads(fixed["content"]) == json.loads(oracle["content"])
    assert json.loads(fixed["content"]) != json.loads(shown["content"])


# ---- freezing ----


def test_the_dry_run_freezes_to_a_verifiable_manifest(dry_run):
    path = Path(dry_run["root"]) / "data" / "manifest.json"

    freeze(
        dry_run["result"].items,
        path=path,
        models={"agent": AGENT_MODEL, "user_sim": USER_MODEL, "judge": "none"},
        tau2_commit="offline-dry-run",
        config=CONFIG.as_dict(),
        counts=dry_run["result"].counts,
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )

    loaded = load_frozen(path)
    assert len(loaded.items) == len(dry_run["result"].items)
    assert loaded.counts["kept"] == dry_run["result"].counts["kept"]
    assert all(entry.split in {"dev", "test"} for entry in loaded.items)
    assert _no_task_spans_both_splits(loaded)


def test_the_p3_gate_passes_on_the_dry_run(dry_run):
    """The gate's own end-to-end test: every criterion, including the
    replay of the faulted recordings, against data this pipeline made.

    One criterion cannot hold on a toy and is asserted to fail, which is
    the gate doing its job: `strata` fails because the scripted agent
    ignores the tool in its late bucket by construction, so no late fault
    ever flips a run. The count is relaxed to the dry run's own size (the
    real bar is 120).
    """
    from scripts.gates.p3 import run_gate

    items = dry_run["result"].items
    path = Path(dry_run["root"]) / "gate" / "manifest.json"
    freeze(
        items,
        path=path,
        models={"agent": AGENT_MODEL, "user_sim": USER_MODEL, "judge": "none"},
        tau2_commit="offline-dry-run",
        config=CONFIG.as_dict(),
        counts=dry_run["result"].counts,
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )

    criteria = run_gate(
        path, dry_run["store"].root, len(items), 3, Path("docs/decisions/absent.md")
    )

    assert {criterion.name: criterion.passed for criterion in criteria} == {
        "hash": True, "count": True, "thresholds": True,
        "split": True, "replay": True, "strata": False,
    }
    assert "missing: ['late']" in next(c for c in criteria if c.name == "strata").detail


# ---- the standing fault (decision 0016) ----


@pytest.mark.parametrize("prefix_tools", ["snapshot", "rerun_live"])
def test_a_fork_taken_before_the_planted_step_still_fails(dry_run, prefix_tools):
    """The regression test for decision 0016.

    A one-shot planted fault lives only in the recording, so a fork taken
    before k re-executes the tool live, gets the truth and passes — which
    would make the pre-registered shared control measure the base run and
    collapse every effect to zero. With the fault standing in the world
    the same fork still fails, and removing the fault is what makes it
    pass again.
    """
    item = next(
        entry for entry in dry_run["result"].items if entry["position_bucket"] == "middle"
    )
    before = item["planted_step"] - 1

    with_fault = _fork_faulted(dry_run, item, before, prefix_tools, keep_fault=True)
    without = _fork_faulted(dry_run, item, before, prefix_tools, keep_fault=False)

    assert with_fault.passed is False
    assert without.passed is True


def test_the_faulted_run_carries_its_fault_in_its_manifest(dry_run):
    store = dry_run["store"]

    for item in dry_run["result"].items:
        fault = injector_spec_from(store.reader.get_manifest(item["run_id"]).params)
        assert fault is not None, item["run_id"]
        assert fault.step_idx == item["planted_step"]
        assert fault.fault_type == item["fault_type"]
        assert fault.content == from_ref(item["intervention"]).new_result["content"]


def _fork_faulted(dry_run, item, fork_step: int, prefix_tools, *, keep_fault: bool):
    """Fork the faulted recording, with or without its standing fault."""
    from agent_bisect.adapters.tau2 import recording_session
    from agent_bisect.adapters.tau2_fault_fork import FaultedForkDriver
    from agent_bisect.core.replay import NoOpIntervention
    from agent_bisect.core.runner import ForkSpec, run_fork

    store = dry_run["store"]
    fault = injector_spec_from(store.reader.get_manifest(item["run_id"]).params)
    spec = ForkSpec(
        parent_run_id=item["run_id"],
        run_id=f"{item['item_id']}-before-{fork_step}-{prefix_tools}-{int(keep_fault)}",
        fork_step=fork_step,
        prefix_tools=prefix_tools,
    )
    with recording_session(
        ledger=ledger_for(dry_run["root"]), phase="P3",
        completion_fn=dry_run["llm"].completion,
        api_key=UNUSED_API_KEY, api_base=UNUSED_API_BASE, limiter_for=no_limiter,
    ):
        import tau2.utils.llm_utils as llm_utils

        driver = FaultedForkDriver(
            spec, store=store.blobs, reader=store.reader, tape=store.tape,
            live_completion=llm_utils.completion,
            fault=fault if keep_fault else None,
        )
        return run_fork(driver, spec, NoOpIntervention())


# ---- resume ----


def test_resuming_the_dry_run_costs_nothing(dry_run):
    before = dry_run["llm"].calls

    again = collect(
        _RefusingRunner(dry_run["store"]),
        tasks=DRY_RUN_TASKS,
        journal=dry_run["journal"],
        config=CONFIG,
    )

    assert [item["item_id"] for item in again.items] == [
        item["item_id"] for item in dry_run["result"].items
    ]
    assert dry_run["llm"].calls == before


class _RefusingRunner:
    """Anything that would spend a call is a bug; reading the tape is not."""

    def __init__(self, store: Store) -> None:
        self._runner = Tau2InjectRunner(
            store=store.blobs, tape=store.tape, reader=store.reader,
            agent_model=AGENT_MODEL, user_model=USER_MODEL, seed=42,
        )

    def record_base(self, *args, **kwargs):
        raise AssertionError("a resumed collection re-recorded a base run")

    def resample(self, *args, **kwargs):
        raise AssertionError("a resumed collection re-ran a stability check")

    def tool_steps(self, base_run_id):
        return self._runner.tool_steps(base_run_id)

    def fault_fork(self, *args, **kwargs):
        raise AssertionError("a resumed collection re-ran a faulted fork")


def _no_task_spans_both_splits(loaded) -> bool:
    sides: dict[str, set[str | None]] = {}
    for entry in loaded.items:
        sides.setdefault(entry.group, set()).add(entry.split)
    return all(len(found) == 1 for found in sides.values())


def _tool_name_at(store: Store, run_id: str, step_idx: int) -> str:
    return store.reader.get_step(run_id, step_idx).tool_name or ""


def _ref(digest: str | None) -> str:
    assert digest is not None, "the step has no tool result"
    return digest
