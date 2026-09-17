"""P5 end to end, offline: a real planted fault on a real tau2 environment.

Every run here drives tau2's own orchestrator, environment and evaluator
with sockets blocked; only the model is scripted
(`tests/p5_offline.ReactiveAirlineAgent`). The pipeline under test is the
whole of P5: judge -> shortlist -> intervention by step type -> forked
re-runs -> shared control -> earliest step clearing delta -> scored
against the label -> report.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from agent_bisect.adapters.tau2 import RunSpec, record_run, recording_session
from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor
from agent_bisect.adapters.tau2_scenarios import AGENT_MODEL, USER_MODEL
from agent_bisect.adapters.tau2_task import task_text
from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
from agent_bisect.attribution.estimate import SequentialConfig
from agent_bisect.attribution.interventions import ReplaceToolResult
from agent_bisect.attribution.search import RerunRequest
from agent_bisect.bench.baselines import BaselineConfig
from agent_bisect.bench.eval_run import evaluate_dataset, outcome_rows, outcomes_from_rows
from agent_bisect.bench.evaluate import build_report, score_outcomes
from agent_bisect.bench.manifest import DatasetItem
from agent_bisect.core.replay import NoOpIntervention
from agent_bisect.core.tape import TapeReader, TapeWriter
from tests.p5_offline import (
    DOMAIN,
    FAULTED_CABIN,
    TASK_ID,
    TRUE_CABIN,
    FakeJudge,
    ReactiveAirlineAgent,
)
from tests.tau2_offline import (
    UNUSED_API_BASE,
    UNUSED_API_KEY,
    Store,
    ledger_for,
    no_limiter,
    quiet_tau2,
)

pytestmark = pytest.mark.usefixtures("_no_real_key")

#: Four draws per arm is enough here because the scripted agent is a
#: function of its conversation: the treated arm passes 4/4 and the control
#: fails 0/4, whose Newcombe lower bound is ~0.31, well clear of delta.
TOY_CONFIG = SequentialConfig(batch=4, max_n=4, efficacy_boundary="none")
BASE_RUN = "base-1"
FAULTED_RUN = "faulted-1"


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


def _spec() -> RunSpec:
    return RunSpec(
        domain=DOMAIN, task_id=TASK_ID,
        agent_model=AGENT_MODEL, user_model=USER_MODEL, seed=42,
    )


def _session(store: Store, agent: ReactiveAirlineAgent):
    return recording_session(
        ledger=ledger_for(store.root),
        phase="test",
        completion_fn=agent.completion,
        api_key=UNUSED_API_KEY,
        api_base=UNUSED_API_BASE,
        limiter_for=no_limiter,
    )


def _reservation_step(store: Store, run_id: str) -> int:
    """The tool step whose result the agent's decision turns on."""
    for step in store.reader.get_steps(run_id):
        if step.tool_name == "get_reservation_details":
            return step.step_idx
    raise AssertionError("the recording has no get_reservation_details step")


def _faulted_payload(store: Store, run_id: str, step_idx: int) -> dict:
    """The recorded tool result with `business` rewritten to `economy`."""
    step = store.reader.get_step(run_id, step_idx)
    assert step.tool_result_ref is not None
    payload = dict(store.blobs.get_json(step.tool_result_ref))
    payload["content"] = str(payload["content"]).replace(
        f'"{TRUE_CABIN}"', f'"{FAULTED_CABIN}"'
    )
    return payload


@pytest.fixture(scope="module")
def planted(tmp_path_factory) -> dict:
    """Record a passing run, plant one fault in it, and keep both."""
    root = tmp_path_factory.mktemp("p5") / "runs"
    store = Store(root)
    agent = ReactiveAirlineAgent()
    with _session(store, agent):
        base = record_run(_spec(), run_id=BASE_RUN, store=store.blobs, tape=store.tape)

        planted_step = _reservation_step(store, BASE_RUN)
        executor = Tau2ForkExecutor(
            store=store.blobs,
            reader=store.reader,
            tape=store.tape,
        )
        faulted = executor.run(
            RerunRequest(
                parent_run_id=BASE_RUN,
                run_id=FAULTED_RUN,
                fork_step=planted_step,
                arm="treated",
                intervention=ReplaceToolResult(
                    step=planted_step,
                    new_result=_faulted_payload(store, BASE_RUN, planted_step),
                ),
                seed=7,
                prefix_tools="snapshot",
                unsafe_positional=False,
            )
        )
    return {
        "root": root,
        "store": store,
        "agent": agent,
        "base": base,
        "faulted": faulted,
        "planted_step": planted_step,
    }


