"""Bisect's search: judge shortlist -> one intervention per suspect -> earliest step."""

from __future__ import annotations

import numpy as np
import pytest
from agent_bisect.attribution.interventions import TruthfulToolResult
from agent_bisect.attribution.judge_view import JudgeVerdict, RankedStep
from agent_bisect.attribution.search import (
    BlameConfig,
    RerunOutcome,
    RerunRequest,
    choose_intervention,
    run_blame,
)
from agent_bisect.core.tape import Step

CALLS_PER_RERUN = 10


def _step(step_idx: int, actor: str = "tool") -> Step:
    return Step(
        run_id="run-1",
        step_idx=step_idx,
        actor=actor,  # type: ignore[arg-type]
        tool_name="get_reservation" if actor == "tool" else None,
        tool_args={"id": "ABC"} if actor == "tool" else None,
        tool_result_ref="res" if actor == "tool" else None,
        state_before="s",
        state_after="s",
        state_hash="h",
    )


def _steps(n: int = 10) -> tuple[Step, ...]:
    return tuple(_step(idx, "tool" if idx % 2 else "agent") for idx in range(n))


def _verdict(shortlist: list[int], *, calls: int = 1, failed: bool = False) -> JudgeVerdict:
    return JudgeVerdict(
        item_id="item-1",
        protocol="all_at_once",
        decisive_step=None if failed else shortlist[0],
        ranking=()
        if failed
        else tuple(
            RankedStep(step=step, rank=i + 1, score=0.9 - 0.1 * i, rationale="r")
            for i, step in enumerate(shortlist)
        ),
        rationale="because",
        calls=calls,
        parse_failed=failed,
        failure_reason="unparseable" if failed else None,
    )


class ScriptedExecutor:
    """Flips a scripted coin per fork and remembers every request it got."""

    def __init__(self, *, control_prob: float = 0.05, treated: dict[int, float] | None = None):
        self.control_prob = control_prob
        self.treated = treated or {}
        self.requests: list[RerunRequest] = []

    def run(self, request: RerunRequest) -> RerunOutcome:
        self.requests.append(request)
        probability = (
            self.control_prob
            if request.arm == "control"
            else self.treated.get(request.fork_step, self.control_prob)
        )
        passed = bool(np.random.default_rng(request.seed).random() < probability)
        return RerunOutcome(passed=passed, n_steps=12, calls=CALLS_PER_RERUN)


def _blame(verdict, executor, **overrides):
    config = BlameConfig(**overrides)
    return run_blame(
        item_id="item-1",
        run_id="run-1",
        steps=_steps(),
        verdict=verdict,
        executor=executor,
        config=config,
        seed=7,
    )


# ---- choose_intervention ----


def test_a_tool_step_gets_the_truthful_tool_result():
    # Arrange / Act
    intervention = choose_intervention(_step(3, "tool"))

    # Assert
    assert isinstance(intervention, TruthfulToolResult)
    assert intervention.name == "truthful_tool_result"
    assert intervention.target_step == 3


def test_an_agent_step_gets_a_resample():
    # Arrange / Act / Assert
    assert choose_intervention(_step(2, "agent")).name == "resample"


def test_a_user_step_gets_a_resample():
    # Arrange / Act / Assert
    assert choose_intervention(_step(2, "user")).name == "resample"


def test_an_evaluator_step_has_no_intervention():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="evaluator"):
        choose_intervention(_step(2, "evaluator"))


def test_the_truthful_fix_carries_the_truth_provider_it_was_given():
    # Arrange
    truth = {"content": "the real answer"}

    # Act
    intervention = choose_intervention(_step(3, "tool"), truth_for=lambda _step: truth)

    # Assert
    assert intervention.apply(_step(3, "tool"), {"content": "wrong"})["content"] == (
        "the real answer"
    )


# ---- run_blame ----


def test_blames_the_shortlisted_step_whose_effect_clears_delta():
    # Arrange: step 5 is the real cause, 1 and 3 are innocent
    executor = ScriptedExecutor(treated={5: 0.95, 1: 0.05, 3: 0.05})

    # Act
    result = _blame(_verdict([5, 1, 3]), executor)

    # Assert
    assert result.blamed_step == 5


def test_blames_the_earliest_clearing_step_not_the_largest_effect():
    # Arrange: step 3 clears delta, step 7 clears it by more
    executor = ScriptedExecutor(treated={3: 0.80, 7: 0.99, 5: 0.05})

    # Act
    result = _blame(_verdict([7, 3, 5]), executor)

    # Assert
    assert result.blamed_step == 3


def test_blames_nothing_when_no_suspect_clears_delta():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.05, 3: 0.05, 5: 0.05})

    # Act
    result = _blame(_verdict([1, 3, 5]), executor)

    # Assert
    assert result.blamed_step is None
    assert result.estimate is not None


def test_a_judge_that_could_not_answer_costs_no_reruns_and_blames_nothing():
    # Arrange
    executor = ScriptedExecutor()

    # Act
    result = _blame(_verdict([], calls=2, failed=True), executor)

    # Assert
    assert result.blamed_step is None
    assert result.reruns == ()
    assert executor.requests == []
    assert result.judge_calls == 2
    assert result.replay_calls == 0


def test_only_the_top_m_suspects_are_tested():
    # Arrange
    executor = ScriptedExecutor(treated={5: 0.95})

    # Act
    result = _blame(_verdict([5, 1, 3, 7, 9]), executor, top_m=2)

    # Assert
    assert result.shortlist == (5, 1)
    assert {request.fork_step for request in executor.requests if request.arm == "treated"} == {
        5, 1
    }


