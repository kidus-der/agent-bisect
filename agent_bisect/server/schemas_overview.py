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
    cost_per_diagnosis_usd: float


class RecallPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    m: int
    recall: float


class CostAccuracyPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Method
    mean_cost_usd: float
    accuracy: float


class OverviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: HeadlineResult
    kpis: Kpis
    recall_at_m: tuple[RecallPoint, ...]
    cost_vs_accuracy: tuple[CostAccuracyPoint, ...]
    hero_run: RunSummary