# ---- the scenario really is causal ----


def test_the_unfaulted_run_passes_for_tau2s_own_reasons(planted):
    # Arrange / Act
    base = planted["base"]

    # Assert
    assert base.outcome is not None
    assert base.outcome.reward == 1.0, "the agent refused, so the database is untouched"


def test_planting_the_fault_flips_the_run_to_a_failure(planted):
    # Arrange / Act / Assert
    assert planted["faulted"].passed is False


def test_the_planted_step_is_a_tool_step(planted):
    # Arrange / Act
    step = planted["store"].reader.get_step(FAULTED_RUN, planted["planted_step"])

    # Assert
    assert step.actor == "tool"
    assert step.tool_name == "get_reservation_details"


def test_the_faulted_run_is_a_complete_recording_of_its_own(planted):
    # Arrange / Act
    steps = planted["store"].reader.get_steps(FAULTED_RUN)

    # Assert
    assert steps
    assert planted["store"].reader.get_outcome(FAULTED_RUN) is not None


# ---- the truthful fix undoes it without knowing the label ----


def test_re_executing_the_faulted_step_recovers_the_true_answer(planted):
    # Arrange
    store = planted["store"]
    resolver = Tau2TruthResolver(DOMAIN, TASK_ID, store.blobs)
    step = store.reader.get_step(FAULTED_RUN, planted["planted_step"])

    # Act
    truth = resolver(step)

    # Assert
    assert f'"{TRUE_CABIN}"' in str(truth["content"])


# ---- the whole pipeline ----


def _item(planted, item_id: str = "item-1") -> DatasetItem:
    return DatasetItem(
        item_id=item_id,
        domain=DOMAIN,
        task_id=TASK_ID,
        split="dev",
        base_run_id=BASE_RUN,
        base_pass_rate=1.0,
        run_id=FAULTED_RUN,
        faulted_pass_rate=0.0,
        planted_step=planted["planted_step"],
        position_bucket="middle",
        fault_type="wrong_value",
        mutation={"path": ["content"], "detail": f"{TRUE_CABIN} -> {FAULTED_CABIN}"},
        oracle={},
        intervention={},
        seeds=[7],
        n_reruns=4,
    )


def _run_pipeline(planted, judge: FakeJudge, *, seed: int = 3, control_mode="per_step"):
    store = planted["store"]
    executor = Tau2ForkExecutor(
        store=store.blobs,
        reader=TapeReader(planted["root"]),
        tape=TapeWriter(planted["root"]),
    )
    item = _item(planted)
    with _session(store, planted["agent"]):
        return evaluate_dataset(
            [item],
            reader=store.reader,
            store=store.blobs,
            judge_backend=judge,
            executor=executor,
            task_text=task_text,
            config=BaselineConfig(
                top_m=3, sequential=TOY_CONFIG, control_mode=control_mode
            ),
            seed=seed,
            runs_dir=planted["root"],
            truth_for_item=lambda entry: Tau2TruthResolver(
                entry.domain, entry.task_id, store.blobs
            ),
        ), item


def test_bisect_blames_the_planted_step_when_the_judge_shortlists_it(planted):
    # Arrange: the judge ranks the culprit second, so only a method that
    # confirms its shortlist can get the answer right.
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})

    # Act
    run, item = _run_pipeline(planted, judge)
    by_method = {outcome.method: outcome for outcome in run.outcomes}

    # Assert
    assert run.failures == []
    assert by_method["bisect"].predicted_step == culprit
    assert by_method["judge_all_at_once"].predicted_step == 0


