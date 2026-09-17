"""End-to-end replay and fork tests: the same real tau2 orchestrator,
environment and evaluator, driven from a tape with sockets blocked.

These are the P2 criteria in test form -- step-identical replay with zero
LLM calls, a mutated request raising `DivergenceError`, and a fork at
every step reproducing the recorded outcome.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from agent_bisect.adapters.tau2_replay import (
    ForkSeedError,
    NoLiveCallError,
    Tau2ForkDriver,
    Tau2Replayer,
    rehydrate_response,
    replay_run,
)
from agent_bisect.adapters.tau2_scenarios import (
    AIRLINE_READS,
    AIRLINE_WRITES,
    JUDGE_MODEL,
    JUDGED_ASSERTION,
    RETAIL_JUDGED,
    RETAIL_WRITES,
    SCENARIOS,
)
from agent_bisect.core.replay import LIVE, DivergenceError, NoOpIntervention, TapeExhaustedError
from agent_bisect.core.runner import ForkSpec, PrefixMode, run_fork
from agent_bisect.core.tape import Step, TapeWriter
from tests.tau2_offline import Store, quiet_tau2, record, ref, reward_of, scripted_session, spec_for

pytestmark = pytest.mark.usefixtures("_no_real_key")


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "runs")


def _recorded(scenario, store: Store, run_id: str = "r1"):
    recorded, llm = record(scenario, store, run_id=run_id)
    assert recorded.outcome is not None, "the scenario must finish, or there is nothing to replay"
    return recorded, llm


# ---- (a) full-run replay is step-identical, with zero LLM calls ----


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_replay_is_step_identical_with_the_same_reward(scenario, tmp_path):
    store = Store(tmp_path / scenario.name)
    recorded, _ = _recorded(scenario, store)

    result = replay_run("r1", store=store.blobs, reader=store.reader)

    assert result.steps == recorded.steps
    assert result.outcome is not None
    assert result.outcome.reward == reward_of(recorded)
    assert result.termination_reason == recorded.termination_reason


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_replay_makes_no_llm_call_at_all(scenario, tmp_path):
    """Every response came off the tape; the scripted model was never asked.

    The suite blocks sockets, so a *live* call would fail anyway -- what
    this pins is that no call was made even to the fake.
    """
    store = Store(tmp_path / scenario.name)
    _recorded(scenario, store)
    from agent_bisect.adapters.tau2_fake_llm import ScriptedLLM

    idle = ScriptedLLM(scenario.scripts)
    import tau2.utils.llm_utils as llm_utils

    llm_utils.completion = idle.completion
    try:
        result = replay_run("r1", store=store.blobs, reader=store.reader)
    finally:
        llm_utils.completion = None

    assert idle.calls == 0
    assert result.live_llm_calls == 0
    assert result.tape_llm_calls > 0


def test_replay_consumes_the_whole_tape(store):
    recorded, _ = _recorded(AIRLINE_READS, store)

    result = replay_run("r1", store=store.blobs, reader=store.reader)

    assert result.tape_llm_calls == sum(recorded.llm_calls_by_actor.values())


def test_replay_raises_rather_than_reaching_for_a_live_call(store):
    """A replay whose tape runs short has no live source to fall back on."""
    _recorded(AIRLINE_READS, store)
    _truncate_tape(store, "r1", keep=3)

    with pytest.raises((TapeExhaustedError, NoLiveCallError)):
        replay_run("r1", store=store.blobs, reader=store.reader)


def _truncate_tape(store: Store, run_id: str, *, keep: int) -> None:
    import sqlite3

    connection = sqlite3.connect(store.root / "index.sqlite")
    with connection:
        connection.execute(
            "DELETE FROM steps WHERE run_id = ? AND step_idx >= ?", (run_id, keep)
        )
    connection.close()


# ---- (b) restoring every step reproduces its recorded hash ----


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_restoring_every_step_reproduces_its_recorded_db_hash(scenario, tmp_path):
    """The P1 gate criterion, on every step of every scenario."""
    from agent_bisect.adapters.tau2 import build_orchestrator
    from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter

    store = Store(tmp_path / scenario.name)
    _recorded(scenario, store)
    steps = store.reader.get_steps("r1")
    environment = build_orchestrator(spec_for(scenario), "probe").environment
    snapshotter = Tau2Snapshotter(environment)

    for step in steps:
        snapshotter.restore(store.blobs.get_json(step.state_before))
        assert snapshotter.state_hash() == step.state_hash_before, f"step {step.step_idx} before"
        snapshotter.restore(store.blobs.get_json(step.state_after))
        assert snapshotter.state_hash() == step.state_hash, f"step {step.step_idx} after"


# ---- (c) an altered request diverges; a volatile field does not ----


def _mutate_step(store: Store, run_id: str, mutate) -> None:
    """Rewrite one recorded step's request blob and hash through `mutate`."""
    import json
    import sqlite3

    from agent_bisect.core.tape import canonical_request_hash

    steps = store.reader.get_steps(run_id)
    target = next(step for step in steps if step.actor == "agent")
    request = store.blobs.get_json(ref(target.request_ref))
    mutated = mutate(request)
    new_ref = store.blobs.put_json(mutated)
    updated = target.model_copy(
        update={"request_ref": new_ref, "request_hash": canonical_request_hash(mutated)}
    )
    connection = sqlite3.connect(store.root / "index.sqlite")
    with connection:
        connection.execute(
            "UPDATE steps SET step_json = ? WHERE run_id = ? AND step_idx = ?",
            (updated.model_dump_json(), run_id, target.step_idx),
        )
    connection.close()
    assert json.loads(updated.model_dump_json())["request_hash"] != target.request_hash


