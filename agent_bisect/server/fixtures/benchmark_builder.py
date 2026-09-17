"""Aggregates `BenchmarkSummary` from the generated `RunPlan`s.

Every number here is computed from the runs, never typed in: correctness is
"does this method's guessed step equal the planted step", accuracy is a
genuine Wilson interval over that boolean (`attribution.estimate.wilson_interval`),
and the flaky-world ablation re-runs `attribution.estimate.estimate_run`
against a second, drift-perturbed `ScriptedSampler` rather than faking a
worse number.
"""

from __future__ import annotations

from collections import defaultdict

from agent_bisect.attribution.estimate import (
    SequentialConfig,
    estimate_run,
    newcombe_diff_interval,
    wilson_interval,
)
from agent_bisect.attribution.fakes import FakeRunSpec, ScriptedSampler
from agent_bisect.server.fixtures.run_builder import CALLS_PER_RERUN, COST_PER_CALL_USD, RunPlan
from agent_bisect.server.schemas_benchmark import (
    AblationArm,
    BenchmarkSummary,
    CiValue,
    CostBucket,
    FlakyAblation,
    HeatmapCell,
    Method,
    MethodResult,
    PositionAccuracy,
    SankeyFlow,
    SankeyLabel,
)
from agent_bisect.server.schemas_runs import FaultType, JudgePanel, PositionBucket

_METHODS: tuple[Method, ...] = (
    "bisect",
    "judge_all_at_once",
    "judge_step_by_step",
    "rerun_live",
    "no_control",
)
_JUDGE_METHODS = ("judge_all_at_once", "judge_step_by_step")
_DRIFT = 0.08
_COST_BUCKET_WIDTH = 400


def _labelled(plans: tuple[RunPlan, ...]) -> tuple[RunPlan, ...]:
    return tuple(p for p in plans if p.fault_type is not None and p.spec is not None)


def _position_bucket(planted_step: int, n_steps: int) -> PositionBucket:
    fraction = planted_step / n_steps
    if fraction <= 1 / 3:
        return "early"
    if fraction <= 2 / 3:
        return "middle"
    return "late"


def _guess_for(plan: RunPlan, method: Method) -> int | None:
    if method == "bisect":
        return plan.estimate_shared.blamed_step if plan.estimate_shared else None
    if method == "no_control":
        return plan.estimate_no_control.blamed_step if plan.estimate_no_control else None
    if method == "rerun_live":
        return plan.estimate_per_step.blamed_step if plan.estimate_per_step else None
    return None  # judge methods handled by the caller, which has the judge panel


def _ci(successes: int, n: int) -> CiValue:
    interval = wilson_interval(successes, max(n, 1))
    return CiValue(
        value=round(successes / n, 4) if n else 0.0,
        ci_low=round(interval.low, 4),
        ci_high=round(interval.high, 4),
    )


def _cost_for(plan: RunPlan, method: Method) -> tuple[float, int]:
    if method == "judge_all_at_once":
        return 0.03, 1
    if method == "judge_step_by_step":
        return 0.03 * plan.n_steps, plan.n_steps
    estimate = {
        "bisect": plan.estimate_shared,
        "no_control": plan.estimate_no_control,
        "rerun_live": plan.estimate_per_step,
    }[method]
    calls = estimate.sampler_calls * CALLS_PER_RERUN if estimate else 0
    return calls * COST_PER_CALL_USD, calls


def _judge_guess(panel: JudgePanel | None, method: Method) -> int | None:
    if panel is None:
        return None
    ranking = panel.all_at_once if method == "judge_all_at_once" else panel.step_by_step
    return ranking[0].step if ranking else None


def _guess(plan: RunPlan, method: Method, judge_by_run: dict[str, JudgePanel | None]) -> int | None:
    if method in _JUDGE_METHODS:
        return _judge_guess(judge_by_run.get(plan.run_id), method)
    return _guess_for(plan, method)


def build_methods(
    plans: tuple[RunPlan, ...], judge_by_run: dict[str, JudgePanel | None]
) -> tuple[MethodResult, ...]:
    labelled = _labelled(plans)
    results = []
    for method in _METHODS:
        correct = 0
        costs: list[float] = []
        calls_list: list[int] = []
        for plan in labelled:
            guess = _guess(plan, method, judge_by_run)
            if guess == plan.planted_step:
                correct += 1
            cost, calls = _cost_for(plan, method)
            costs.append(cost)
            calls_list.append(calls)
        n = len(labelled)
        results.append(
            MethodResult(
                method=method,
                accuracy=_ci(correct, n),
                mean_cost_usd=round(sum(costs) / n, 4) if n else 0.0,
                mean_calls=round(sum(calls_list) / n, 2) if n else 0.0,
            )
        )
    return tuple(results)


