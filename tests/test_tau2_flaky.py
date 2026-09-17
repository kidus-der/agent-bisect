"""The flaky world, and the drift that justifies snapshots.

The claim the whole engine rests on is that a snapshot prefix is *exact*
where a re-run-live prefix drifts. On deterministic τ² that claim is
untestable, because both are exact. Here it is testable, and measured:

- **snapshot** — restoring a recorded snapshot reproduces the recorded
  database hash at every tool step, always;
- **rerun_live** — re-executing the same recorded calls later reproduces
  neither the answers nor the state, in X% of runs.

X is measured by `test_rerun_live_drifts_where_snapshot_does_not` and
reported with the P3 evidence.
"""

from __future__ import annotations

import json

import pytest
from agent_bisect.adapters.tau2 import build_orchestrator
from agent_bisect.adapters.tau2_fake_llm import ScriptedToolCall, ScriptedTurn
from agent_bisect.adapters.tau2_flaky import (
    DETERMINISTIC_RESERVATION_IDS,
    TRANSIENT_ERROR,
    FlakyConfig,
    FlakyWorld,
    canonicalise,
    flaky_db_hash,
    flaky_world,
)
from agent_bisect.adapters.tau2_scenarios import STOP, Scenario
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
from tests.inject_offline import AGENT_MODEL, PANIC_BOOKING, USER_MODEL
from tests.tau2_offline import (
    UNUSED_API_BASE,
    UNUSED_API_KEY,
    Store,
    ledger_for,
    no_limiter,
    quiet_tau2,
)

quiet_tau2()

#: Books (so an identifier is generated), searches (so a drifting read is
#: returned) and reads a user (so something stable is in the mix too).
FLAKY_SCENARIO = Scenario(
    name="airline-flaky",
    domain="airline",
    task_id="0",
    agent=(
        ScriptedTurn(tool_calls=(PANIC_BOOKING,)),
        ScriptedTurn(
            tool_calls=(ScriptedToolCall("f2", "search_direct_flight",
                                         {"origin": "PHL", "destination": "LGA",
                                          "date": "2024-05-16"}),)
        ),
        ScriptedTurn(
            tool_calls=(ScriptedToolCall("f3", "get_user_details",
                                         {"user_id": "mia_li_3668"}),)
        ),
        ScriptedTurn(content="All done. Anything else?"),
        ScriptedTurn(content="Thanks for contacting us."),
    ),
    user=(
        ScriptedTurn(content="Please book me PHL to LGA."),
        ScriptedTurn(content="No, that is all."),
        ScriptedTurn(content=STOP),
    ),
)

#: How many runs the drift measurement is taken over.
MEASURED_RUNS = 10


def environment_for(domain: str = "airline", task_id: str = "0"):
    from agent_bisect.adapters.tau2 import RunSpec

    return build_orchestrator(
        RunSpec(domain=domain, task_id=task_id,
                agent_model=AGENT_MODEL, user_model=USER_MODEL),
        f"flaky-probe-{domain}-{task_id}",
    ).environment


def tool_call(name: str, **arguments):
    from tau2.data_model.message import ToolCall

    return ToolCall(id=f"probe-{name}", name=name, arguments=arguments, requestor="assistant")


# ---- the three sources of non-determinism ----


def test_the_same_seed_gives_the_same_world():
    first = FlakyWorld(FlakyConfig(seed=7))
    second = FlakyWorld(FlakyConfig(seed=7))

    assert [first.new_id() for _ in range(3)] == [second.new_id() for _ in range(3)]
    assert [first.should_fail() for _ in range(20)] == [second.should_fail() for _ in range(20)]


def test_a_different_seed_gives_a_different_world():
    assert FlakyWorld(FlakyConfig(seed=1)).new_id() != FlakyWorld(FlakyConfig(seed=2)).new_id()


def test_a_generated_id_is_paired_with_the_one_the_domain_would_have_used():
    world = FlakyWorld(FlakyConfig(seed=3))

    first, second = world.new_id(), world.new_id()

    assert first != second
    assert len(first) == len(DETERMINISTIC_RESERVATION_IDS[0])
    assert world.canonical_ids()[first] == DETERMINISTIC_RESERVATION_IDS[0]
    assert world.canonical_ids()[second] == DETERMINISTIC_RESERVATION_IDS[1]