def test_a_one_character_message_change_raises_divergence_naming_the_step(store):
    _recorded(AIRLINE_READS, store)

    def change_a_character(request):
        messages = [dict(message) for message in request["messages"]]
        messages[0]["content"] = (messages[0]["content"] or "") + "."
        return {**request, "messages": messages}

    _mutate_step(store, "r1", change_a_character)

    with pytest.raises(DivergenceError) as excinfo:
        replay_run("r1", store=store.blobs, reader=store.reader)

    assert excinfo.value.step_idx >= 0
    assert excinfo.value.actor == "agent"
    assert "messages" in excinfo.value.diff


def test_a_changed_tool_schema_raises_divergence(store):
    _recorded(AIRLINE_READS, store)

    def change_the_schema(request):
        tools = [dict(tool) for tool in request["tools"]]
        tools[0] = {**tools[0], "x-bisect-tampered": True}
        return {**request, "tools": tools}

    _mutate_step(store, "r1", change_the_schema)

    with pytest.raises(DivergenceError) as excinfo:
        replay_run("r1", store=store.blobs, reader=store.reader)

    assert "tools" in excinfo.value.diff


def test_a_changed_sampling_param_raises_divergence(store):
    _recorded(AIRLINE_READS, store)
    _mutate_step(store, "r1", lambda request: {**request, "temperature": 0.9})

    with pytest.raises(DivergenceError) as excinfo:
        replay_run("r1", store=store.blobs, reader=store.reader)

    assert "temperature" in excinfo.value.diff


