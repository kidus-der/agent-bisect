"""Assembles the full fixture run set: bulk generated runs plus the named
edge cases the UI needs to exercise (0 tested steps, a run where no step
clears delta, a 60-step run, a very long payload, unicode, and the brief's
own 12-step worked example).
"""

from __future__ import annotations

from agent_bisect.attribution.estimate import SequentialConfig, estimate_run
from agent_bisect.attribution.fakes import BRIEF_12_STEP_RUN, FakeRunSpec, ScriptedSampler
from agent_bisect.server.fixtures.catalog import BRIEF_RUN_ID, LONG_PAYLOAD_RUN_ID, UNICODE_RUN_ID
from agent_bisect.server.fixtures.run_builder import (
    RunPlan,
    build_actors,
    build_run_plan,
    build_tool_names,
)
from agent_bisect.server.fixtures.synth import seeded_rng

BULK_COUNT = 258

ZERO_TESTED_RUN_ID = "run-edge-zero-tested"
NO_CLEAR_RUN_ID = "run-edge-no-clear"
SIXTY_STEP_RUN_ID = "run-edge-60-step"
RECORDING_RUN_IDS = ("run-edge-recording-1", "run-edge-recording-2")


def _zero_tested_run(master_seed: int) -> RunPlan:
    rng = seeded_rng(master_seed, ZERO_TESTED_RUN_ID)
    n_steps = 14
    actors = build_actors(n_steps)
    tool_names = build_tool_names(rng, "airline", actors)
    return RunPlan(
        run_id=ZERO_TESTED_RUN_ID,
        domain="airline",
        task_id="refund_after_cancellation",
        agent_model="nvidia/llama-3.1-nemotron-70b-instruct",
        user_model="meta/llama-3.1-8b-instruct",
        seed=1,
        tau2_commit="a1b2c3d4e5f6",
        created_at="2026-08-15T09:00:00Z",
        actors=actors,
        tool_names=tool_names,
        passed=False,
        reward=0.0,
        fault_type=None,
        planted_step=None,
        spec=None,
        tested_steps=(),
        estimate_shared=None,
        estimate_no_control=None,
        estimate_per_step=None,
        base_pass_rate=None,
        split=None,
    )


def _no_clear_run(master_seed: int) -> RunPlan:
    n_steps = 10
    rng = seeded_rng(master_seed, NO_CLEAR_RUN_ID)
    actors = build_actors(n_steps)
    tool_names = build_tool_names(rng, "retail", actors)
    flat_prob = 0.5
    spec = FakeRunSpec(
        run_id=NO_CLEAR_RUN_ID,
        planted_step=5,
        control_prob=flat_prob,
        treated_probs=tuple(flat_prob for _ in range(n_steps)),
    )
    sampler = ScriptedSampler(spec)
    config = SequentialConfig()
    estimate = estimate_run(tuple(spec.steps), sampler, config, control_mode="shared", seed=42)
    if estimate.blamed_step is not None:
        raise AssertionError(
            "no-clear fixture run unexpectedly cleared delta; pick a different flat_prob/seed"
        )
    return RunPlan(
        run_id=NO_CLEAR_RUN_ID,
        domain="retail",
        task_id="order_dup_investigation",
        agent_model="meta/llama-3.3-70b-instruct",
        user_model="meta/llama-3.1-8b-instruct",
        seed=42,
        tau2_commit="a1b2c3d4e5f6",
        created_at="2026-08-16T09:00:00Z",
        actors=actors,
        tool_names=tool_names,
        passed=False,
        reward=0.0,
        fault_type=None,
        planted_step=None,
        spec=spec,
        tested_steps=tuple(spec.steps),
        estimate_shared=estimate,
        estimate_no_control=estimate_run(
            tuple(spec.steps), sampler, config, control_mode="none", seed=42
        ),
        estimate_per_step=estimate_run(
            tuple(spec.steps), sampler, config, control_mode="per_step", seed=42
        ),
        base_pass_rate=None,
        split=None,
    )


