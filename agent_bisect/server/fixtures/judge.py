"""Synthetic judge rankings with imperfect recall, for `RunPlan`s that have a spec.

Both protocols (all-at-once, step-by-step) rank tool steps by their true
effect, with an independent chance of missing the actual culprit -- the
`recall@m` curve on the Overview page is only interesting if some fixture
runs' judges genuinely miss.
"""

from __future__ import annotations

from agent_bisect.attribution.fakes import FakeRunSpec
from agent_bisect.server.fixtures.run_builder import RunPlan
from agent_bisect.server.schemas_runs import JudgePanel, JudgeRankEntry

_MAX_CANDIDATES = 5
_MISS_PROB_ALL_AT_ONCE = 0.22
_MISS_PROB_STEP_BY_STEP = 0.12


def _rank(rng, spec: FakeRunSpec, tool_steps: tuple[int, ...], miss_prob: float, tag: str):
    candidates = sorted(tool_steps, key=lambda step: -spec.true_effect(step))
    candidates = list(candidates[: min(_MAX_CANDIDATES, len(candidates))])
    if rng.random() < miss_prob and spec.planted_step in candidates:
        candidates.remove(spec.planted_step)
        remaining = [step for step in tool_steps if step not in candidates]
        if remaining:
            candidates.append(remaining[int(rng.integers(0, len(remaining)))])

    entries = []
    for rank, step in enumerate(candidates, start=1):
        noise = float(rng.normal(0.0, 0.05))
        score = round(max(0.0, min(1.0, spec.true_effect(step) + noise)), 3)
        entries.append(
            JudgeRankEntry(
                step=step,
                rank=rank,
                score=score,
                rationale=(
                    f"[{tag}] tool result at step {step} looks inconsistent with the "
                    "reasoning that follows it"
                ),
            )
        )
    return tuple(entries)


def build_judge_panel(rng, plan: RunPlan) -> JudgePanel | None:
    if plan.spec is None or not plan.tool_steps:
        return None
    return JudgePanel(
        all_at_once=_rank(rng, plan.spec, plan.tool_steps, _MISS_PROB_ALL_AT_ONCE, "all-at-once"),
        step_by_step=_rank(
            rng, plan.spec, plan.tool_steps, _MISS_PROB_STEP_BY_STEP, "step-by-step"
        ),
    )
