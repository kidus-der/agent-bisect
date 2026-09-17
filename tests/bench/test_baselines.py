"""Every method answers the same item from the same judge output."""

from __future__ import annotations

import numpy as np
import pytest
from agent_bisect.attribution.judge_view import (
    JudgeInput,
    JudgeStepView,
    JudgeVerdict,
    Protocol,
    RankedStep,
)
from agent_bisect.attribution.search import RerunOutcome, RerunRequest
from agent_bisect.bench.baselines import (
    EVAL_METHODS,
    BaselineConfig,
    ItemJudgement,
    evaluate_item,
    judge_item,
)
from agent_bisect.core.tape import Step


def _step(idx: int, actor: str = "tool") -> Step:
    return Step(
        run_id="run-1", step_idx=idx, actor=actor,  # type: ignore[arg-type]
        tool_name="get_reservation" if actor == "tool" else None,
        state_before="s", state_after="s", state_hash="h",
    )


STEPS = tuple(_step(idx, "tool" if idx % 2 else "agent") for idx in range(10))


def _verdict(
    steps: list[int], protocol: Protocol = "all_at_once", calls: int = 1
) -> JudgeVerdict:
    return JudgeVerdict(
        item_id="item-1",
        protocol=protocol,
        decisive_step=steps[0] if steps else None,
        ranking=tuple(
            RankedStep(step=step, rank=i + 1, score=0.9 - 0.05 * i, rationale="r")
            for i, step in enumerate(steps)
        ),
        rationale="because",
        calls=calls,
    )


class ScriptedExecutor:
    def __init__(self, treated: dict[int, float], control: float = 0.05):
        self.treated = treated
        self.control = control
        self.requests: list[RerunRequest] = []

    def run(self, request: RerunRequest) -> RerunOutcome:
        self.requests.append(request)
        probability = (
            self.control if request.arm == "control"
            else self.treated.get(request.fork_step, self.control)
        )
        return RerunOutcome(
            passed=bool(np.random.default_rng(request.seed).random() < probability),
            n_steps=12,
            calls=10,
        )


class StubBackend:
    """Returns a scripted verdict per protocol without touching a model."""

    model = "fake-judge"

    def __init__(self, all_at_once: JudgeVerdict, step_by_step: JudgeVerdict):
        self.all_at_once = all_at_once
        self.step_by_step = step_by_step
        self.asked: list[str] = []

    def ask(self, *, system: str, user: str, item_id: str, protocol: Protocol):
        """Never reached: the two tests using this backend patch the protocols."""
        raise AssertionError("the protocol functions are patched; ask must not be called")


def _judge_input() -> JudgeInput:
    return JudgeInput(
        item_id="item-1", run_id="run-1", domain="airline",
        task_description="t", policy="p",
        steps=(JudgeStepView(0, "agent", None, None, "hello"),),
    )


def _outcomes(executor, judgement, **overrides):
    config = BaselineConfig(**overrides)
    return {
        outcome.method: outcome
        for outcome in evaluate_item(
            item_id="item-1",
            run_id="run-1",
            steps=STEPS,
            judgement=judgement,
            executor=executor,
            config=config,
            seed=11,
        )
    }


def _judgement(all_steps=None, sbs_steps=None) -> ItemJudgement:
    return ItemJudgement(
        all_at_once=_verdict(all_steps if all_steps is not None else [5, 1, 3]),
        step_by_step=_verdict(
            sbs_steps if sbs_steps is not None else [7, 5], protocol="step_by_step", calls=6
        ),
    )


# ---- the method set ----


def test_all_five_preregistered_methods_are_produced():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    assert set(outcomes) == set(EVAL_METHODS)


def test_the_judge_only_methods_answer_straight_from_their_verdict():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    assert outcomes["judge_all_at_once"].predicted_step == 5
    assert outcomes["judge_step_by_step"].predicted_step == 7


def test_the_judge_only_methods_buy_no_reruns():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    for method in ("judge_all_at_once", "judge_step_by_step"):
        assert outcomes[method].replay_calls == 0
        assert outcomes[method].reruns == 0


def test_every_replay_method_uses_the_same_all_at_once_shortlist():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    shortlists = {outcomes[m].shortlist for m in ("bisect", "rerun_live", "no_control")}
    assert shortlists == {(5, 1, 3)}


def test_the_step_by_step_shortlist_never_reaches_the_replay_methods():
    # Arrange: the two protocols disagree, so a leak would be visible
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement(all_steps=[5, 1, 3], sbs_steps=[7, 9]))

    # Assert
    assert outcomes["bisect"].shortlist == (5, 1, 3)


