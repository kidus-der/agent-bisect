"""What a finished pass reports about itself, and what it refuses to hide.

The rows here are what `build_report` puts in the report's scope section:
the items that could not be evaluated and the items whose control arm did
not reproduce their recorded failure. Both are reported, never dropped,
so both are pinned by a test.
"""

from __future__ import annotations

from pathlib import Path

from agent_bisect.bench.baselines import BaselineConfig, MethodOutcome
from agent_bisect.bench.eval_run import (
    ControlFlag,
    EvaluationRun,
    ItemFailure,
    _report_progress,
    evaluate_dataset,
)
from agent_bisect.bench.manifest import DatasetItem


def _outcome(method: str = "bisect", **fields) -> MethodOutcome:
    base = dict(
        item_id="item-0", run_id="r0", method=method, predicted_step=2,
        ranking=(2,), shortlist=(2,), judge_calls=1, replay_calls=10,
        reruns=8, control_reruns=16, parse_failed=False,
    )
    return MethodOutcome(**{**base, **fields})  # type: ignore[arg-type]


def _item(index: int) -> DatasetItem:
    return DatasetItem(
        item_id=f"item-{index}", domain="airline", task_id=str(index), split="dev",
        base_run_id=f"b{index}", base_pass_rate=1.0, run_id=f"r{index}",
        faulted_pass_rate=0.0, planted_step=2, position_bucket="middle",
        fault_type="wrong_value", mutation={}, oracle={}, intervention={},
        seeds=[1], n_reruns=4,
    )


def test_the_failure_rows_name_every_item_that_got_no_verdict():
    # Arrange
    run = EvaluationRun(
        failures=[ItemFailure(item_id="item-0", run_id="r0", reason="504 from the judge")]
    )

    # Act
    rows = run.failure_rows()

    # Assert
    assert run.n_failed_items == 1
    assert rows == [{"item_id": "item-0", "run_id": "r0", "reason": "504 from the judge"}]


def test_a_flagged_control_carries_both_rates_and_says_what_they_mean():
    # Arrange
    run = EvaluationRun(
        control_flags=[
            ControlFlag(
                item_id="item-0", run_id="r0", method="bisect",
                control_pass_rate=0.5, faulted_pass_rate=0.0,
            )
        ]
    )

    # Act
    rows = run.flag_rows()

    # Assert
    assert run.n_control_flags == 1
    assert rows[0]["control_pass_rate"] == 0.5
    assert rows[0]["faulted_pass_rate"] == 0.0
    assert "understated" in rows[0]["detail"]


def test_unguarded_calls_are_counted_for_the_bisect_arms_only():
    """`rerun_live` is allowed to drift from the recording; Bisect is not."""
    # Arrange
    class _Blame:
        unguarded_calls = 3

    run = EvaluationRun(
        outcomes=[
            _outcome(method="bisect", blame=_Blame()),
            _outcome(method="rerun_live", blame=_Blame()),
            _outcome(method="judge_all_at_once", blame=None),
        ]
    )

    # Act / Assert
    assert run.bisect_unguarded_calls == 3


def test_progress_reporting_never_takes_the_run_down(tmp_path):
    # Arrange: a runs dir that is a file, so writing the status must fail
    blocked = tmp_path / "runs"
    blocked.write_text("not a directory")

    # Act / Assert: it returns rather than raising
    _report_progress(blocked, 1, 2, EvaluationRun(), attempted=1, failed=0)


def test_a_completed_item_is_counted_once_and_its_blame_is_saved(tmp_path: Path, monkeypatch):
    """The whole worker body: judge, evaluate, persist, count. Concurrent."""
    # Arrange
    import numpy as np
    from agent_bisect.attribution.judge_view import (
        JudgeInput,
        JudgeStepView,
        JudgeVerdict,
        RankedStep,
    )
    from agent_bisect.attribution.search import RerunOutcome
    from agent_bisect.bench import eval_run as module
    from agent_bisect.bench.baselines import ItemJudgement
    from agent_bisect.core.tape import Step

    steps = tuple(
        Step(run_id="r0", step_idx=i, actor="tool" if i % 2 else "agent",
             tool_name="get_reservation" if i % 2 else None,
             state_before="s", state_after="s", state_hash="h")
        for i in range(6)
    )

    class _Reader:
        def get_steps(self, run_id: str):
            return steps

    class _Executor:
        def run(self, request):
            passed = request.arm == "treated" and request.fork_step == 2
            return RerunOutcome(
                passed=passed or bool(np.random.default_rng(request.seed).random() < 0.05),
                n_steps=6, calls=4,
            )

    def _verdict(item_id: str) -> JudgeVerdict:
        return JudgeVerdict(
            item_id=item_id, protocol="all_at_once", decisive_step=2,
            ranking=(RankedStep(step=2, rank=1, score=0.9, rationale="r"),),
            rationale="because", calls=1,
        )

    monkeypatch.setattr(
        module, "build_judge_input",
        lambda run_id, **kwargs: JudgeInput(
            item_id=kwargs["item_id"], run_id=run_id, domain="airline",
            task_description="t", policy="p",
            steps=(JudgeStepView(0, "agent", None, None, "hello"),),
        ),
    )
    monkeypatch.setattr(
        module, "judge_item",
        lambda judge_input, *a, **k: ItemJudgement(
            all_at_once=_verdict(judge_input.item_id), step_by_step=None
        ),
    )

    # Act
    run = evaluate_dataset(
        [_item(0), _item(1)],
        reader=_Reader(),  # type: ignore[arg-type]
        store=None,  # type: ignore[arg-type]
        judge_backend=None,  # type: ignore[arg-type]
        executor=_Executor(),  # type: ignore[arg-type]
        task_text=lambda domain, task_id: ("t", "p"),
        config=BaselineConfig(methods=("bisect", "judge_all_at_once")),
        seed=1,
        runs_dir=tmp_path,
        item_concurrency=2,
        max_passes=1,
        sleep=lambda _s: None,
    )

    # Assert
    assert run.complete is True
    assert run.n_failed_items == 0
    assert {outcome.item_id for outcome in run.outcomes} == {"item-0", "item-1"}
    assert list((tmp_path / "blame").glob("*.json")), "a blame result is persisted"


def test_items_are_evaluated_when_more_than_one_runs_at_a_time(tmp_path: Path):
    """The threaded route, which is the one every live run takes."""
    # Arrange
    seen: list[str] = []

    def task_text(domain: str, task_id: str) -> tuple[str, str]:
        seen.append(task_id)
        raise LookupError("the judge is not the subject of this test")

    # Act
    run = evaluate_dataset(
        [_item(0), _item(1), _item(2)],
        reader=None,  # type: ignore[arg-type]
        store=None,  # type: ignore[arg-type]
        judge_backend=None,  # type: ignore[arg-type]
        executor=None,  # type: ignore[arg-type]
        task_text=task_text,
        config=BaselineConfig(),
        seed=1,
        runs_dir=tmp_path,
        item_concurrency=3,
        max_passes=1,
        sleep=lambda _s: None,
    )

    # Assert: every item was attempted, and every one is reported as failed
    assert sorted(seen) == ["0", "1", "2"]
    assert run.n_failed_items == 3
    assert run.complete is False