def test_a_control_forked_before_the_fault_does_not_reproduce_the_failure(planted):
    """The finding that decides which control mode P5 can use.

    A fault planted with `ReplaceToolResult` lives in the *recording*, not
    in the world: the database was never touched. So a fork taken BEFORE
    the planted step re-executes that tool live, gets the true answer, and
    the run passes -- it is not a control for this failure at all. A fork
    taken AT the planted step serves the faulted result from the tape and
    does reproduce it.

    Under `control_mode="shared"` the control is forked at the earliest
    tested step, which is usually earlier than the planted one, so the
    control pass rate is the *base* run's rather than the failure's and
    every effect collapses towards zero. `docs/findings/p5-control-fork.md`.
    """
    # Arrange
    store = planted["store"]
    culprit = planted["planted_step"]
    executor = Tau2ForkExecutor(
        store=store.blobs, reader=store.reader, tape=store.tape
    )

    def control_at(step: int) -> bool:
        return executor.run(
            RerunRequest(
                parent_run_id=FAULTED_RUN,
                run_id=f"probe-control-{step}",
                fork_step=step,
                arm="control",
                intervention=NoOpIntervention(),
                seed=11,
                prefix_tools="snapshot",
                unsafe_positional=False,
            )
        ).passed

    # Act
    with _session(store, planted["agent"]):
        before = control_at(0)
        at_the_fault = control_at(culprit)

    # Assert
    assert at_the_fault is False, "forking at the fault must reproduce the failure"
    assert before is True, (
        "forking before the fault loses it: the tool is re-executed live and "
        "answers truthfully, so this is not a control for this failure"
    )


def test_the_shared_control_misses_the_planted_step_on_this_dataset(planted):
    # Arrange: the judge ranks an innocent earlier step first, so the shared
    # control forks before the fault.
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})

    # Act
    run, _ = _run_pipeline(planted, judge, seed=21, control_mode="shared")
    by_method = {outcome.method: outcome for outcome in run.outcomes}

    # Assert
    assert by_method["bisect"].predicted_step is None


def test_bisect_cannot_find_a_step_the_judge_never_shortlisted(planted):
    # Arrange
    judge = FakeJudge(answers={"item-1": [0]})

    # Act
    run, _ = _run_pipeline(planted, judge)
    by_method = {outcome.method: outcome for outcome in run.outcomes}

    # Assert
    assert by_method["bisect"].predicted_step is None


def test_a_judge_that_cannot_answer_costs_no_reruns_and_is_scored_wrong(planted):
    # Arrange
    judge = FakeJudge(answers={}, fallback=())

    # Act
    run, item = _run_pipeline(planted, judge)
    scores = score_outcomes([item], run.outcomes)

    # Assert
    assert all(score.correct is False for score in scores)
    assert {score.verdict for score in scores} == {"none"}


def test_the_report_reports_the_expected_accuracies_and_recall(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})

    # Act
    run, item = _run_pipeline(planted, judge)
    report = build_report(
        score_outcomes([item], run.outcomes),
        split="dev", seed=1, bootstrap_resamples=100,
    )
    accuracy = {row["method"]: row["accuracy"]["value"] for row in report["methods"]}

    # Assert
    assert accuracy["bisect"] == 1.0
    assert accuracy["judge_all_at_once"] == 0.0
    assert report["recall"]["judge_all_at_once"]["1"] == 0.0
    assert report["recall"]["judge_all_at_once"]["2"] == 1.0


def test_the_gap_over_the_best_judge_is_reported_with_its_interval(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})

    # Act
    run, item = _run_pipeline(planted, judge)
    report = build_report(
        score_outcomes([item], run.outcomes),
        split="dev", seed=1, bootstrap_resamples=100,
    )

    # Assert
    assert report["gap"]["value"] == 1.0
    assert report["gap"]["ci_low"] <= report["gap"]["value"] <= report["gap"]["ci_high"]


def test_the_control_at_the_planted_step_fails_every_time(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})

    # Act
    run, _ = _run_pipeline(planted, judge)
    blame = next(o.blame for o in run.outcomes if o.method == "bisect")

    # Assert
    assert blame is not None
    at_fault = [r for r in blame.reruns if r.arm == "control" and r.step == culprit]
    assert len(at_fault) == TOY_CONFIG.max_n
    assert not any(record.passed for record in at_fault)


