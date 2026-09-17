"""`RunPlan` -> dashboard DTOs, including on-demand deep-payload regeneration.

`build_step_payload`/`build_intervention_diff`/`build_state_diff` are pure
functions of `(plan, step_idx)`: they derive everything from a
`seeded_rng(plan.run_id, step_idx, ...)` draw rather than reading anything
stored on the plan, so `fixture_repository.py` can call them straight from
a `RunPlan` kept in memory without ever having serialized the deep payload
to `data/fixtures/*.json` -- that's what keeps the on-disk fixture set
under the 5 MB budget with 260+ runs.
"""

from __future__ import annotations

from agent_bisect.attribution.estimate import ArmResult, RunEstimate, StepEffect
from agent_bisect.server.fixtures.catalog import (
    BRIEF_FAULT_STEP,
    BRIEF_ORIGINAL_RESULT,
    BRIEF_REPLACED_RESULT,
    BRIEF_RUN_ID,
    DIFF_PATHS_BY_DOMAIN,
    LONG_PAYLOAD_LENGTH,
    LONG_PAYLOAD_RUN_ID,
    LONG_PAYLOAD_STEP,
    UNICODE_PHRASE,
    UNICODE_RUN_ID,
    UNICODE_STEP,
)
from agent_bisect.server.fixtures.run_builder import (
    CALLS_PER_RERUN,
    COST_PER_CALL_USD,
    JUDGE_CALL_COST_USD,
    RunPlan,
)
from agent_bisect.server.fixtures.synth import pick, pick_int, random_id, seeded_rng
from agent_bisect.server.schemas_runs import (
    ArmResultView,
    BlameCell,
    DiffEntry,
    InterventionDiff,
    JudgePanel,
    RerunPage,
    RerunRow,
    RunDetail,
    RunEstimateView,
    RunSummary,
    SparkPoint,
    StateDiff,
    StepEffectView,
    StepPayload,
    StepView,
)

_MUTATING_PREFIXES = ("update_", "book_", "cancel_", "modify_", "return_", "exchange_", "send_")


def _is_mutating(tool_name: str | None) -> bool:
    return tool_name is not None and tool_name.startswith(_MUTATING_PREFIXES)


def _to_arm_view(arm: ArmResult | None) -> ArmResultView | None:
    return None if arm is None else ArmResultView(successes=arm.successes, n=arm.n)


def _to_step_effect_view(effect: StepEffect) -> StepEffectView:
    return StepEffectView(
        step=effect.step,
        treated=_to_arm_view(effect.treated),  # type: ignore[arg-type]
        control=_to_arm_view(effect.control),
        effect=round(effect.effect, 4),
        ci_low=round(effect.ci_low, 4),
        ci_high=round(effect.ci_high, 4),
        n_batches=effect.n_batches,
        stop_reason=effect.stop_reason,
    )


def to_run_estimate_view(estimate: RunEstimate | None) -> RunEstimateView | None:
    if estimate is None:
        return None
    return RunEstimateView(
        step_effects=tuple(_to_step_effect_view(e) for e in estimate.step_effects),
        blamed_step=estimate.blamed_step,
        control_mode=estimate.control_mode,
        control_fork_step=estimate.control_fork_step,
        treated_reruns=estimate.treated_reruns,
        control_reruns=estimate.control_reruns,
        sampler_calls=estimate.sampler_calls,
    )


def _calls_and_cost(plan: RunPlan) -> tuple[int, float]:
    if plan.estimate_shared is None:
        return 0, 0.0
    calls = plan.estimate_shared.sampler_calls * CALLS_PER_RERUN
    cost = calls * COST_PER_CALL_USD + JUDGE_CALL_COST_USD
    return calls, round(cost, 4)


def _spark_points(plan: RunPlan) -> tuple[SparkPoint, ...]:
    rng = seeded_rng(plan.run_id, "spark")
    points = []
    for idx, actor in enumerate(plan.actors, start=1):
        latency = pick_int(rng, 150, 4200) if actor != "user" else pick_int(rng, 400, 9000)
        tokens = pick_int(rng, 30, 900)
        points.append(SparkPoint(step_idx=idx, actor=actor, latency_ms=latency, tokens=tokens))
    return tuple(points)


def _blame_stripe(plan: RunPlan) -> tuple[BlameCell, ...]:
    effect_by_step: dict[int, float] = {}
    if plan.estimate_shared is not None:
        effect_by_step = {e.step: round(e.effect, 4) for e in plan.estimate_shared.step_effects}
    cells = []
    for idx in range(1, plan.n_steps + 1):
        tested = idx in effect_by_step
        cells.append(BlameCell(step_idx=idx, effect=effect_by_step.get(idx), tested=tested))
    return tuple(cells)