@pytest.mark.parametrize(
    "volatile",
    [
        {"api_base": "https://elsewhere.example/v1"},
        {"timeout": 123},
        {"metadata": {"trace_id": "abc"}},
        {"num_retries": 7},
        {"api_key": "a-secret-that-is-not-part-of-the-sample"},
    ],
    ids=lambda field: next(iter(field)),
)
def test_a_volatile_field_on_the_replayed_request_does_not_diverge(store, volatile):
    """api_base, timeout, metadata, retry counts and credentials do not
    change what was sampled, so they must not be mistaken for divergence."""
    _recorded(AIRLINE_READS, store)
    steps = store.reader.get_steps("r1")
    first = steps[0]
    recorded_request = store.blobs.get_json(ref(first.request_ref))
    replayer = Tau2Replayer(
        environment=object(), steps=steps, store=store.blobs, sink=_Sink(fork_step_reached=False)
    )

    kwargs = {
        key: value
        for key, value in recorded_request.items()
        # `purpose` is the router's own tag, not a completion argument.
        if key not in {"model", "messages", "purpose"}
    }

    served = replayer.completion(
        model=recorded_request["model"],
        messages=recorded_request["messages"],
        **{**kwargs, **volatile},
    )

    assert served.to_dict() == store.blobs.get_json(ref(first.response_ref))


def test_a_tool_whose_result_drifted_raises_divergence(store):
    """Full-run replay re-executes the tools; a recording that no longer
    matches what the tool returns is a divergence, not a silent pass."""
    _recorded(AIRLINE_READS, store)
    steps = store.reader.get_steps("r1")
    target = next(step for step in steps if step.actor == "tool")
    drifted = {**store.blobs.get_json(ref(target.tool_result_ref)), "content": "something else"}
    drifted_ref = store.blobs.put_json(drifted)
    _replace_step(store, target.model_copy(update={"tool_result_ref": drifted_ref}))

    with pytest.raises(DivergenceError) as excinfo:
        replay_run("r1", store=store.blobs, reader=store.reader)

    assert "tool_result" in excinfo.value.diff


def _replace_step(store: Store, step: Step) -> None:
    import sqlite3

    connection = sqlite3.connect(store.root / "index.sqlite")
    with connection:
        connection.execute(
            "UPDATE steps SET step_json = ? WHERE run_id = ? AND step_idx = ?",
            (step.model_dump_json(), step.run_id, step.step_idx),
        )
    connection.close()


# ---- (d) forking at every step with the identity intervention ----


def _fork(
    store: Store,
    scenario,
    *,
    fork_step: int,
    prefix_tools: PrefixMode = "snapshot",
    run_id: str | None = None,
    environment_hook=None,
):
    """Fork run `r1` at `fork_step`, with the scripted model live after it."""
    run_id = run_id or f"fork-{prefix_tools}-{fork_step}"
    with scripted_session(scenario, store.root):
        import tau2.utils.llm_utils as llm_utils

        router_completion = llm_utils.completion
        driver = Tau2ForkDriver(
            ForkSpec(
                parent_run_id="r1",
                run_id=run_id,
                fork_step=fork_step,
                prefix_tools=prefix_tools,
            ),
            store=store.blobs,
            reader=store.reader,
            tape=store.tape,
            live_completion=router_completion,
            environment_hook=environment_hook,
        )
        outcome = run_fork(
            driver,
            ForkSpec(
                parent_run_id="r1",
                run_id=run_id,
                fork_step=fork_step,
                prefix_tools=prefix_tools,
            ),
            NoOpIntervention(),
        )
    return outcome, driver


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_forking_at_every_step_reproduces_the_recorded_outcome(scenario, tmp_path):
    """The determinism sanity check: with nothing changed at the fork step
    and a deterministic model after it, a fork is the recorded run."""
    store = Store(tmp_path / scenario.name)
    recorded, _ = _recorded(scenario, store)

    for fork_step in range(recorded.steps):
        outcome, driver = _fork(store, scenario, fork_step=fork_step)
        assert outcome.reward == reward_of(recorded), f"fork at {fork_step}"
        assert driver.result is not None
        assert driver.result.termination_reason == recorded.termination_reason


def test_a_fork_records_its_prefix_as_read_from_the_tape(store):
    recorded, _ = _recorded(AIRLINE_READS, store)

    _fork(store, AIRLINE_READS, fork_step=4, run_id="fork-4")

    steps = store.reader.get_steps("fork-4")
    assert [step.from_tape for step in steps[:5]] == [True] * 5
    assert steps[5].from_tape is False