def test_booking_twice_in_a_flaky_world_gives_two_random_ids():
    environment = environment_for()

    with flaky_world(environment, FlakyConfig(seed=11, p_error=0.0)) as world:
        environment.get_response(tool_call("book_reservation", **dict(PANIC_BOOKING.arguments)))
        booked = json.loads(environment.get_response(
            tool_call("get_user_details", user_id="mia_li_3668")
        ).content)

    assert world.id_trail
    assert world.id_trail[0][0] in booked["reservations"]
    assert "HATHAT" not in booked["reservations"]


def test_an_injected_error_never_executes_the_tool():
    environment = environment_for()
    before = Tau2Snapshotter(environment).state_hash()

    with flaky_world(environment, FlakyConfig(seed=5, p_error=1.0)) as world:
        message = environment.get_response(
            tool_call("book_reservation", **dict(PANIC_BOOKING.arguments))
        )

    assert message.error is True
    assert message.content == TRANSIENT_ERROR
    assert Tau2Snapshotter(environment).state_hash() == before
    assert world.injected_errors == 1
    assert world.executions == 0


def test_a_read_answer_drifts_with_the_clock():
    environment = environment_for()

    with flaky_world(environment, FlakyConfig(seed=2, p_error=0.0)) as world:
        first = environment.get_response(
            tool_call("search_direct_flight", origin="PHL", destination="LGA",
                      date="2024-05-16")
        ).content
        for _ in range(3):
            environment.get_response(tool_call("list_all_airports"))
        later = environment.get_response(
            tool_call("search_direct_flight", origin="PHL", destination="LGA",
                      date="2024-05-16")
        ).content

    assert first != later
    assert world.ticks == 5


def test_drifting_fields_never_reach_the_database():
    """Availability drifts in what the agent is *told*, not in what is
    stored: the DB check must stay a check on the agent's behaviour."""
    environment = environment_for()
    before = Tau2Snapshotter(environment).state_hash()

    with flaky_world(environment, FlakyConfig(seed=2, p_error=0.0)):
        for _ in range(4):
            environment.get_response(
                tool_call("search_direct_flight", origin="PHL", destination="LGA",
                          date="2024-05-16")
            )

    assert Tau2Snapshotter(environment).state_hash() == before


# ---- the canonicalised reward (decision 0011) ----


def test_canonicalising_renames_keys_and_values():
    mapping = {"ZZ11QQ": "HATHAT"}

    renamed = canonicalise(
        {"reservations": {"ZZ11QQ": {"reservation_id": "ZZ11QQ", "seats": 2}}}, mapping
    )

    assert renamed == {"reservations": {"HATHAT": {"reservation_id": "HATHAT", "seats": 2}}}


def test_two_flaky_runs_that_did_the_same_thing_hash_the_same():
    hashes = []
    for seed in (21, 22):
        environment = environment_for()
        with flaky_world(environment, FlakyConfig(seed=seed, p_error=0.0)) as world:
            environment.get_response(
                tool_call("book_reservation", **dict(PANIC_BOOKING.arguments))
            )
            hashes.append(flaky_db_hash(environment, world))

    assert hashes[0] == hashes[1]


def test_a_run_that_did_something_else_still_hashes_differently():
    """Canonicalisation is a renaming, not a relaxation."""
    same, different = [], []
    for seed, baggages in ((31, 1), (32, 2)):
        environment = environment_for()
        arguments = {**dict(PANIC_BOOKING.arguments), "total_baggages": baggages}
        with flaky_world(environment, FlakyConfig(seed=seed, p_error=0.0)) as world:
            environment.get_response(tool_call("book_reservation", **arguments))
            (same if baggages == 1 else different).append(flaky_db_hash(environment, world))

    assert same[0] != different[0]


def test_the_world_records_what_it_did_for_the_manifest():
    environment = environment_for()

    with flaky_world(environment, FlakyConfig(seed=9, p_error=0.0)) as world:
        environment.get_response(tool_call("book_reservation", **dict(PANIC_BOOKING.arguments)))
        manifest = world.manifest()

    assert manifest["seed"] == 9
    assert manifest["generated_ids"]
    assert manifest["executions"] == 1
    assert manifest["canonical_ids"][manifest["generated_ids"][0]] == "HATHAT"