def to_run_summary(plan: RunPlan) -> RunSummary:
    calls, cost = _calls_and_cost(plan)
    decisive = plan.estimate_shared.blamed_step if plan.estimate_shared else None
    return RunSummary(
        run_id=plan.run_id,
        domain=plan.domain,
        task_id=plan.task_id,
        model=plan.agent_model,
        outcome="pass" if plan.passed else "fail",
        n_steps=plan.n_steps,
        decisive_step=decisive,
        fault_type=plan.fault_type,
        planted_step=plan.planted_step,
        cost_usd=cost,
        calls=calls,
        sparkline=_spark_points(plan),
        blame_stripe=_blame_stripe(plan),
    )


def _step_text(rng, actor: str, tool_name: str | None) -> str:
    if actor == "tool":
        return f"{tool_name} returned"
    if actor == "user":
        return pick(
            rng,
            (
                "asks about the reservation status",
                "confirms the requested change",
                "provides an order number",
                "pushes back on the proposed fix",
            ),
        )
    return pick(
        rng,
        (
            "looks up the record before acting",
            "explains the next step to the user",
            "calls a tool to check the current state",
            "summarizes what it found so far",
        ),
    )


def to_step_views(plan: RunPlan) -> tuple[StepView, ...]:
    rng = seeded_rng(plan.run_id, "steps")
    decisive = plan.estimate_shared.blamed_step if plan.estimate_shared else None
    boundary = decisive or plan.n_steps
    views = []
    for idx, (actor, tool_name) in enumerate(
        zip(plan.actors, plan.tool_names, strict=True), start=1
    ):
        views.append(
            StepView(
                step_idx=idx,
                actor=actor,  # type: ignore[arg-type]
                tool_name=tool_name,
                text=_step_text(rng, actor, tool_name),
                from_tape=idx <= boundary,
                state_changed=_is_mutating(tool_name),
            )
        )
    return tuple(views)


def to_run_detail(plan: RunPlan, judge: JudgePanel | None) -> RunDetail:
    return RunDetail(
        run_id=plan.run_id,
        domain=plan.domain,
        task_id=plan.task_id,
        agent_model=plan.agent_model,
        user_model=plan.user_model,
        seed=plan.seed,
        tau2_commit=plan.tau2_commit,
        created_at=plan.created_at,
        outcome="pass" if plan.passed else "fail",
        reward=plan.reward,
        steps=to_step_views(plan),
        planted_step=plan.planted_step,
        fault_type=plan.fault_type,
        estimate=to_run_estimate_view(plan.estimate_shared),
        judge=judge,
    )


def _tool_call_payload(rng, domain: str, tool_name: str) -> tuple[dict[str, str], dict[str, str]]:
    record_id = random_id(rng)
    args = {"id": record_id}
    if domain == "airline":
        result = {
            "reservation_id": record_id,
            "status": "confirmed",
            "origin": pick(rng, ("SFO", "JFK", "ORD")),
        }
    else:
        result = {
            "order_id": record_id,
            "status": "pending",
            "item_count": str(pick_int(rng, 1, 5)),
        }
    return args, result


def build_step_payload(plan: RunPlan, step_idx: int) -> StepPayload:
    if not 1 <= step_idx <= plan.n_steps:
        raise KeyError(f"step {step_idx} outside run {plan.run_id} ({plan.n_steps} steps)")
    rng = seeded_rng(plan.run_id, step_idx, "payload")
    actor = plan.actors[step_idx - 1]
    tool_name = plan.tool_names[step_idx - 1]
    content = _step_text(rng, actor, tool_name)
    if plan.run_id == UNICODE_RUN_ID and step_idx == UNICODE_STEP:
        content = UNICODE_PHRASE
    if plan.run_id == LONG_PAYLOAD_RUN_ID and step_idx == LONG_PAYLOAD_STEP:
        content = content + " " + "x" * LONG_PAYLOAD_LENGTH
    messages = ({"role": actor, "content": content},)
    tool_args: dict[str, str] | None = None
    tool_result: dict[str, str] | None = None
    if actor == "tool":
        tool_args, tool_result = _tool_call_payload(rng, plan.domain, tool_name or "unknown_tool")
        if plan.run_id == BRIEF_RUN_ID and step_idx == BRIEF_FAULT_STEP:
            tool_result = {**tool_result, "reservation_id": BRIEF_ORIGINAL_RESULT}
        elif plan.planted_step == step_idx and plan.fault_type is not None:
            tool_result = _apply_fault(rng, tool_result, plan.fault_type)
    return StepPayload(
        step_idx=step_idx, messages=messages, tool_args=tool_args, tool_result=tool_result
    )