# ---- the replay methods ----


def test_bisect_confirms_the_shortlist_by_re_running():
    # Arrange
    executor = ScriptedExecutor({5: 0.95, 1: 0.05, 3: 0.05})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    assert outcomes["bisect"].predicted_step == 5
    assert outcomes["bisect"].reruns > 0


def test_rerun_live_forks_without_snapshots_and_says_so():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    _outcomes(executor, _judgement())

    # Assert
    live = [r for r in executor.requests if r.prefix_tools == "rerun_live"]
    assert live and all(r.unsafe_positional for r in live)


def test_the_no_control_ablation_buys_no_control_arm():
    # Arrange
    executor = ScriptedExecutor({5: 0.95, 1: 0.05, 3: 0.05})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    assert outcomes["no_control"].control_reruns == 0
    assert outcomes["bisect"].control_reruns > 0


def test_the_no_control_ablation_blames_a_step_the_control_would_have_cleared():
    # Arrange: everything passes often, so treated-only looks decisive everywhere
    executor = ScriptedExecutor({5: 0.95, 1: 0.95, 3: 0.95}, control=0.95)

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    assert outcomes["no_control"].predicted_step == 1
    assert outcomes["bisect"].predicted_step is None


# ---- cost and failure ----


def test_the_judge_cost_is_attributed_to_every_method_that_used_it():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement())

    # Assert
    assert outcomes["judge_all_at_once"].judge_calls == 1
    assert outcomes["judge_step_by_step"].judge_calls == 6
    assert outcomes["bisect"].judge_calls == 1


def test_total_calls_is_judge_plus_replay():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcome = _outcomes(executor, _judgement())["bisect"]

    # Assert
    assert outcome.total_calls == outcome.judge_calls + outcome.replay_calls


def test_a_judge_parse_failure_makes_every_method_predict_nothing():
    # Arrange
    failed = JudgeVerdict(
        item_id="item-1", protocol="all_at_once", decisive_step=None, ranking=(),
        rationale="", calls=2, parse_failed=True, failure_reason="no JSON object",
    )
    judgement = ItemJudgement(all_at_once=failed, step_by_step=failed)
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, judgement)

    # Assert
    assert all(outcome.predicted_step is None for outcome in outcomes.values())
    assert outcomes["bisect"].parse_failed is True
    assert executor.requests == []


def test_the_ranking_is_carried_for_recall_at_m():
    # Arrange
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, _judgement(all_steps=[5, 1, 3, 7, 9]))

    # Assert
    assert outcomes["judge_all_at_once"].ranking == (5, 1, 3, 7, 9)


def test_a_missing_step_by_step_verdict_is_allowed_and_reported_as_a_non_answer():
    # Arrange
    judgement = ItemJudgement(all_at_once=_verdict([5, 1, 3]), step_by_step=None)
    executor = ScriptedExecutor({5: 0.95})

    # Act
    outcomes = _outcomes(executor, judgement)

    # Assert
    assert outcomes["judge_step_by_step"].predicted_step is None
    assert outcomes["judge_step_by_step"].ranking == ()


# ---- judge_item ----


def test_judge_item_runs_both_protocols_once_each(monkeypatch):
    # Arrange
    from agent_bisect.bench import baselines

    calls: list[str] = []
    monkeypatch.setattr(
        baselines, "judge_all_at_once",
        lambda *a, **k: (calls.append("all"), _verdict([5]))[1],
    )
    monkeypatch.setattr(
        baselines, "judge_step_by_step",
        lambda *a, **k: (calls.append("sbs"), _verdict([7], "step_by_step"))[1],
    )

    # Act
    judgement = judge_item(
        _judge_input(), StubBackend(_verdict([5]), _verdict([7], "step_by_step"))
    )

    # Assert
    assert calls == ["all", "sbs"]
    assert judgement.all_at_once.decisive_step == 5
    assert judgement.step_by_step is not None


def test_judge_item_can_skip_the_expensive_protocol(monkeypatch):
    # Arrange
    from agent_bisect.bench import baselines

    monkeypatch.setattr(baselines, "judge_all_at_once", lambda *a, **k: _verdict([5]))
    monkeypatch.setattr(
        baselines, "judge_step_by_step",
        lambda *a, **k: pytest.fail("step-by-step must not run when it was not asked for"),
    )

    # Act
    judgement = judge_item(
        _judge_input(), StubBackend(_verdict([5]), _verdict([7])), step_by_step=False
    )

    # Assert
    assert judgement.step_by_step is None
