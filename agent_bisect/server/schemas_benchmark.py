"""Benchmark comparison response models (page group 4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agent_bisect.server.schemas_runs import FaultType, PositionBucket

Method = Literal["bisect", "judge_all_at_once", "judge_step_by_step", "rerun_live", "no_control"]
SankeyLabel = Literal["exact", "earlier", "later", "none"]

#: `CostBucket`'s bin width, shared by the fixture builder and the real
#: repository so a bucket means the same thing regardless of `data_source`.
COST_BUCKET_WIDTH_CALLS = 400


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
    # `None`, never a fabricated number -- real mode has no per-model USD
    # price list (the NIM free tier this project evaluates against isn't
    # priced); this project's spend is measured in calls, which is real in
    # both modes.
    mean_cost_usd: float | None
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
    # `None` when no flaky-world run exists to ablate -- absent, never a
    # fabricated comparison (`bench.evaluate.build_report`'s own rule).
    # Fixture mode always has one.
    flaky_ablation: FlakyAblation | None
    cost_histogram: tuple[CostBucket, ...]