def _brief_run() -> RunPlan:
    spec = BRIEF_12_STEP_RUN
    n_steps = spec.n_steps
    rng = seeded_rng(1, BRIEF_RUN_ID)
    actors = build_actors(n_steps)
    tool_names = build_tool_names(rng, "airline", actors)
    sampler = ScriptedSampler(spec)
    config = SequentialConfig()
    estimate = estimate_run(tuple(spec.steps), sampler, config, control_mode="shared", seed=7)
    return RunPlan(
        run_id=BRIEF_RUN_ID,
        domain="airline",
        task_id="refund_after_cancellation",
        agent_model="nvidia/llama-3.1-nemotron-70b-instruct",
        user_model="meta/llama-3.1-8b-instruct",
        seed=7,
        tau2_commit="a1b2c3d4e5f6",
        created_at="2026-08-01T09:00:00Z",
        actors=actors,
        tool_names=tool_names,
        passed=False,
        reward=0.0,
        fault_type="wrong_value",
        planted_step=spec.planted_step,
        spec=spec,
        tested_steps=tuple(spec.steps),
        estimate_shared=estimate,
        estimate_no_control=estimate_run(
            tuple(spec.steps), sampler, config, control_mode="none", seed=7
        ),
        estimate_per_step=estimate_run(
            tuple(spec.steps), sampler, config, control_mode="per_step", seed=7
        ),
        base_pass_rate=0.9,
        split="test",
    )


def _recording_run(
    master_seed: int, run_id: str, domain: str, task_id: str, n_steps: int
) -> RunPlan:
    """A run that's still being recorded: no outcome, no reward, no blame --
    `status="recording"` masks `outcome`/`reward` at serialization time
    (`fixtures.serialize`), so the UI's in-progress state has something real
    to render against instead of only ever seeing finished runs."""
    rng = seeded_rng(master_seed, run_id)
    actors = build_actors(n_steps)
    tool_names = build_tool_names(rng, domain, actors)
    return RunPlan(
        run_id=run_id,
        domain=domain,
        task_id=task_id,
        agent_model="nvidia/llama-3.1-nemotron-70b-instruct",
        user_model="meta/llama-3.1-8b-instruct",
        seed=int(rng.integers(0, 2**31 - 1)),
        tau2_commit="a1b2c3d4e5f6",
        created_at="2026-09-17T09:00:00Z",
        actors=actors,
        tool_names=tool_names,
        passed=False,  # unused: `status="recording"` masks `outcome` regardless
        reward=0.0,  # unused: `status="recording"` masks `reward` regardless
        fault_type=None,
        planted_step=None,
        spec=None,
        tested_steps=(),
        estimate_shared=None,
        estimate_no_control=None,
        estimate_per_step=None,
        base_pass_rate=None,
        split=None,
        status="recording",
    )


def build_all_plans(master_seed: int) -> tuple[RunPlan, ...]:
    """The whole fixture run set: named edge cases plus `BULK_COUNT` generated runs."""
    edge_cases = (
        _zero_tested_run(master_seed),
        _no_clear_run(master_seed),
        build_run_plan(
            90001,
            master_seed=master_seed,
            force_n_steps=60,
            force_fail=True,
            force_plant=True,
            run_id=SIXTY_STEP_RUN_ID,
        ),
        build_run_plan(
            90002,
            master_seed=master_seed,
            force_fail=True,
            force_plant=True,
            run_id=LONG_PAYLOAD_RUN_ID,
        ),
        build_run_plan(
            90003,
            master_seed=master_seed,
            force_fail=True,
            force_plant=True,
            run_id=UNICODE_RUN_ID,
        ),
        _brief_run(),
        _recording_run(
            master_seed, RECORDING_RUN_IDS[0], "airline", "seat_upgrade_request", n_steps=4
        ),
        _recording_run(
            master_seed, RECORDING_RUN_IDS[1], "retail", "cancel_before_ship", n_steps=9
        ),
    )
    bulk = tuple(build_run_plan(index, master_seed=master_seed) for index in range(BULK_COUNT))
    return edge_cases + bulk


def _position_bucket(planted_step: int, n_steps: int) -> str:
    fraction = planted_step / n_steps
    if fraction <= 1 / 3:
        return "early"
    if fraction <= 2 / 3:
        return "middle"
    return "late"


def build_dataset_entries(plans: tuple[RunPlan, ...]):
    """The dataset explorer's rows: one per labelled (planted-fault) run."""
    from agent_bisect.server.schemas_benchmark import DatasetEntry

    entries = []
    for plan in plans:
        if plan.fault_type is None or plan.spec is None or plan.split is None:
            continue
        entries.append(
            DatasetEntry(
                run_id=plan.run_id,
                domain=plan.domain,
                task_id=plan.task_id,
                fault_type=plan.fault_type,  # type: ignore[arg-type]
                planted_step=plan.planted_step,  # type: ignore[arg-type]
                position_bucket=_position_bucket(plan.planted_step, plan.n_steps),  # type: ignore[arg-type,index]
                split=plan.split,  # type: ignore[arg-type]
                base_pass_rate=round(plan.base_pass_rate, 4) if plan.base_pass_rate else 1.0,
                faulted_pass_rate=round(plan.spec.control_prob, 4),
            )
        )
    return tuple(entries)
