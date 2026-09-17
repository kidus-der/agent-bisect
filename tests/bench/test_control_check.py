"""A control arm that passes is not a control: flagged, reported, never dropped."""

from __future__ import annotations

from agent_bisect.attribution.estimate import ArmResult, RunEstimate, StepEffect
from agent_bisect.attribution.judge_view import JudgeVerdict, RankedStep
from agent_bisect.attribution.search import BlameConfig, BlameResult
from agent_bisect.bench.baselines import MethodOutcome
from agent_bisect.bench.eval_run import (
    CONTROL_PASS_LIMIT,
    check_controls,
    control_pass_rate,
)
from agent_bisect.bench.manifest import DatasetItem


def _item(faulted_pass_rate: float = 0.0) -> DatasetItem:
    return DatasetItem(
        item_id="item-1", domain="airline", task_id="1", split="dev",
        base_run_id="b1", base_pass_rate=1.0, run_id="r1",
        faulted_pass_rate=faulted_pass_rate, planted_step=4,
        position_bucket="middle", fault_type="wrong_value",
        mutation={}, oracle={}, intervention={}, seeds=[1], n_reruns=4,
    )


def _outcome(control: ArmResult | None, method="bisect") -> MethodOutcome:
    effect = StepEffect(
        step=4, treated=ArmResult(16, 16), control=control, effect=1.0,
        ci_low=0.7, ci_high=1.0, n_batches=4, stop_reason="blameworthy",
    )
    estimate = RunEstimate(
        step_effects=(effect,), blamed_step=4, control_mode="shared",
        control_fork_step=1, treated_reruns=16,
        control_reruns=0 if control is None else control.n, sampler_calls=2,
    )
    blame = BlameResult(
        item_id="item-1", run_id="r1", method="bisect", blamed_step=4,
        estimate=estimate, reruns=(),
        judge=JudgeVerdict(
            item_id="item-1", protocol="all_at_once", decisive_step=4,
            ranking=(RankedStep(step=4, rank=1, score=0.9, rationale="r"),),
            rationale="", calls=1,
        ),
        shortlist=(4,), tested_steps=(4,), interventions={4: "truthful_tool_result"},
        untestable=(), judge_calls=1, replay_calls=100, config=BlameConfig(),
    )
    return MethodOutcome(
        item_id="item-1", run_id="r1", method=method,  # type: ignore[arg-type]
        predicted_step=4, ranking=(4,), shortlist=(4,), judge_calls=1,
        replay_calls=100, reruns=32,
        control_reruns=0 if control is None else control.n,
        parse_failed=False, blame=blame,
    )


def test_a_control_that_always_fails_has_a_zero_pass_rate():
    assert control_pass_rate(_outcome(ArmResult(0, 16))) == 0.0


def test_a_control_that_always_passes_has_a_pass_rate_of_one():
    assert control_pass_rate(_outcome(ArmResult(16, 16))) == 1.0


def test_a_method_with_no_control_arm_has_no_rate_to_check():
    assert control_pass_rate(_outcome(None)) is None


def test_a_method_that_bought_no_reruns_has_no_rate_to_check():
    outcome = MethodOutcome(
        item_id="item-1", run_id="r1", method="judge_all_at_once",
        predicted_step=4, ranking=(4,), shortlist=(), judge_calls=1,
        replay_calls=0, reruns=0, control_reruns=0, parse_failed=False,
    )
    assert control_pass_rate(outcome) is None


def test_a_control_reproducing_the_failure_is_not_flagged():
    assert check_controls(_item(), [_outcome(ArmResult(0, 16))]) == []


def test_a_control_that_passes_most_of_the_time_is_flagged():
    flags = check_controls(_item(), [_outcome(ArmResult(16, 16))])
    assert len(flags) == 1
    assert flags[0].control_pass_rate == 1.0


def test_the_flag_explains_what_it_means_for_the_numbers():
    flags = check_controls(_item(), [_outcome(ArmResult(16, 16))])
    assert "understated" in flags[0].describe()


def test_the_limit_is_a_reporting_threshold_not_a_gate():
    # Exactly at the limit is not flagged; above it is.
    at_limit = ArmResult(int(16 * CONTROL_PASS_LIMIT), 16)
    assert check_controls(_item(), [_outcome(at_limit)]) == []
    assert check_controls(_item(), [_outcome(ArmResult(9, 16))])


def test_a_flagged_item_is_still_scored():
    """The flag is a note on the report, never a filter on the sample."""
    from agent_bisect.bench.evaluate import score_outcomes

    outcome = _outcome(ArmResult(16, 16))
    scores = score_outcomes([_item()], [outcome])
    assert len(scores) == 1
    assert scores[0].correct is True
