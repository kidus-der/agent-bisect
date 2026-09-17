"""Builds one synthetic run's causal structure and step-actor layout.

`RunPlan` is the generator's internal, pre-serialization shape: enough to
derive every dashboard DTO (`RunSummary`, `RunDetail`, dataset entries,
benchmark rows) plus enough to regenerate a step's deep payload on demand
(`fixtures.serialize`) without storing it on disk.

The causal model (flat control before the fault, a spike at it, geometric
recovery after) mirrors `agent_bisect.attribution.fakes`'s documented shape;
`RunPlan` builds a real `FakeRunSpec` so `attribution.estimate.estimate_run`
runs against it unmodified -- the blame results in the fixtures are genuine
statistics, not typed-in numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_bisect.attribution.estimate import RunEstimate, SequentialConfig, estimate_run
from agent_bisect.attribution.fakes import FakeRunSpec, ScriptedSampler
from agent_bisect.server.fixtures.catalog import (
    AIRLINE_TASKS,
    AIRLINE_TOOLS,
    FAULT_TYPES,
    RETAIL_TASKS,
    RETAIL_TOOLS,
)
from agent_bisect.server.fixtures.synth import pick, pick_int, seeded_rng
from agent_bisect.server.schemas_runs import Actor, FaultType

_ACTOR_BLOCK: tuple[Actor, ...] = ("user", "agent", "tool", "agent")
CALLS_PER_RERUN = 10
COST_PER_CALL_USD = 0.002
JUDGE_CALL_COST_USD = 0.03


def build_actors(n_steps: int) -> tuple[Actor, ...]:
    """A plausible user/agent/tool turn sequence, 1-indexed like `FakeRunSpec.steps`."""
    actors: list[Actor] = [_ACTOR_BLOCK[i % len(_ACTOR_BLOCK)] for i in range(n_steps)]
    return tuple(actors)


def build_tool_names(rng, domain: str, actors: tuple[Actor, ...]) -> tuple[str | None, ...]:
    tools = AIRLINE_TOOLS if domain == "airline" else RETAIL_TOOLS
    return tuple(pick(rng, tools) if actor == "tool" else None for actor in actors)


def _treated_probs(
    n_steps: int,
    planted_step: int,
    control_prob: float,
    planted_prob: float,
    recovery_prob: float,
    decay: float,
) -> tuple[float, ...]:
    """Same shape as `attribution.fakes`'s model: flat, spike, decaying recovery."""
    probs: list[float] = []
    for step in range(1, n_steps + 1):
        if step < planted_step:
            probs.append(control_prob)
        elif step == planted_step:
            probs.append(planted_prob)
        else:
            steps_past = step - planted_step - 1
            probs.append(max(control_prob, recovery_prob * decay**steps_past))
    return tuple(probs)


@dataclass(frozen=True, slots=True)
class RunPlan:
    """Everything needed to serialize one fixture run, before JSON shaping."""

    run_id: str
    domain: str
    task_id: str
    agent_model: str
    user_model: str
    seed: int
    tau2_commit: str
    created_at: str
    actors: tuple[Actor, ...]
    tool_names: tuple[str | None, ...]
    passed: bool
    reward: float
    fault_type: FaultType | None
    planted_step: int | None
    spec: FakeRunSpec | None
    tested_steps: tuple[int, ...]
    estimate_shared: RunEstimate | None
    estimate_no_control: RunEstimate | None
    estimate_per_step: RunEstimate | None
    base_pass_rate: float | None
    split: str | None

    @property
    def n_steps(self) -> int:
        return len(self.actors)

    @property
    def tool_steps(self) -> tuple[int, ...]:
        return tuple(i + 1 for i, actor in enumerate(self.actors) if actor == "tool")


_AGENT_MODELS = ("nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.3-70b-instruct")
_USER_MODEL = "meta/llama-3.1-8b-instruct"
_TAU2_COMMIT = "a1b2c3d4e5f6"


