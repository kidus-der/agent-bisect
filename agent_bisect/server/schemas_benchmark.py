"""Benchmark comparison response models (page group 4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agent_bisect.server.schemas_runs import FaultType, PositionBucket

Method = Literal["bisect", "judge_all_at_once", "judge_step_by_step", "rerun_live", "no_control"]
SankeyLabel = Literal["exact", "earlier", "later", "none"]


class CiValue(BaseModel):
    """A point estimate with its 95% bootstrap CI. An estimate never appears without one."""

    model_config = ConfigDict(frozen=True)

    value: float
    ci_low: float
    ci_high: float


class MethodResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Method
    accuracy: CiValue
    mean_cost_usd: float
    mean_calls: float


class HeatmapCell(BaseModel):
    model_config = ConfigDict(frozen=True)

    fault_type: FaultType
    method: Method
    accuracy: float
    n: int


class PositionAccuracy(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Method
    position: PositionBucket
    accuracy: float
    n: int


class SankeyFlow(BaseModel):
    model_config = ConfigDict(frozen=True)

    fault_type: FaultType
    label: SankeyLabel
    count: int


class AblationArm(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Literal["snapshot", "no_snapshot"]
    accuracy: CiValue


class FlakyAblation(BaseModel):
    model_config = ConfigDict(frozen=True)

    arms: tuple[AblationArm, AblationArm]
    difference: CiValue


class CostBucket(BaseModel):
    model_config = ConfigDict(frozen=True)

    calls_low: int
    calls_high: int
    count: int


class DatasetEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    domain: str
    task_id: str
    fault_type: FaultType
    planted_step: int
    position_bucket: PositionBucket
    split: Literal["dev", "test"]
    base_pass_rate: float
    faulted_pass_rate: float


class DatasetPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[DatasetEntry, ...]


class BenchmarkSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    methods: tuple[MethodResult, ...]
    heatmap: tuple[HeatmapCell, ...]
    by_position: tuple[PositionAccuracy, ...]
    sankey: tuple[SankeyFlow, ...]
    flaky_ablation: FlakyAblation
    cost_histogram: tuple[CostBucket, ...]