def test_a_fork_pins_its_parent_and_fork_step(store):
    _recorded(AIRLINE_READS, store)

    _fork(store, AIRLINE_READS, fork_step=3, run_id="fork-3")

    manifest = store.reader.get_manifest("fork-3")
    assert manifest.parent_run_id == "r1"
    assert manifest.fork_step == 3
    assert manifest.agent_model == store.reader.get_manifest("r1").agent_model


def test_a_forks_prefix_rows_repeat_the_parents_hashes_exactly(store):
    """The prefix is shared, not re-derived: same request hashes, same
    state hashes, same blob refs."""
    _recorded(AIRLINE_READS, store)

    _fork(store, AIRLINE_READS, fork_step=5, run_id="fork-5")

    parent = store.reader.get_steps("r1")
    forked = store.reader.get_steps("fork-5")
    for original, copy in zip(parent[:5], forked[:5], strict=True):
        assert copy.actor == original.actor
        assert copy.request_hash == original.request_hash
        assert copy.request_ref == original.request_ref
        assert copy.response_ref == original.response_ref
        assert copy.state_hash == original.state_hash
        assert copy.state_hash_before == original.state_hash_before


def test_a_fork_makes_live_calls_only_after_the_fork_step(store):
    recorded, _ = _recorded(AIRLINE_WRITES, store)

    _outcome, driver = _fork(store, AIRLINE_WRITES, fork_step=2, run_id="fork-2")

    assert driver.result is not None
    assert driver.result.tape_llm_calls > 0
    assert driver.result.live_llm_calls > 0
    assert driver.result.tape_llm_calls + driver.result.live_llm_calls == sum(
        recorded.llm_calls_by_actor.values()
    )


def test_forking_past_the_end_of_the_tape_is_refused(store):
    recorded, _ = _recorded(AIRLINE_READS, store)

    with pytest.raises(DivergenceError, match="steps"):
        _fork(store, AIRLINE_READS, fork_step=recorded.steps + 5, run_id="fork-far")


# ---- both prefix modes ----


@pytest.mark.parametrize("prefix_tools", ["snapshot", "rerun_live"])
def test_both_prefix_modes_agree_on_deterministic_tau2(store, prefix_tools):
    """Plain tau2 tools are deterministic, so serving the recorded result
    and re-executing it must give the same answer. The flaky world is
    where the two are meant to part company."""
    recorded, _ = _recorded(AIRLINE_WRITES, store)

    outcome, _driver = _fork(
        store, AIRLINE_WRITES, fork_step=3, prefix_tools=prefix_tools, run_id=f"f-{prefix_tools}"
    )

    assert outcome.reward == reward_of(recorded)


def test_the_snapshot_prefix_never_executes_the_tool(store):
    """Serving a recorded tool result means the tool is not run at all --
    that is what makes the prefix immune to a flaky world -- and the world
    is put where the recording left it instead."""
    from agent_bisect.adapters.tau2 import build_orchestrator
    from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter

    _recorded(AIRLINE_WRITES, store)
    booked = next(s for s in store.reader.get_steps("r1") if s.tool_name == "book_reservation")
    environment = build_orchestrator(spec_for(AIRLINE_WRITES), "probe").environment
    replayer = Tau2Replayer(
        environment=environment,
        steps=[booked],
        store=store.blobs,
        sink=_Sink(fork_step_reached=False),
        tool_mode="snapshot",
    )

    message = replayer.get_response(_must_not_run, _tool_call_of(booked))

    assert message.content == store.blobs.get_json(ref(booked.tool_result_ref))["content"]
    assert Tau2Snapshotter(environment).state_hash() == booked.state_hash


def _must_not_run(_tool_call):
    raise AssertionError("the snapshot prefix executed a tool")