def build_run_plan(
    index: int,
    *,
    master_seed: int,
    force_domain: str | None = None,
    force_n_steps: int | None = None,
    force_fail: bool | None = None,
    force_plant: bool | None = None,
    force_planted_step: int | None = None,
    run_id: str | None = None,
) -> RunPlan:
    """Build one run. `force_*` knobs back the edge-case fixtures in `dataset.py`."""
    rid = run_id or f"run-{index:04d}"
    rng = seeded_rng(master_seed, rid)
    domain = force_domain or pick(rng, ("airline", "retail"))
    task_pool = AIRLINE_TASKS if domain == "airline" else RETAIL_TASKS
    task_id = pick(rng, task_pool)
    n_steps = force_n_steps or pick_int(rng, 8, 30)
    actors = build_actors(n_steps)
    tool_names = build_tool_names(rng, domain, actors)
    tool_steps = tuple(i + 1 for i, actor in enumerate(actors) if actor == "tool")

    is_failure = force_fail if force_fail is not None else rng.random() < 0.45
    plant = (
        (force_plant if force_plant is not None else rng.random() < 0.8)
        and is_failure
        and bool(tool_steps)
    )

    if not is_failure:
        return RunPlan(
            run_id=rid,
            domain=domain,
            task_id=task_id,
            agent_model=pick(rng, _AGENT_MODELS),
            user_model=_USER_MODEL,
            seed=int(rng.integers(0, 2**31 - 1)),
            tau2_commit=_TAU2_COMMIT,
            created_at=f"2026-08-{1 + index % 28:02d}T09:00:00Z",
            actors=actors,
            tool_names=tool_names,
            passed=True,
            reward=1.0,
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

    min_before, min_after = 1, 3
    lo = 1 + min_before
    hi = max(lo, n_steps - min_after)
    candidate_steps = tuple(s for s in tool_steps if lo <= s <= hi) or tool_steps or (1,)
    planted_step = force_planted_step or candidate_steps[int(rng.integers(0, len(candidate_steps)))]
    control_prob = float(rng.uniform(0.00, 0.15))
    planted_prob = float(rng.uniform(0.60, 0.95))
    recovery_prob = float(rng.uniform(0.15, 0.45))
    spec = FakeRunSpec(
        run_id=rid,
        planted_step=planted_step,
        control_prob=control_prob,
        treated_probs=_treated_probs(
            n_steps, planted_step, control_prob, planted_prob, recovery_prob, decay=0.65
        ),
    )
    sampler = ScriptedSampler(spec)
    tested_steps = tuple(spec.steps)
    config = SequentialConfig()
    est_seed = int(rng.integers(0, 2**31 - 1))
    estimate_shared = estimate_run(
        tested_steps, sampler, config, control_mode="shared", seed=est_seed
    )
    estimate_no_control = estimate_run(
        tested_steps, sampler, config, control_mode="none", seed=est_seed
    )
    estimate_per_step = estimate_run(
        tested_steps, sampler, config, control_mode="per_step", seed=est_seed
    )

    # Indexed directly rather than through `pick()`: pyright's generic-bound
    # solving for `pick[S: str]` widens the result to plain `str`, but direct
    # indexing on a `tuple[FaultType, ...]` correctly keeps the Literal type.
    fault_type = FAULT_TYPES[int(rng.integers(0, len(FAULT_TYPES)))] if plant else None
    split = "test" if index % 3 == 0 else "dev"

    return RunPlan(
        run_id=rid,
        domain=domain,
        task_id=task_id,
        agent_model=pick(rng, _AGENT_MODELS),
        user_model=_USER_MODEL,
        seed=int(rng.integers(0, 2**31 - 1)),
        tau2_commit=_TAU2_COMMIT,
        created_at=f"2026-08-{1 + index % 28:02d}T09:00:00Z",
        actors=actors,
        tool_names=tool_names,
        passed=False,
        reward=0.0,
        fault_type=fault_type,
        planted_step=planted_step if plant else None,
        spec=spec,
        tested_steps=tested_steps,
        estimate_shared=estimate_shared,
        estimate_no_control=estimate_no_control,
        estimate_per_step=estimate_per_step,
        base_pass_rate=float(rng.uniform(0.75, 1.0)) if plant else None,
        split=split if plant else None,
    )
