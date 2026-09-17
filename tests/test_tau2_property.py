"""Property test: for a randomly scripted tau2 run, `replay(record(run))`
is the run.

The scripted scenarios in `adapters/tau2_scenarios.py` are chosen to cover
the awkward shapes; this covers the shapes nobody chose. Every example
drives the real orchestrator, environment and evaluator with sockets
blocked.
"""

from __future__ import annotations

from typing import Any

import pytest
from agent_bisect.adapters.tau2_fake_llm import ScriptedToolCall, ScriptedTurn
from agent_bisect.adapters.tau2_replay import replay_run
from agent_bisect.adapters.tau2_scenarios import STOP, Scenario
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.tau2_offline import Store, quiet_tau2, record

pytestmark = pytest.mark.usefixtures("_no_real_key")


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


#: Airline calls that are valid whatever the DB already holds. The last two
#: are the interesting ones: `get_reservation_details` on an id that does
#: not exist comes back as a tool *error*, and `send_certificate` is a
#: WRITE, so it moves the DB hash (and eventually runs out of certificate
#: ids, which is itself a deterministic error worth recording).
_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("get_user_details", {"user_id": "mia_li_3668"}),
    ("list_all_airports", {}),
    ("calculate", {"expression": "2 + 2"}),
    ("search_direct_flight", {"origin": "PHL", "destination": "LGA", "date": "2024-05-16"}),
    ("get_flight_status", {"flight_number": "HAT001", "date": "2024-05-16"}),
    ("get_reservation_details", {"reservation_id": "NOPE11"}),
    ("send_certificate", {"user_id": "mia_li_3668", "amount": 50}),
]

#: One "phase" is some tool-call turns followed by a message to the user.
_phases = st.lists(
    st.lists(st.lists(st.sampled_from(_CALLS), min_size=1, max_size=2), min_size=0, max_size=3),
    min_size=1,
    max_size=3,
)


def _scenario(phases: list[list[list[tuple[str, dict]]]], task_id: str) -> Scenario:
    """Turn a generated shape into a scenario the orchestrator can run.

    The user opens, then answers each of the agent's messages; the last
    thing it says ends the run.
    """
    agent: list[ScriptedTurn] = []
    call_id = 0
    for index, turns in enumerate(phases):
        for calls in turns:
            scripted = []
            for name, arguments in calls:
                call_id += 1
                scripted.append(ScriptedToolCall(id=f"c{call_id}", name=name, arguments=arguments))
            agent.append(ScriptedTurn(tool_calls=tuple(scripted)))
        agent.append(ScriptedTurn(content=f"Phase {index} done. Anything else?"))
    user = [ScriptedTurn(content="Hello, I need some help.")]
    user.extend(ScriptedTurn(content="Yes, carry on.") for _ in range(len(phases) - 1))
    user.append(ScriptedTurn(content=STOP))
    return Scenario(
        name="generated", domain="airline", task_id=task_id, agent=tuple(agent), user=tuple(user)
    )


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(phases=_phases, task_id=st.sampled_from(["0", "1", "2"]))
def test_replaying_a_recorded_run_reproduces_it(tmp_path_factory, phases, task_id):
    store = Store(tmp_path_factory.mktemp("property"))
    scenario = _scenario(phases, task_id)

    recorded, _ = record(scenario, store, run_id="r1")
    assert recorded.outcome is not None

    result = replay_run("r1", store=store.blobs, reader=store.reader)

    # `replay_run` has already checked, step by step, that every request
    # hash, every tool result and every state hash matched, that the whole
    # tape was consumed and that the reward agreed. What is left to pin is
    # that it got there the same way, and spent nothing doing it.
    assert result.steps == recorded.steps
    assert result.live_llm_calls == 0
    assert result.tape_llm_calls == sum(recorded.llm_calls_by_actor.values())
    assert result.termination_reason == recorded.termination_reason


@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(phases=_phases)
def test_every_recorded_step_restores_to_its_recorded_hash(tmp_path_factory, phases):
    from agent_bisect.adapters.tau2 import build_orchestrator
    from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
    from tests.tau2_offline import spec_for

    store = Store(tmp_path_factory.mktemp("property-state"))
    scenario = _scenario(phases, "0")
    record(scenario, store, run_id="r1")

    environment = build_orchestrator(spec_for(scenario), "probe").environment
    snapshotter = Tau2Snapshotter(environment)

    for step in store.reader.get_steps("r1"):
        snapshotter.restore(store.blobs.get_json(step.state_before))
        assert snapshotter.state_hash() == step.state_hash_before
        snapshotter.restore(store.blobs.get_json(step.state_after))
        assert snapshotter.state_hash() == step.state_hash