def test_the_control_at_an_innocent_earlier_step_passes_every_time(planted):
    # Arrange: the same forks, at a step before the fault -- the evidence
    # that the shared control arm is not one control but two populations.
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})

    # Act
    run, _ = _run_pipeline(planted, judge)
    blame = next(o.blame for o in run.outcomes if o.method == "bisect")

    # Assert
    assert blame is not None
    early = [r for r in blame.reruns if r.arm == "control" and r.step == 0]
    assert early and all(record.passed for record in early)


def test_the_treated_arm_at_the_planted_step_passes_every_time(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [culprit]})

    # Act
    run, _ = _run_pipeline(planted, judge)
    blame = next(o.blame for o in run.outcomes if o.method == "bisect")

    # Assert
    assert blame is not None
    treated = [r for r in blame.reruns if r.arm == "treated" and r.step == culprit]
    assert treated and all(record.passed for record in treated)


def test_the_blame_document_is_written_where_the_dashboard_reads_it(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [culprit]})

    # Act
    _run_pipeline(planted, judge)
    document = Path(planted["root"]) / "blame" / f"{FAULTED_RUN}.json"

    # Assert
    assert document.exists()


def test_the_outcome_table_round_trips_so_the_report_can_be_rebuilt(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [0, culprit]})
    run, item = _run_pipeline(planted, judge)

    # Act
    rebuilt = outcomes_from_rows(outcome_rows(run.outcomes))
    first = build_report(
        score_outcomes([item], run.outcomes), split="dev", seed=1, bootstrap_resamples=50
    )
    second = build_report(
        score_outcomes([item], rebuilt), split="dev", seed=1, bootstrap_resamples=50
    )

    # Assert
    assert first == second


def test_a_second_pass_reuses_the_forks_the_first_one_paid_for(planted):
    # Arrange
    culprit = planted["planted_step"]
    judge = FakeJudge(answers={"item-1": [culprit]})
    store = planted["store"]
    _run_pipeline(planted, judge)

    executor = Tau2ForkExecutor(
        store=store.blobs,
        reader=store.reader,
        tape=store.tape,
    )

    # Act
    from agent_bisect.attribution.trajectory import build_judge_input
    from agent_bisect.bench.baselines import evaluate_item, judge_item

    description, policy = task_text(DOMAIN, TASK_ID)
    judge_input = build_judge_input(
        FAULTED_RUN, reader=store.reader, store=store.blobs,
        item_id="item-1", task_description=description, policy=policy,
    )
    with _session(store, planted["agent"]):
        judgement = judge_item(judge_input, judge, step_by_step=False)
        evaluate_item(
            item_id="item-1",
            run_id=FAULTED_RUN,
            steps=store.reader.get_steps(FAULTED_RUN),
            judgement=judgement,
            executor=executor,
            config=BaselineConfig(
                top_m=3, sequential=TOY_CONFIG, methods=("bisect",)
            ),
            seed=3,
            truth_for=Tau2TruthResolver(DOMAIN, TASK_ID, store.blobs),
        )

    # Assert
    assert executor.reused > 0, "a resumed evaluation must not pay for a fork twice"


def test_the_item_is_recorded_as_unevaluated_when_its_run_is_missing(planted):
    # Arrange
    store = planted["store"]
    executor = Tau2ForkExecutor(
        store=store.blobs, reader=store.reader, tape=store.tape,
    )
    ghost = _item(planted, item_id="item-ghost").model_copy(update={"run_id": "nope"})

    # Act
    run = evaluate_dataset(
        [ghost],
        reader=store.reader,
        store=store.blobs,
        judge_backend=FakeJudge(answers={}),
        executor=executor,
        task_text=task_text,
        config=BaselineConfig(top_m=3, sequential=TOY_CONFIG),
        seed=3,
        runs_dir=planted["root"],
    )

    # Assert
    assert run.n_failed_items == 1
    assert len(run.outcomes) == 5, "every method still answers, wrongly, with a reason"
    assert all(outcome.predicted_step is None for outcome in run.outcomes)


def test_a_manifest_item_carries_the_label_the_report_scores_against(planted):
    # Arrange / Act
    item = _item(planted)

    # Assert
    assert item.planted_step == planted["planted_step"]
    assert item.fault_type == "wrong_value"
    assert datetime.now(UTC) is not None
