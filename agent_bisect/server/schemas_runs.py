"""Run list / run detail response models (page groups 2 and 3).

`StepEffectView`/`RunEstimateView` mirror `agent_bisect.attribution.estimate`'s
`StepEffect`/`RunEstimate` as plain, JSON-serializable DTOs — the server never
re-derives statistics, it only reshapes what `estimate.py` already computed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["pass", "fail"]
# A run with no outcome row yet is still being recorded -- `outcome`/`reward`
# are `None` while `status == "recording"`, never a fabricated "fail"/`0.0`.
RunStatus = Literal["recording", "complete"]
FaultType = Literal["wrong_value", "missing_field", "stale_record", "tool_error"]
Actor = Literal["agent", "user", "tool"]
PositionBucket = Literal["early", "middle", "late"]


class SparkPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_idx: int
    actor: Actor
    # `None`, never a made-up `0`, when the recorded step didn't carry this
    # telemetry -- real_repository.py leaves it unset rather than "0ms/0 tok".
    latency_ms: int | None
    tokens: int | None


class BlameCell(BaseModel):
    """One cell of a run's blame stripe. `effect` is `None` for an untested step."""

    model_config = ConfigDict(frozen=True)

    step_idx: int
    effect: float | None
    tested: bool


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    domain: str
    task_id: str
    model: str
    status: RunStatus
    # `None` while `status == "recording"` -- never a fabricated "fail".
    outcome: Outcome | None
    n_steps: int
    decisive_step: int | None
    fault_type: FaultType | None
    planted_step: int | None
    # `None`, never `0`/`0.0`, when per-run cost isn't attributable yet (real
    # mode: the ledger has no run_id column until P1b). Fixture mode always
    # has a real number here.
    cost_usd: float | None
    calls: int | None
    sparkline: tuple[SparkPoint, ...]
    blame_stripe: tuple[BlameCell, ...]


class RunListPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    runs: tuple[RunSummary, ...]


class StepView(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_idx: int
    actor: Actor
    tool_name: str | None
    text: str
    from_tape: bool
    state_changed: bool


class StepPayload(BaseModel):
    """The step inspector's detail for one step: messages plus tool call/result."""

    model_config = ConfigDict(frozen=True)

    step_idx: int
    messages: tuple[dict[str, str], ...]
    tool_args: dict[str, str] | None
    tool_result: dict[str, str] | None


class DiffEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    kind: Literal["added", "removed", "changed"]
    before: str | None
    after: str | None


class InterventionDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_idx: int
    original_tool_result: dict[str, str]
    replaced_tool_result: dict[str, str]


class StateDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_idx: int
    entries: tuple[DiffEntry, ...]


class ArmResultView(BaseModel):
    model_config = ConfigDict(frozen=True)

    successes: int
    n: int


class StepEffectView(BaseModel):
    """DTO for `attribution.estimate.StepEffect`."""

    model_config = ConfigDict(frozen=True)

    step: int
    treated: ArmResultView
    control: ArmResultView | None
    effect: float
    ci_low: float
    ci_high: float
    n_batches: int
    stop_reason: Literal["blameworthy", "cleared", "max_n"]


class RunEstimateView(BaseModel):
    """DTO for `attribution.estimate.RunEstimate`."""

    model_config = ConfigDict(frozen=True)

    step_effects: tuple[StepEffectView, ...]
    blamed_step: int | None
    control_mode: Literal["shared", "per_step", "none"]
    control_fork_step: int | None
    treated_reruns: int
    control_reruns: int
    sampler_calls: int


class RerunRow(BaseModel):
    """One individual treated/control re-run in the matrix."""

    model_config = ConfigDict(frozen=True)

    rerun_id: str
    arm: Literal["treated", "control"]
    step: int
    seed: int
    passed: bool
    n_steps: int
    calls: int


class JudgeRankEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    step: int
    rank: int
    score: float
    rationale: str


class JudgePanel(BaseModel):
    model_config = ConfigDict(frozen=True)

    all_at_once: tuple[JudgeRankEntry, ...]
    step_by_step: tuple[JudgeRankEntry, ...]


class RunDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    domain: str
    task_id: str
    agent_model: str
    user_model: str
    seed: int | None
    tau2_commit: str
    created_at: str
    status: RunStatus
    # Both `None` while `status == "recording"` -- never a fabricated
    # "fail"/`0.0`.
    outcome: Outcome | None
    reward: float | None
    steps: tuple[StepView, ...]
    planted_step: int | None
    fault_type: FaultType | None
    estimate: RunEstimateView | None
    judge: JudgePanel | None


class RerunPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    reruns: tuple[RerunRow, ...]
