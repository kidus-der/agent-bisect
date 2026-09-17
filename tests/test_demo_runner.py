"""The demo suite end to end: real tau2 mock-domain orchestrator, scripted
agent and user, zero network calls, zero secrets.

These are integration tests in the same spirit as `tests/test_p5_end_to_end
.py`: the only thing scripted is the model, everything else -- the
orchestrator, the environment, the evaluator -- is tau2's own.
"""

from __future__ import annotations

import pytest
from demo.agent import demo_completion
from demo.faults import corrupted_get_users_result, get_users_step, plant_wrong_lookup_key
from demo.harness import UNUSED_API_BASE, UNUSED_API_KEY, Store, ledger_for, no_limiter
from demo.runner import DEFAULT_SEED, run_suite
from demo.tasks import AGENT_MODEL, DOMAIN, SCENARIOS, USER_MODEL, run_id_for, scenario


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    from loguru import logger

    logger.remove()


pytestmark = pytest.mark.usefixtures("_no_real_key")


def test_the_suite_runs_every_scenario_the_configured_number_of_times(tmp_path):
    result = run_suite(seed=DEFAULT_SEED, runs_per_scenario=2, out_dir=tmp_path / "out")

    assert len(result.scenarios) == len(SCENARIOS)
    assert all(len(s.runs) == 2 for s in result.scenarios)
    assert result.total_runs == 2 * len(SCENARIOS)


def test_the_default_policy_passes_most_but_not_all_runs(tmp_path):
    """The suite's own target range (`docs/decisions/0019-gate-rule.md`)."""
    result = run_suite(seed=DEFAULT_SEED, runs_per_scenario=8, out_dir=tmp_path / "out")

    assert 0.7 <= result.pass_rate <= 1.0
    # At n=64 draws across 4 non-trivial slip probabilities, at least one
    # scenario should show *some* variance -- a suite that always passes
    # 100% could not be testing anything.
    assert any(s.pass_rate < 1.0 for s in result.scenarios)


def test_a_run_is_reproducible_byte_for_byte_given_the_same_seed(tmp_path):
    first = run_suite(seed=1, runs_per_scenario=2, out_dir=tmp_path / "a")
    second = run_suite(seed=1, runs_per_scenario=2, out_dir=tmp_path / "b")

    first_outcomes = [(s.name, [r.passed for r in s.runs]) for s in first.scenarios]
    second_outcomes = [(s.name, [r.passed for r in s.runs]) for s in second.scenarios]
    assert first_outcomes == second_outcomes


def test_a_different_seed_can_change_which_runs_slip(tmp_path):
    """Not a hard guarantee for every pair, but true for these two."""
    a = run_suite(seed=1, runs_per_scenario=4, out_dir=tmp_path / "a")
    b = run_suite(seed=999983, runs_per_scenario=4, out_dir=tmp_path / "b")

    a_outcomes = [tuple(r.passed for r in s.runs) for s in a.scenarios]
    b_outcomes = [tuple(r.passed for r in s.runs) for s in b.scenarios]
    assert a_outcomes != b_outcomes


def test_unfaulted_lookup_scenarios_find_the_freshly_created_task(tmp_path):
    result = run_suite(seed=DEFAULT_SEED, runs_per_scenario=1, out_dir=tmp_path / "out")
    by_name = {s.name: s for s in result.scenarios}

    for name in ("update_task_from_initialization_data", "update_task_from_initialization_actions"):
        assert by_name[name].runs[0].passed, name


# ---- the standing fault: plant, then confirm it away --------------------


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "store")


def _record_clean(store: Store, task_id: str, run_id: str, *, seed: int = 1):
    from agent_bisect.adapters.tau2 import RunSpec, record_run

    spec = RunSpec(
        domain=DOMAIN, task_id=task_id, agent_model=AGENT_MODEL, user_model=USER_MODEL, seed=seed
    )
    return record_run(spec, run_id=run_id, store=store.blobs, tape=store.tape)


def _session(store: Store):
    from agent_bisect.adapters.tau2 import recording_session

    return recording_session(
        ledger=ledger_for(store.root), phase="test", completion_fn=demo_completion,
        api_key=UNUSED_API_KEY, api_base=UNUSED_API_BASE, limiter_for=no_limiter,
    )


# Every run id used below must start with `demo-<scenario name>-` --
# `demo.agent.demo_completion` resolves the active run's scenario (and so
# its policy rule) from the run id alone (`demo.tasks.scenario_of_run_id`),
# so an ad-hoc id here would make the agent raise `KeyError` mid-run, which
# `Tau2Router` mistakes for a retryable transport error and sleeps on
# (`adapters/tau2_llm.py`'s backoff) instead of failing fast.


