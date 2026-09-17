"""Ties every fixture generator module together into one `FixtureBundle`.

`build_bundle(seed)` is pure and deterministic: two calls with the same
seed produce byte-identical `model_dump_json()` output for every DTO it
returns (`tests/server/test_fixtures.py::test_determinism`).
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_bisect.server.fixtures.benchmark_builder import build_benchmark
from agent_bisect.server.fixtures.catalog import BRIEF_RUN_ID
from agent_bisect.server.fixtures.dataset import build_all_plans, build_dataset_entries
from agent_bisect.server.fixtures.judge import build_judge_panel
from agent_bisect.server.fixtures.pr_checks import build_pr_checks
from agent_bisect.server.fixtures.run_builder import RunPlan
from agent_bisect.server.fixtures.serialize import to_run_summary
from agent_bisect.server.fixtures.synth import seeded_rng
from agent_bisect.server.schemas_benchmark import BenchmarkSummary, DatasetEntry
from agent_bisect.server.schemas_overview import (
    CostAccuracyPoint,
    HeadlineResult,
    Kpis,
    OverviewPayload,
    RecallPoint,
)
from agent_bisect.server.schemas_pr import PrCheckDetail
from agent_bisect.server.schemas_runs import JudgePanel, RunSummary

_RECALL_MAX_M = 10


@dataclass(frozen=True, slots=True)
class FixtureBundle:
    seed: int
    plans: tuple[RunPlan, ...]
    judge_by_run: dict[str, JudgePanel | None]
    run_summaries: tuple[RunSummary, ...]
    dataset_entries: tuple[DatasetEntry, ...]
    pr_checks: tuple[PrCheckDetail, ...]
    benchmark: BenchmarkSummary
    overview: OverviewPayload

    def plan_by_id(self, run_id: str) -> RunPlan:
        for plan in self.plans:
            if plan.run_id == run_id:
                return plan
        raise KeyError(run_id)


def _recall_at_m(plans: tuple[RunPlan, ...], judge_by_run: dict[str, JudgePanel | None]):
    labelled = [p for p in plans if p.fault_type is not None and p.spec is not None]
    points = []
    for m in range(1, _RECALL_MAX_M + 1):
        hits = 0
        for plan in labelled:
            panel = judge_by_run.get(plan.run_id)
            ranking = panel.all_at_once if panel else ()
            top_m = {entry.step for entry in ranking[:m]}
            if plan.planted_step in top_m:
                hits += 1
        recall = hits / len(labelled) if labelled else 0.0
        points.append(RecallPoint(m=m, recall=round(recall, 4)))
    return tuple(points)


def _build_overview(
    plans, judge_by_run, run_summaries, benchmark, hero_run_id: str
) -> OverviewPayload:
    methods_by_name = {m.method: m for m in benchmark.methods}
    bisect = methods_by_name["bisect"]
    judge_methods = [
        methods_by_name["judge_all_at_once"],
        methods_by_name["judge_step_by_step"],
    ]
    best_judge = max(judge_methods, key=lambda m: m.accuracy.value)
    # A recording run hasn't failed -- it just hasn't finished -- so it's
    # excluded from "failures" the same way its `outcome` is masked at
    # serialization (fixtures.serialize).
    failing = [p for p in plans if p.status == "complete" and not p.passed]
    labelled = [p for p in plans if p.fault_type is not None]
    total_calls = sum(s.calls for s in run_summaries)
    total_cost = sum(s.cost_usd for s in run_summaries)
    hero = next(s for s in run_summaries if s.run_id == hero_run_id)
    return OverviewPayload(
        headline=HeadlineResult(
            bisect=bisect.accuracy,
            best_judge=best_judge.accuracy,
            best_judge_method=best_judge.method,
        ),
        kpis=Kpis(
            runs_recorded=len(plans),
            failures_diagnosed=len(labelled),
            calls_spent=total_calls,
            cost_per_diagnosis_usd=round(total_cost / len(failing), 4) if failing else 0.0,
        ),
        recall_at_m=_recall_at_m(plans, judge_by_run),
        cost_vs_accuracy=tuple(
            CostAccuracyPoint(
                method=m.method, mean_cost_usd=m.mean_cost_usd, accuracy=m.accuracy.value
            )
            for m in benchmark.methods
        ),
        hero_run=hero,
    )


def build_bundle(seed: int) -> FixtureBundle:
    plans = build_all_plans(seed)
    judge_by_run: dict[str, JudgePanel | None] = {}
    for plan in plans:
        rng = seeded_rng(seed, plan.run_id, "judge")
        judge_by_run[plan.run_id] = build_judge_panel(rng, plan)

    run_summaries = tuple(to_run_summary(plan) for plan in plans)
    benchmark = build_benchmark(plans, judge_by_run)
    dataset_entries = build_dataset_entries(plans)
    pr_checks = build_pr_checks(seed)
    overview = _build_overview(plans, judge_by_run, run_summaries, benchmark, BRIEF_RUN_ID)

    return FixtureBundle(
        seed=seed,
        plans=plans,
        judge_by_run=judge_by_run,
        run_summaries=run_summaries,
        dataset_entries=dataset_entries,
        pr_checks=pr_checks,
        benchmark=benchmark,
        overview=overview,
    )