def _tool_call_of(step: Step):
    from tau2.data_model.message import ToolCall

    return ToolCall(
        id="replayed",
        name=ref(step.tool_name),
        arguments=step.tool_args or {},
        requestor="assistant",
    )


def test_the_evaluator_runs_its_tool_checks_on_its_own_environment(store):
    """tau2's reward replays the trajectory's write actions against a fresh
    DB (`evaluator/evaluator_env.py`), so those executions are not steps of
    the run and are not recorded -- the recorder wraps the orchestrator's
    environment instance, not the class."""
    recorded, _ = _recorded(AIRLINE_WRITES, store)

    tool_steps = [s for s in store.reader.get_steps("r1") if s.actor == "tool"]

    assert [s.tool_name for s in tool_steps] == [
        "get_user_details",
        "book_reservation",
        "update_reservation_baggages",
        "cancel_reservation",
    ]
    assert recorded.steps == len(store.reader.get_steps("r1"))


# ---- the intervention seam ----


def test_an_intervention_can_replace_the_response_at_the_fork_step(store):
    _recorded(AIRLINE_READS, store)
    replaced = _ReplaceContent("this is not what the model said")

    outcome, driver = _fork_with(store, AIRLINE_READS, fork_step=0, intervention=replaced)

    assert replaced.applied == 1
    assert driver.result is not None
    first = store.reader.get_steps(driver.result.run_id)[0]
    served = store.blobs.get_json(ref(first.response_ref))
    assert served["choices"][0]["message"]["content"] == "this is not what the model said"


def test_an_intervention_returning_live_forces_a_fresh_sample(store):
    _recorded(AIRLINE_READS, store)
    resample = _Resample()

    _outcome, driver = _fork_with(store, AIRLINE_READS, fork_step=0, intervention=resample)

    assert driver.result is not None
    assert driver.result.live_llm_calls > 0


class _ReplaceContent:
    name = "replace-content"

    def __init__(self, content: str) -> None:
        self._content = content
        self.applied = 0

    def apply(self, step, payload):
        self.applied += 1
        message = {**payload["choices"][0]["message"], "content": self._content}
        choices = [{**payload["choices"][0], "message": message}]
        return {**payload, "choices": choices}


class _Resample:
    name = "resample"

    def apply(self, step, payload):
        return LIVE


def _fork_with(store: Store, scenario, *, fork_step: int, intervention):

    run_id = f"fork-{intervention.name}-{fork_step}"
    with scripted_session(scenario, store.root):
        import tau2.utils.llm_utils as llm_utils

        spec = ForkSpec(parent_run_id="r1", run_id=run_id, fork_step=fork_step)
        driver = Tau2ForkDriver(
            spec,
            store=store.blobs,
            reader=store.reader,
            tape=store.tape,
            live_completion=llm_utils.completion,
        )
        outcome = run_fork(driver, spec, intervention)
    return outcome, driver


# ---- rehydration ----


def test_a_rehydrated_response_round_trips_to_the_recorded_payload(store):
    _recorded(AIRLINE_READS, store)
    step = next(s for s in store.reader.get_steps("r1") if s.actor == "agent")
    payload = store.blobs.get_json(ref(step.response_ref))

    assert rehydrate_response(payload).to_dict() == payload


# ---- the replayer used directly ----


def test_a_replayer_without_a_live_source_refuses_to_invent_one(store):
    _recorded(AIRLINE_READS, store)
    replayer = Tau2Replayer(
        environment=object(),
        steps=[],
        store=store.blobs,
        sink=_Sink(fork_step_reached=True),
        fork_step=0,
    )

    with pytest.raises(NoLiveCallError):
        replayer.completion(model="m", messages=[])


class _Sink:
    def __init__(self, fork_step_reached: bool) -> None:
        self.next_step_idx = 1 if fork_step_reached else 0

    def begin_step(self) -> None:
        return None

    def on_llm_call(self, *_args, **_kwargs) -> None:
        self.next_step_idx += 1

    def on_tool_call(self, *_args, **_kwargs) -> None:
        self.next_step_idx += 1


