"""Scripted fake agent runs with a planted causal step, for testing the estimator.

A `FakeRunSpec` is a generative model of one recorded failure: `n_steps`, the
planted step `k*`, a control pass probability, and a true treated pass
probability per step. `ScriptedSampler` turns a spec into a `RerunSampler`, so
the estimator cannot tell it apart from the real replay runner -- and nothing
here touches the network or any global RNG.

The shape of the model, in one line per region of the run:

- before `k*`: treated == control, so the true effect is exactly zero (fixing a
  step that happens before the fault changes nothing);
- at `k*`: a large treated probability (the fault is undone);
- after `k*`: partial recovery decaying geometrically back to the control rate,
  because a later fix can still rescue some runs. This is what makes the
  earliest-step blame rule necessary rather than decorative.

Every parameter and its justification is fixed in
`docs/decisions/0006-p4-synthetic-design.md`, which was committed before the P4
gate was run for the first time. Do not retune anything here in response to a
gate result.

Note what this model bakes in: the control probability is a single per-run
number, so the "flat control" assumption behind the shared control arm
(`docs/decisions/0005-shared-control.md`) holds here by construction. P4
therefore measures the estimator's statistics, not that modelling choice; P5's
`control_mode="per_step"` ablation on real runs is where the assumption is
actually tested.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import numpy as np

from agent_bisect.attribution.estimate import Arm

_ARMS: frozenset[str] = frozenset({"treated", "control"})


@dataclass(frozen=True, slots=True)
class SyntheticRunConfig:
    """Generative parameters, fixed in `docs/decisions/0006-p4-synthetic-design.md`."""

    min_steps: int = 8
    max_steps: int = 30
    min_steps_before_planted: int = 1
    min_steps_after_planted: int = 3
    control_prob_range: tuple[float, float] = (0.00, 0.15)
    planted_prob_range: tuple[float, float] = (0.60, 0.95)
    recovery_prob_range: tuple[float, float] = (0.15, 0.45)
    recovery_decay: float = 0.65


DEFAULT_SYNTHETIC_CONFIG = SyntheticRunConfig()


@dataclass(frozen=True, slots=True)
class FakeRunSpec:
    """One synthetic failed run. Steps are 1-indexed, as in "step 7 of 12"."""

    run_id: str
    planted_step: int
    control_prob: float
    treated_probs: tuple[float, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.treated_probs:
            raise ValueError("a run needs at least one step")
        if not 1 <= self.planted_step <= self.n_steps:
            raise ValueError(
                f"planted_step {self.planted_step} is outside a run of {self.n_steps} steps"
            )
        probabilities = (self.control_prob, *self.treated_probs)
        if not all(0.0 <= probability <= 1.0 for probability in probabilities):
            raise ValueError("every probability must lie in [0, 1]")

    @property
    def n_steps(self) -> int:
        return len(self.treated_probs)

    @property
    def steps(self) -> Iterator[int]:
        return iter(range(1, self.n_steps + 1))

    def treated_prob(self, step: int) -> float:
        if not 1 <= step <= self.n_steps:
            raise ValueError(f"step {step} is outside a run of {self.n_steps} steps")
        return self.treated_probs[step - 1]

    def true_effect(self, step: int) -> float:
        """The effect the estimator is trying to recover for this step."""
        return self.treated_prob(step) - self.control_prob


BRIEF_12_STEP_RUN = FakeRunSpec(
    run_id="brief-12-step",
    planted_step=7,
    control_prob=0.10,
    treated_probs=(0.10, 0.12, 0.12, 0.18, 0.10, 0.10, 0.88, 0.40, 0.30, 0.18, 0.12, 0.10),
)
"""The brief's worked example, verbatim. A demo and UI fixture, not gate sample."""


def _treated_probs(
    n_steps: int,
    planted_step: int,
    control_prob: float,
    planted_prob: float,
    recovery_prob: float,
    decay: float,
) -> tuple[float, ...]:
    """Control rate before the fault, a spike at it, decaying recovery after it."""
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


def sample_run_spec(
    rng: np.random.Generator,
    run_id: str,
    config: SyntheticRunConfig = DEFAULT_SYNTHETIC_CONFIG,
) -> FakeRunSpec:
    """Draw one synthetic run from `rng`. No global RNG state is read or written."""
    n_steps = int(rng.integers(config.min_steps, config.max_steps, endpoint=True))
    planted_step = int(
        rng.integers(
            1 + config.min_steps_before_planted,
            n_steps - config.min_steps_after_planted,
            endpoint=True,
        )
    )
    control_prob = float(rng.uniform(*config.control_prob_range))
    planted_prob = float(rng.uniform(*config.planted_prob_range))
    recovery_prob = float(rng.uniform(*config.recovery_prob_range))
    return FakeRunSpec(
        run_id=run_id,
        planted_step=planted_step,
        control_prob=control_prob,
        treated_probs=_treated_probs(
            n_steps,
            planted_step,
            control_prob,
            planted_prob,
            recovery_prob,
            config.recovery_decay,
        ),
    )


def sample_run_specs(
    count: int,
    master_seed: int,
    config: SyntheticRunConfig = DEFAULT_SYNTHETIC_CONFIG,
) -> tuple[FakeRunSpec, ...]:
    """`count` independent runs, reproducible from `master_seed` alone."""
    if count <= 0:
        raise ValueError(f"count must be positive, got {count}")
    return tuple(
        sample_run_spec(
            np.random.default_rng([master_seed, index]),
            run_id=f"synthetic-{index:04d}",
            config=config,
        )
        for index in range(count)
    )


@dataclass(frozen=True, slots=True)
class ScriptedSampler:
    """A `RerunSampler` that flips scripted coins instead of re-running an agent.

    The control arm ignores its fork step, which is exactly the flat-control
    assumption the shared control arm relies on.
    """

    spec: FakeRunSpec

    def sample(self, step: int, arm: Arm, n: int, seed: int) -> Sequence[bool]:
        if n <= 0:
            raise ValueError(f"n must be positive, got {n}")
        if arm not in _ARMS:
            raise ValueError(f"unknown arm {arm!r}, expected one of {sorted(_ARMS)}")
        treated_prob = self.spec.treated_prob(step)  # also rejects a step outside the run
        probability = self.spec.control_prob if arm == "control" else treated_prob
        rng = np.random.default_rng(seed)
        return tuple(bool(draw) for draw in rng.random(n) < probability)