# ---- recording, and the drift that justifies snapshots ----


@pytest.fixture(scope="module")
def flaky_recordings(tmp_path_factory) -> dict:
    """`MEASURED_RUNS` recordings of the same scenario, one seed each."""
    from agent_bisect.adapters.tau2 import record_run, recording_session
    from agent_bisect.adapters.tau2_fake_llm import ScriptedLLM

    root = tmp_path_factory.mktemp("flaky")
    store = Store(root / "runs")
    scripts = {AGENT_MODEL: list(FLAKY_SCENARIO.agent), USER_MODEL: list(FLAKY_SCENARIO.user)}
    runs: list[tuple[str, FlakyConfig]] = []
    with recording_session(
        ledger=ledger_for(root), phase="test", completion_fn=ScriptedLLM(scripts).completion,
        api_key=UNUSED_API_KEY, api_base=UNUSED_API_BASE, limiter_for=no_limiter,
    ):
        from agent_bisect.adapters.tau2 import RunSpec, Tau2Recorder, build_orchestrator

        for index in range(MEASURED_RUNS):
            config = FlakyConfig(seed=1000 + index)
            run_id = f"flaky-{index}"
            spec = RunSpec(domain="airline", task_id="0", agent_model=AGENT_MODEL,
                           user_model=USER_MODEL, seed=42)
            orchestrator = build_orchestrator(spec, run_id)
            with flaky_world(orchestrator.environment, config) as world_used:
                simulation = _record(orchestrator, spec, run_id, store, record_run,
                                     Tau2Recorder)
            runs.append((run_id, config))
            if index == 0:
                scored = (simulation, orchestrator.task, world_used)
    return {"store": store, "runs": runs, "scored": scored}


def _record(orchestrator, spec, run_id, store, record_run, recorder_class):
    """Record one run on an environment the flaky world already wraps."""
    from datetime import UTC, datetime

    from agent_bisect.core.tape import RunManifest
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.runner.simulation import run_simulation

    # COMMUNICATE, not ALL, and this is the whole reason decision 0011
    # exists: `EvaluationType.ALL` makes tau2's evaluator replay the run's
    # write actions on an environment of its own, where `book_reservation`
    # mints `HATHAT` while the recording holds a random id. It does not
    # merely score 0 — `Environment.set_state` raises on the mismatch
    # (`environment/environment.py:401`, strict replay). The flaky-world
    # reward is the canonicalised DB check instead.

    recorder = recorder_class(run_id, store.blobs, store.tape, orchestrator.environment)
    recorder.start(
        RunManifest(run_id=run_id, domain=spec.domain, task_id=spec.task_id,
                    agent_model=spec.agent_model, user_model=spec.user_model,
                    params=spec.manifest_params, seed=spec.seed, tau2_commit="flaky-test",
                    created_at=datetime.now(UTC))
    )
    with recorder.bind(orchestrator.environment):
        simulation = run_simulation(orchestrator, evaluation_type=EvaluationType.COMMUNICATE)
    result = simulation
    if simulation.reward_info is not None:
        recorder.record_outcome(
            reward=simulation.reward_info.reward,
            termination_reason=str(getattr(simulation.termination_reason, "value",
                                           simulation.termination_reason)),
            breakdown=simulation.reward_info.model_dump(mode="json"),
        )
    return result


def test_the_canonicalised_reward_can_be_computed_where_tau2s_cannot(flaky_recordings):
    """The decision-0011 measurement, end to end: scoring a flaky run that
    books with `EvaluationType.ALL` raises, because tau2 replays the write
    action on its own environment and mints `HATHAT` where the recording
    holds a random id. The same evaluation on the canonicalised trajectory
    returns a reward."""
    from agent_bisect.adapters.tau2_flaky import flaky_evaluate
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation

    simulation, task, world = flaky_recordings["scored"]

    with pytest.raises(ValueError, match="Tool call"):
        evaluate_simulation(simulation=simulation, task=task,
                            evaluation_type=EvaluationType.ALL, solo_mode=False,
                            domain="airline")

    reward_info = flaky_evaluate(simulation, task, "airline", world)

    assert reward_info.reward in (0.0, 1.0)


