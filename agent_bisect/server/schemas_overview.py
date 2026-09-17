"""Overview page response models (page group 1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agent_bisect.server.schemas_benchmark import CiValue, Method
from agent_bisect.server.schemas_runs import RunSummary


class HeadlineResult(BaseModel):
    """Bisect vs. the best judge, each with its own 95% CI, plus the gap
    between them with its own paired-bootstrap CI (never a Newcombe interval
    over the two accuracies -- they're measured on the same dataset)."""

    model_config = ConfigDict(frozen=True)

    bisect: CiValue
    best_judge: CiValue
    best_judge_method: Method
    gap: CiValue


class Kpis(BaseModel):
    model_config = ConfigDict(frozen=True)

    runs_recorded: int
    failures_diagnosed: int
    calls_spent: int
    # `None`, never a fabricated number -- see `MethodResult.mean_cost_usd`.
    cost_per_diagnosis_usd: float | None
    # `None` only when nothing has been diagnosed yet (division by zero,
    # not a real quantity). This project's real cost signal either way.
    cost_per_diagnosis_calls: float | None


class RecallPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    m: int
    recall: float


class RecallProvenance(BaseModel):
    """recall@m beyond `measured_to_m` was never confirmed by a re-run --
    it is the judge's ranking alone (does its top-m contain the planted
    step). Mirrors `bench.evaluate.build_report`'s own `recall_provenance`
    document so the UI can label the unmeasured tail rather than imply it
    was tested."""

    model_config = ConfigDict(frozen=True)

    measured_to_m: int
    beyond_is_judge_ranking_only: bool
    note: str


class CostAccuracyPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Method
    # `None`, never a fabricated number -- see `MethodResult.mean_cost_usd`.
    mean_cost_usd: float | None
    mean_calls: float
    accuracy: float


class OverviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: HeadlineResult
    kpis: Kpis
    recall_at_m: tuple[RecallPoint, ...]
    recall_provenance: RecallProvenance
    cost_vs_accuracy: tuple[CostAccuracyPoint, ...]
    hero_run: RunSummary