def test_the_control_is_shared_and_forked_at_the_earliest_tested_step():
    # Arrange
    executor = ScriptedExecutor(treated={5: 0.95, 1: 0.05, 3: 0.05})

    # Act
    result = _blame(_verdict([5, 1, 3]), executor)

    # Assert
    control_steps = {r.fork_step for r in executor.requests if r.arm == "control"}
    assert control_steps == {1}
    assert result.estimate is not None
    assert result.estimate.control_fork_step == 1


def test_the_control_arm_applies_no_intervention():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    _blame(_verdict([1]), executor)

    # Assert
    controls = [r for r in executor.requests if r.arm == "control"]
    assert controls and all(r.intervention.name == "noop" for r in controls)


def test_the_no_control_ablation_runs_no_control_arm_at_all():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    result = _blame(_verdict([1]), executor, control_mode="none")

    # Assert
    assert all(request.arm == "treated" for request in executor.requests)
    assert result.estimate is not None
    assert result.estimate.control_reruns == 0


def test_every_rerun_is_recorded_with_its_own_id_and_seed():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    result = _blame(_verdict([1]), executor)

    # Assert
    ids = [record.rerun_id for record in result.reruns]
    assert len(ids) == len(set(ids)) == len(executor.requests)
    assert all(record.calls == CALLS_PER_RERUN for record in result.reruns)


def test_rerun_ids_are_deterministic_so_a_resume_finds_the_same_forks():
    # Arrange
    first = ScriptedExecutor(treated={1: 0.95, 3: 0.05})
    second = ScriptedExecutor(treated={1: 0.95, 3: 0.05})

    # Act
    left = _blame(_verdict([1, 3]), first)
    right = _blame(_verdict([1, 3]), second)

    # Assert
    assert [r.rerun_id for r in left.reruns] == [r.rerun_id for r in right.reruns]
    assert left.blamed_step == right.blamed_step


def test_the_prefix_mode_reaches_every_fork():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    _blame(_verdict([1]), executor, prefix_tools="rerun_live", unsafe_positional=True)

    # Assert
    assert all(r.prefix_tools == "rerun_live" for r in executor.requests)
    assert all(r.unsafe_positional for r in executor.requests)


def test_a_suspect_that_cannot_be_intervened_on_is_recorded_not_tested():
    # Arrange: step 20 is beyond the run
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    result = _blame(_verdict([1, 20]), executor)

    # Assert
    assert result.shortlist == (1, 20)
    assert result.tested_steps == (1,)
    assert any("20" in note for note in result.untestable)


def test_the_cost_is_split_between_judge_and_replay_calls():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    result = _blame(_verdict([1], calls=3), executor)

    # Assert
    assert result.judge_calls == 3
    assert result.replay_calls == len(result.reruns) * CALLS_PER_RERUN
    assert result.total_calls == result.judge_calls + result.replay_calls


def test_the_result_carries_the_interventions_that_were_applied():
    # Arrange: step 1 is a tool step, step 2 an agent step
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    result = _blame(_verdict([1, 2]), executor)

    # Assert
    assert result.interventions[1] == "truthful_tool_result"
    assert result.interventions[2] == "resample"


def test_the_result_keeps_the_judge_ranking_and_rationale():
    # Arrange
    executor = ScriptedExecutor(treated={1: 0.95})

    # Act
    result = _blame(_verdict([1, 3, 5]), executor)

    # Assert
    assert [entry.step for entry in result.judge.ranking] == [1, 3, 5]
    assert result.judge.rationale == "because"


def test_an_empty_shortlist_from_a_judge_that_answered_is_still_no_reruns():
    # Arrange
    verdict = JudgeVerdict(
        item_id="item-1", protocol="all_at_once", decisive_step=None,
        ranking=(), rationale="", calls=1,
    )
    executor = ScriptedExecutor()

    # Act
    result = _blame(verdict, executor)

    # Assert
    assert result.blamed_step is None
    assert executor.requests == []


# ---- concurrency is throughput only ----


def test_concurrent_draws_give_the_same_result_as_serial_ones():
    # Arrange
    serial = ScriptedExecutor(treated={5: 0.95, 1: 0.05, 3: 0.05})
    parallel = ScriptedExecutor(treated={5: 0.95, 1: 0.05, 3: 0.05})

    # Act
    left = _blame(_verdict([5, 1, 3]), serial, concurrency=1)
    right = _blame(_verdict([5, 1, 3]), parallel, concurrency=8)

    # Assert
    assert left.blamed_step == right.blamed_step
    assert [r.rerun_id for r in left.reruns] == [r.rerun_id for r in right.reruns]
    assert [r.passed for r in left.reruns] == [r.passed for r in right.reruns]


def test_records_come_back_in_draw_order_whatever_order_they_finished():
    # Arrange: an executor that finishes later draws first
    import time

    class Jittered(ScriptedExecutor):
        def run(self, request: RerunRequest) -> RerunOutcome:
            time.sleep(0.01 if request.seed % 2 else 0.0)
            return super().run(request)

    # Act
    result = _blame(_verdict([1]), Jittered(treated={1: 0.95}), concurrency=4)

    # Assert
    seeds = [r.seed for r in result.reruns if r.arm == "treated"]
    assert seeds == sorted(seeds, key=lambda s: [r.seed for r in result.reruns].index(s))


def test_a_failing_draw_still_surfaces_when_draws_run_concurrently():
    # Arrange
    class Exploding(ScriptedExecutor):
        def run(self, request: RerunRequest) -> RerunOutcome:
            if request.seed % 3 == 0:
                raise RuntimeError("fork died on infrastructure")
            return super().run(request)

    # Act / Assert
    with pytest.raises(RuntimeError, match="infrastructure"):
        _blame(_verdict([1]), Exploding(treated={1: 0.95}), concurrency=4)


def test_a_non_positive_concurrency_is_refused():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="concurrency"):
        BlameConfig(concurrency=0)
