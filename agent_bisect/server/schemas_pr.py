"""PR-check response models (page group 6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agent_bisect.server.schemas_benchmark import CiValue


class ScenarioRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario: str
    base_pass_rate: float
    head_pass_rate: float
    n: int


class PrCheckSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: str
    pr_number: int
    title: str
    is_regression: bool
    base_pass_rate: float
    head_pass_rate: float
    p_value: float


class PrCheckDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: str
    pr_number: int
    title: str
    is_regression: bool
    base_pass_rate: CiValue
    head_pass_rate: CiValue
    p_value: float
    decisive_step_base: int | None
    decisive_step_head: int | None
    scenarios: tuple[ScenarioRow, ...]
    comment_markdown: str