def test_canonicalising_a_trajectory_renames_the_generated_id(flaky_recordings):
    from agent_bisect.adapters.tau2_flaky import canonical_simulation

    simulation, _task, world = flaky_recordings["scored"]
    flaky_id = world.id_trail[0][0]

    renamed = canonical_simulation(simulation, world)

    assert flaky_id in simulation.model_dump_json()
    assert flaky_id not in renamed.model_dump_json()
    assert "HATHAT" in renamed.model_dump_json()


def test_a_flaky_run_records_like_any_other(flaky_recordings):
    store = flaky_recordings["store"]

    for run_id, _config in flaky_recordings["runs"]:
        steps = store.reader.get_steps(run_id)
        assert [step.actor for step in steps][:2] == ["user", "agent"]
        assert any(step.actor == "tool" for step in steps)


def test_two_flaky_recordings_of_the_same_script_differ(flaky_recordings):
    """The premise of the ablation: the world itself is not reproducible."""
    store = flaky_recordings["store"]
    hashes = {
        store.reader.get_steps(run_id)[-1].state_hash
        for run_id, _config in flaky_recordings["runs"]
    }

    assert len(hashes) > 1


def test_rerun_live_drifts_where_snapshot_does_not(flaky_recordings, capsys):
    """The measurement. Snapshot restores are exact at every tool step;
    re-executing the same calls later is not, in X% of runs."""
    store = flaky_recordings["store"]
    snapshot = _Tally()
    live = _Tally()
    for run_id, config in flaky_recordings["runs"]:
        steps = [step for step in store.reader.get_steps(run_id) if step.actor == "tool"]
        snapshot.add(_snapshot_reproduced(store, steps))
        live.add(_rerun_live_reproduced(store, steps, config))

    with capsys.disabled():
        print(
            f"\nflaky-world drift over {MEASURED_RUNS} runs "
            f"({snapshot.steps} tool steps): "
            f"snapshot reproduced {snapshot.step_rate:.0%} of steps and "
            f"{snapshot.run_rate:.0%} of runs; "
            f"rerun_live reproduced {live.step_rate:.0%} of steps and "
            f"{live.run_rate:.0%} of runs "
            f"(X = {1 - live.run_rate:.0%} of runs drift)"
        )

    assert snapshot.step_rate == 1.0
    assert snapshot.run_rate == 1.0
    assert live.run_rate < 1.0


class _Tally:
    """Steps and runs that reproduced the recording."""

    def __init__(self) -> None:
        self.steps = 0
        self.steps_ok = 0
        self.runs = 0
        self.runs_ok = 0

    def add(self, results: list[bool]) -> None:
        self.steps += len(results)
        self.steps_ok += sum(results)
        self.runs += 1
        self.runs_ok += int(all(results))

    @property
    def step_rate(self) -> float:
        return self.steps_ok / self.steps if self.steps else 0.0

    @property
    def run_rate(self) -> float:
        return self.runs_ok / self.runs if self.runs else 0.0


def _snapshot_reproduced(store: Store, steps) -> list[bool]:
    """Restore each step's recorded snapshot and check the world matches."""
    environment = environment_for()
    snapshotter = Tau2Snapshotter(environment)
    results = []
    for step in steps:
        snapshotter.restore(store.blobs.get_json(step.state_after))
        results.append(snapshotter.state_hash() == step.state_hash)
    return results


def _rerun_live_reproduced(store: Store, steps, config: FlakyConfig) -> list[bool]:
    """Execute the same calls again, later, restoring nothing."""
    environment = environment_for()
    snapshotter = Tau2Snapshotter(environment)
    results = []
    with flaky_world(environment, FlakyConfig(**{**config.as_dict(),
                                                "seed": config.seed + 5000})):
        for step in steps:
            message = environment.get_response(
                tool_call(step.tool_name or "", **dict(step.tool_args or {}))
            )
            recorded = store.blobs.get_json(step.tool_result_ref or "")
            results.append(
                _same(message.content, recorded.get("content"))
                and snapshotter.state_hash() == step.state_hash
            )
    return results


def _same(one: str | None, other: str | None) -> bool:
    """Equal as data: a restored snapshot is key-sorted, a live db is not."""
    try:
        return json.loads(one or "") == json.loads(other or "")
    except ValueError:
        return one == other