def build_heatmap(
    plans: tuple[RunPlan, ...], judge_by_run: dict[str, JudgePanel | None]
) -> tuple[HeatmapCell, ...]:
    labelled = _labelled(plans)
    tally: dict[tuple[FaultType, Method], list[int]] = defaultdict(lambda: [0, 0])
    for plan in labelled:
        assert plan.fault_type is not None  # guaranteed by `_labelled`
        for method in _METHODS:
            guess = _guess(plan, method, judge_by_run)
            key = (plan.fault_type, method)
            tally[key][1] += 1
            if guess == plan.planted_step:
                tally[key][0] += 1
    cells = []
    for (fault_type, method), (correct, n) in sorted(tally.items()):
        cells.append(
            HeatmapCell(
                fault_type=fault_type,
                method=method,
                accuracy=round(correct / n, 4) if n else 0.0,
                n=n,
            )
        )
    return tuple(cells)


def build_by_position(plans: tuple[RunPlan, ...]) -> tuple[PositionAccuracy, ...]:
    labelled = _labelled(plans)
    tally: dict[tuple[Method, PositionBucket], list[int]] = defaultdict(lambda: [0, 0])
    for plan in labelled:
        assert plan.planted_step is not None  # guaranteed by `_labelled`
        bucket = _position_bucket(plan.planted_step, plan.n_steps)
        guess = _guess_for(plan, "bisect")
        key: tuple[Method, PositionBucket] = ("bisect", bucket)
        tally[key][1] += 1
        if guess == plan.planted_step:
            tally[key][0] += 1
    rows = []
    for (method, bucket), (correct, n) in sorted(tally.items()):
        rows.append(
            PositionAccuracy(
                method=method, position=bucket, accuracy=round(correct / n, 4) if n else 0.0, n=n
            )
        )
    return tuple(rows)


def build_sankey(plans: tuple[RunPlan, ...]) -> tuple[SankeyFlow, ...]:
    labelled = _labelled(plans)
    tally: dict[tuple[FaultType, SankeyLabel], int] = defaultdict(int)
    for plan in labelled:
        assert plan.fault_type is not None and plan.planted_step is not None
        guess = _guess_for(plan, "bisect")
        label: SankeyLabel
        if guess is None:
            label = "none"
        elif guess == plan.planted_step:
            label = "exact"
        elif guess < plan.planted_step:
            label = "earlier"
        else:
            label = "later"
        tally[(plan.fault_type, label)] += 1
    return tuple(
        SankeyFlow(fault_type=fault_type, label=label, count=count)
        for (fault_type, label), count in sorted(tally.items())
    )


def build_flaky_ablation(plans: tuple[RunPlan, ...]) -> FlakyAblation:
    labelled = _labelled(plans)
    config = SequentialConfig()
    snap_correct = 0
    no_snap_correct = 0
    n = len(labelled)
    for plan in labelled:
        spec = plan.spec
        assert spec is not None
        snap_correct += int(_guess_for(plan, "bisect") == plan.planted_step)
        drifted = FakeRunSpec(
            run_id=spec.run_id,
            planted_step=spec.planted_step,
            control_prob=min(1.0, spec.control_prob + _DRIFT),
            treated_probs=tuple(min(1.0, p + _DRIFT) for p in spec.treated_probs),
        )
        estimate = estimate_run(
            tuple(drifted.steps),
            ScriptedSampler(drifted),
            config,
            control_mode="shared",
            seed=plan.seed,
        )
        no_snap_correct += int(estimate.blamed_step == plan.planted_step)

    snap_ci = _ci(snap_correct, n)
    no_snap_ci = _ci(no_snap_correct, n)
    diff = newcombe_diff_interval(snap_correct, max(n, 1), no_snap_correct, max(n, 1))
    return FlakyAblation(
        arms=(
            AblationArm(name="snapshot", accuracy=snap_ci),
            AblationArm(name="no_snapshot", accuracy=no_snap_ci),
        ),
        difference=CiValue(
            value=round(snap_ci.value - no_snap_ci.value, 4),
            ci_low=round(diff.low, 4),
            ci_high=round(diff.high, 4),
        ),
    )


def build_cost_histogram(plans: tuple[RunPlan, ...]) -> tuple[CostBucket, ...]:
    labelled = _labelled(plans)
    buckets: dict[int, int] = defaultdict(int)
    for plan in labelled:
        _, calls = _cost_for(plan, "bisect")
        bucket = calls // _COST_BUCKET_WIDTH
        buckets[bucket] += 1
    return tuple(
        CostBucket(
            calls_low=int(bucket * _COST_BUCKET_WIDTH),
            calls_high=int((bucket + 1) * _COST_BUCKET_WIDTH),
            count=count,
        )
        for bucket, count in sorted(buckets.items())
    )


def build_benchmark(
    plans: tuple[RunPlan, ...], judge_by_run: dict[str, JudgePanel | None]
) -> BenchmarkSummary:
    return BenchmarkSummary(
        methods=build_methods(plans, judge_by_run),
        heatmap=build_heatmap(plans, judge_by_run),
        by_position=build_by_position(plans),
        sankey=build_sankey(plans),
        flaky_ablation=build_flaky_ablation(plans),
        cost_histogram=build_cost_histogram(plans),
    )