def _apply_fault(rng, result: dict[str, str], fault_type: str) -> dict[str, str]:
    mutated = dict(result)
    if fault_type == "wrong_value":
        key = next(iter(mutated))
        mutated[key] = random_id(rng, 6)
    elif fault_type == "missing_field":
        key = next(iter(mutated))
        del mutated[key]
    elif fault_type == "stale_record":
        mutated["last_updated"] = "2024-01-01T00:00:00Z"
    else:  # tool_error
        mutated = {"error": "upstream service returned a 500"}
    return mutated


def build_intervention_diff(plan: RunPlan, step_idx: int) -> InterventionDiff | None:
    if plan.run_id == BRIEF_RUN_ID and step_idx == BRIEF_FAULT_STEP:
        rng = seeded_rng(plan.run_id, step_idx, "payload")
        tool_name = plan.tool_names[step_idx - 1] or "unknown_tool"
        _, base_result = _tool_call_payload(rng, plan.domain, tool_name)
        original = {**base_result, "reservation_id": BRIEF_ORIGINAL_RESULT}
        replaced = {**base_result, "reservation_id": BRIEF_REPLACED_RESULT}
        return InterventionDiff(
            step_idx=step_idx, original_tool_result=original, replaced_tool_result=replaced
        )
    if plan.planted_step != step_idx or plan.fault_type is None:
        return None
    rng = seeded_rng(plan.run_id, step_idx, "payload")
    tool_name = plan.tool_names[step_idx - 1] or "unknown_tool"
    _, original = _tool_call_payload(rng, plan.domain, tool_name)
    faulted = _apply_fault(rng, original, plan.fault_type)
    return InterventionDiff(
        step_idx=step_idx, original_tool_result=original, replaced_tool_result=faulted
    )


def build_state_diff(plan: RunPlan, step_idx: int) -> StateDiff:
    if not 1 <= step_idx <= plan.n_steps:
        raise KeyError(f"step {step_idx} outside run {plan.run_id} ({plan.n_steps} steps)")
    tool_name = plan.tool_names[step_idx - 1]
    if not _is_mutating(tool_name):
        return StateDiff(step_idx=step_idx, entries=())
    rng = seeded_rng(plan.run_id, step_idx, "state")
    paths = DIFF_PATHS_BY_DOMAIN[plan.domain]
    path = pick(rng, paths)
    return StateDiff(
        step_idx=step_idx,
        entries=(
            DiffEntry(path=path, kind="changed", before=random_id(rng, 4), after=random_id(rng, 4)),
        ),
    )


def build_reruns(plan: RunPlan) -> RerunPage:
    if plan.estimate_shared is None:
        return RerunPage(reruns=())
    rows: list[RerunRow] = []
    for effect in plan.estimate_shared.step_effects:
        for i in range(effect.treated.n):
            passed = i < effect.treated.successes
            rows.append(
                RerunRow(
                    rerun_id=f"{plan.run_id}-t{effect.step}-{i}",
                    arm="treated",
                    step=effect.step,
                    seed=plan.seed + effect.step * 100 + i,
                    passed=passed,
                    n_steps=plan.n_steps,
                    calls=CALLS_PER_RERUN,
                )
            )
    if plan.estimate_shared.control_fork_step is not None:
        control_arm = plan.estimate_shared.step_effects[0].control
        n = control_arm.n if control_arm else 0
        successes = control_arm.successes if control_arm else 0
        for i in range(n):
            rows.append(
                RerunRow(
                    rerun_id=f"{plan.run_id}-c-{i}",
                    arm="control",
                    step=plan.estimate_shared.control_fork_step,
                    seed=plan.seed + 9000 + i,
                    passed=i < successes,
                    n_steps=plan.n_steps,
                    calls=CALLS_PER_RERUN,
                )
            )
    return RerunPage(reruns=tuple(rows))


def build_rerun_steps(plan: RunPlan, rerun_id: str) -> tuple[StepView, ...]:
    """A lightweight synthetic step trace for one individual re-run."""
    rerun_row = next((r for r in build_reruns(plan).reruns if r.rerun_id == rerun_id), None)
    if rerun_row is None:
        raise KeyError(f"no re-run {rerun_id!r} for run {plan.run_id!r}")
    base = to_step_views(plan)
    return tuple(v for v in base if v.step_idx >= rerun_row.step)