# ---- retail, for a second data model ----


def test_a_retail_run_replays_step_identically(store):
    recorded, _ = _recorded(RETAIL_WRITES, store)

    result = replay_run("r1", store=store.blobs, reader=store.reader)

    assert result.steps == recorded.steps
    assert result.outcome is not None
    assert result.outcome.reward == reward_of(recorded)


def test_tape_writer_is_unused_by_a_plain_replay(store, monkeypatch):
    """A replay verifies; it does not write a second copy of the run."""
    _recorded(AIRLINE_READS, store)
    monkeypatch.setattr(TapeWriter, "append_step", _fail)

    replay_run("r1", store=store.blobs, reader=store.reader)


def _fail(*_args, **_kwargs):
    raise AssertionError("a plain replay must not write steps")


# ---- the evaluator is a recorded actor too ----


def test_an_evaluator_llm_call_is_recorded_as_its_own_step(store):
    """Retail task 2 carries NL_ASSERTION in its reward_basis, so tau2's
    judge is called to compute the reward. It goes through the same seam,
    so it is a step like any other."""
    recorded, llm = _recorded(RETAIL_JUDGED, store)

    evaluator_steps = [s for s in store.reader.get_steps("r1") if s.actor == "evaluator"]

    assert len(evaluator_steps) == 1
    assert recorded.llm_calls_by_actor["evaluator"] == 1
    assert llm.calls_by_model[JUDGE_MODEL] == 1
    assert evaluator_steps[0].model == JUDGE_MODEL


def test_an_evaluator_step_is_the_last_step_of_the_run(store):
    """The reward is computed after the orchestrator loop, so the judge's
    call comes after every agent, user and tool step."""
    _recorded(RETAIL_JUDGED, store)

    actors = [step.actor for step in store.reader.get_steps("r1")]

    assert actors[-1] == "evaluator"
    assert "evaluator" not in actors[:-1]


def test_a_run_with_an_evaluator_call_replays_step_identically(store):
    """The judge's response comes off the tape like any other, so the
    reward is reproduced without asking it again."""
    recorded, _ = _recorded(RETAIL_JUDGED, store)

    result = replay_run("r1", store=store.blobs, reader=store.reader)

    assert result.steps == recorded.steps
    assert result.outcome is not None
    assert result.outcome.reward == reward_of(recorded)
    assert result.live_llm_calls == 0


def test_the_recorded_judges_verdict_is_what_the_reward_reflects(store):
    """The reward would be computed whether or not the judge was really
    asked, so pin that the scripted verdict is the one in the breakdown --
    justification and all."""
    _recorded(RETAIL_JUDGED, store)
    outcome = store.reader.get_outcome("r1")
    assert outcome is not None
    breakdown = store.blobs.get_json(ref(outcome.breakdown_ref))

    assert "NL_ASSERTION" in breakdown["reward_basis"]
    [check] = breakdown["nl_assertions"]
    assert check["met"] is True
    assert check["justification"] == "The agent said so."
    assert check["nl_assertion"] == JUDGED_ASSERTION


# ---- the re-run-live baseline's escape hatch (P5) ----


def test_a_guarded_replay_reports_no_unguarded_calls(store):
    """The default: every prefix response matched its recorded request."""
    _recorded(AIRLINE_READS, store)

    result = replay_run("r1", store=store.blobs, reader=store.reader)

    assert result.unguarded_llm_calls == 0


def test_a_fork_reports_how_many_responses_were_served_unguarded(store):
    """P5's CAR-style baseline drops the hash guard by construction, so how
    far it drifted has to be countable rather than invisible."""
    _recorded(AIRLINE_READS, store)

    _outcome, driver = _fork(store, AIRLINE_READS, fork_step=4, run_id="fork-guarded")

    assert driver.result is not None
    assert driver.result.unguarded_llm_calls == 0