def test_the_clean_recording_of_a_fault_injectable_scenario_passes(store):
    spec = scenario("update_task_from_initialization_data")
    run_id = run_id_for(spec.name, 0) + "-clean"
    with _session(store):
        recorded = _record_clean(store, spec.task_id, run_id)

    assert recorded.outcome is not None
    assert recorded.outcome.passed is True


def test_planting_the_wrong_lookup_key_fault_flips_the_run_to_a_failure(store):
    spec = scenario("update_task_from_initialization_actions")
    clean_id = run_id_for(spec.name, 1) + "-clean"
    faulted_id = run_id_for(spec.name, 1)
    with _session(store):
        _record_clean(store, spec.task_id, clean_id)
        outcome = plant_wrong_lookup_key(
            parent_run_id=clean_id, run_id=faulted_id,
            store=store.blobs, reader=store.reader, tape=store.tape,
        )

    assert outcome.passed is False


def test_the_corrupted_answer_drops_only_the_newest_task(store):
    spec = scenario("update_task_from_initialization_data")
    run_id = run_id_for(spec.name, 2) + "-clean"
    with _session(store):
        _record_clean(store, spec.task_id, run_id)
    step = get_users_step(store.reader, run_id)

    corrupted = corrupted_get_users_result(store.blobs, step)

    import json

    users = json.loads(corrupted["content"])
    assert users[0]["tasks"] == ["task_1"]


def test_a_run_with_no_get_users_step_cannot_be_faulted(store):
    from demo.faults import NoGetUsersStepError

    spec = scenario("update_task_fixed_id")
    run_id = run_id_for(spec.name, 0) + "-clean"
    with _session(store):
        _record_clean(store, spec.task_id, run_id)

    with pytest.raises(NoGetUsersStepError):
        get_users_step(store.reader, run_id)


def test_truthful_tool_result_recovers_the_planted_fault(store):
    from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor
    from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
    from agent_bisect.attribution.interventions import TruthfulToolResult
    from agent_bisect.attribution.search import RerunRequest
    from agent_bisect.core.replay import NoOpIntervention

    spec = scenario("update_task_from_initialization_data")
    clean_id = run_id_for(spec.name, 3) + "-clean"
    faulted_id = run_id_for(spec.name, 3)
    with _session(store):
        _record_clean(store, spec.task_id, clean_id)
        plant_wrong_lookup_key(
            parent_run_id=clean_id, run_id=faulted_id,
            store=store.blobs, reader=store.reader, tape=store.tape,
        )
    step = get_users_step(store.reader, faulted_id)
    executor = Tau2ForkExecutor(store=store.blobs, reader=store.reader, tape=store.tape)
    resolver = Tau2TruthResolver(DOMAIN, spec.task_id, store.blobs)

    with _session(store):
        treated = executor.run(
            RerunRequest(
                parent_run_id=faulted_id, run_id=faulted_id + "-treated", fork_step=step.step_idx,
                arm="treated",
                intervention=TruthfulToolResult(step=step.step_idx).with_truth(resolver),
                seed=1, prefix_tools="snapshot", unsafe_positional=False,
            )
        )
        control = executor.run(
            RerunRequest(
                parent_run_id=faulted_id, run_id=faulted_id + "-control", fork_step=step.step_idx,
                arm="control", intervention=NoOpIntervention(),
                seed=1, prefix_tools="snapshot", unsafe_positional=False,
            )
        )

    assert treated.passed is True
    assert control.passed is False


def test_the_standing_fault_survives_a_fork_taken_before_it(store):
    """The finding `docs/decisions/0016-persistent-planted-fault.md` fixed:
    a control forked before the fault must still reproduce it."""
    from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor
    from agent_bisect.attribution.search import RerunRequest
    from agent_bisect.core.replay import NoOpIntervention

    spec = scenario("update_task_from_initialization_actions")
    clean_id = run_id_for(spec.name, 4) + "-clean"
    faulted_id = run_id_for(spec.name, 4)
    with _session(store):
        _record_clean(store, spec.task_id, clean_id)
        plant_wrong_lookup_key(
            parent_run_id=clean_id, run_id=faulted_id,
            store=store.blobs, reader=store.reader, tape=store.tape,
        )
    executor = Tau2ForkExecutor(store=store.blobs, reader=store.reader, tape=store.tape)

    with _session(store):
        before = executor.run(
            RerunRequest(
                parent_run_id=faulted_id, run_id=faulted_id + "-before", fork_step=0,
                arm="control", intervention=NoOpIntervention(),
                seed=1, prefix_tools="snapshot", unsafe_positional=False,
            )
        )

    assert before.passed is False, "the standing fault must reproduce even forked before it"


def test_unscripted_model_name_raises():
    from demo.agent import UnscriptedModelError

    with pytest.raises(UnscriptedModelError):
        demo_completion(
            model="openai/not-a-demo-model", messages=[{"role": "user", "content": "hi"}]
        )