# ---- seams the later phases need ----


def test_replay_can_serve_the_prefix_tools_from_the_snapshot(store):
    """A P3 dataset item's recorded tool result IS the planted mutation, so
    re-executing the tool and asserting the recording comes back is false
    by construction. Snapshot mode still checks every request hash, still
    restores and hash-checks the world, and still consumes the whole tape."""
    recorded, _ = _recorded(AIRLINE_READS, store)

    result = replay_run(
        "r1", store=store.blobs, reader=store.reader, tool_mode="snapshot"
    )

    assert result.steps == recorded.steps
    assert result.outcome is not None
    assert result.outcome.reward == reward_of(recorded)
    assert result.live_llm_calls == 0


def test_replay_verifies_the_tools_by_default(store):
    """The P2 gate's mode: re-execute and assert. A drifted recording must
    still be caught when nobody asked for snapshot mode."""
    _recorded(AIRLINE_READS, store)
    step = next(s for s in store.reader.get_steps("r1") if s.actor == "tool")
    drifted = {**store.blobs.get_json(ref(step.tool_result_ref)), "content": "drifted"}
    _replace_step(store, step.model_copy(update={"tool_result_ref": store.blobs.put_json(drifted)}))

    with pytest.raises(DivergenceError):
        replay_run("r1", store=store.blobs, reader=store.reader)


def test_a_fork_can_install_a_component_before_the_recorder_wraps_the_tools(store):
    """A planted fault is a standing component on the environment, and it
    has to be installed before the recorder and the replayer wrap
    get_response -- otherwise the tape records the true answer while the
    agent saw the corrupted one."""
    seen: list[str] = []

    @contextmanager
    def hook(environment):
        seen.append(type(environment).__name__)
        yield

    _recorded(AIRLINE_READS, store)

    _outcome, driver = _fork(
        store, AIRLINE_READS, fork_step=3, run_id="fork-hooked", environment_hook=hook
    )

    assert seen, "the hook was never entered"
    assert driver.result is not None


def test_a_fork_without_a_hook_still_runs(store):
    _recorded(AIRLINE_READS, store)

    outcome, _driver = _fork(store, AIRLINE_READS, fork_step=3, run_id="fork-unhooked")

    assert outcome.reward == 1.0 or outcome.reward == 0.0


def test_a_fork_refuses_a_seed_that_would_diverge_its_own_prefix(store):
    """tau2 puts the run seed into every model request, so it is part of
    the canonical request hash: re-pinning it makes the fork diverge on
    its own first prefix step. Refuse loudly rather than produce a
    recording that cannot be replayed."""
    _recorded(AIRLINE_READS, store)
    parent_seed = store.reader.get_manifest("r1").seed
    spec = ForkSpec(
        parent_run_id="r1", run_id="fork-reseeded", fork_step=2, seed=(parent_seed or 0) + 1
    )
    driver = Tau2ForkDriver(
        spec, store=store.blobs, reader=store.reader, tape=store.tape, live_completion=_must_not_run
    )

    with pytest.raises(ForkSeedError, match="request hash"):
        run_fork(driver, spec, NoOpIntervention())


def test_a_fork_accepts_the_parents_own_seed(store):
    _recorded(AIRLINE_READS, store)
    parent_seed = store.reader.get_manifest("r1").seed
    spec = ForkSpec(parent_run_id="r1", run_id="fork-same-seed", fork_step=2, seed=parent_seed)

    with scripted_session(AIRLINE_READS, store.root):
        import tau2.utils.llm_utils as llm_utils

        driver = Tau2ForkDriver(
            spec,
            store=store.blobs,
            reader=store.reader,
            tape=store.tape,
            live_completion=llm_utils.completion,
        )
        outcome = run_fork(driver, spec, NoOpIntervention())

    assert outcome is not None
