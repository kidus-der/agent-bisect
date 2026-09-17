"""Treated-vs-control effect estimation for a single step of a recorded run.

`effect(k) = P(pass | fix step k) - P(pass | step k as recorded)`, with a Wilson
score interval per arm and Newcombe's hybrid score interval (1998, method 10)
for the difference. Sampling is sequential: batches of `batch` per arm up to
`max_n`, stopping a step early once its interval is decisively above or at-or-
below delta. Blame goes to the **earliest** step whose interval lower bound
clears delta -- not the largest effect, because a later fix can partially
recover a run that was already doomed earlier.

Control arms and their fork point
---------------------------------
The control for step `k` is "restore the world at `k`, apply no intervention,
run the rest". On a recorded failure the prefix is fixed, so a control arm is
fully determined by its fork step; there is nothing else to vary. With
`control_mode="shared"` a run draws **one** control arm, forked at the earliest
tested step and taken to the full `max_n`, and every tested step is compared
against it. That is what makes the cost `(suspects + 1) x N` rather than
`2 x suspects x N`, and it assumes:

    P(pass | restore at k, no intervention) does not depend materially on k.

That assumption is plausible -- every control fork replays the same recorded
prefix onto the same failing trajectory -- but it is not free, and the shared
arm correlates every step's interval, so one unlucky-low control shifts all
effects up together. `control_mode="per_step"` draws a fresh control beside
each treated arm and exists to check the assumption on real runs;
`control_mode="none"` is the no-control ablation (effect := treated pass rate,
Wilson interval), which the baselines need. See
`docs/decisions/0005-shared-control.md`.

Repeated looks and the efficacy boundary
----------------------------------------
Acting on a nominal 95% bound at four successive looks is not a 95% test, and
under the earliest-step rule a false crossing at an early null step is
irreversible. Interim **blame** decisions therefore consult an O'Brien-Fleming
boundary (`efficacy_boundary="obf"`, the default): at look j the step is
blame-worthy only if the interval computed at that look's level clears delta.
`"none"` keeps the original uncorrected behaviour so the two can be compared.

Two things stay at the nominal level: futility ("cleared") stopping, which
cannot manufacture a false blame, and the **reported** interval, which is always
the nominal 95% Newcombe CI at the step's final n -- that is what the P4
coverage criterion measures and what the dashboard draws. Only the decision
moves. See `docs/decisions/0008-sequential-efficacy-boundary.md`.

This module is pure: it reaches the world only through the `RerunSampler`
protocol, so the replay runner, the fakes and the baselines all plug into the
same estimator.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal, Protocol

Arm = Literal["treated", "control"]
ControlMode = Literal["shared", "per_step", "none"]
StopReason = Literal["blameworthy", "cleared", "max_n"]
EfficacyBoundary = Literal["obf", "none"]

DEFAULT_BATCH = 4
DEFAULT_MAX_N = 16
DEFAULT_DELTA = 0.10
DEFAULT_CONF = 0.95

# O'Brien-Fleming boundary for K = 4 equally spaced looks at overall two-sided
# alpha = 0.05. O'Brien & Fleming (1979); constant C_B(4, 0.05) = 2.024 as
# tabulated in Jennison & Turnbull (2000), Table 2.3. Verified in
# `tests/attribution/test_boundary.py`: each value equals C * sqrt(K / j), the
# implied nominal alphas reproduce the published table, and integrating the
# crossing probability of the equivalent constant score-scale boundary returns
# an overall two-sided alpha of 0.05. See docs/decisions/0008-*.
OBF_CONSTANT = 2.024
OBF_LOOKS = 4
OBF_CRITICAL_Z: tuple[float, ...] = (4.049, 2.863, 2.337, 2.024)

_SEED_BYTES = 4
_SEED_MODULUS = 1 << (8 * _SEED_BYTES)


@dataclass(frozen=True, slots=True)
class Interval:
    """A closed confidence interval. Immutable; construct a new one to change it."""

    low: float
    high: float

    @property
    def width(self) -> float:
        return self.high - self.low

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high


def _z_for(conf: float) -> float:
    if not 0.0 < conf < 1.0:
        raise ValueError(f"conf must be strictly between 0 and 1, got {conf}")
    return NormalDist().inv_cdf(1.0 - (1.0 - conf) / 2.0)


def confidence_for_z(critical_z: float) -> float:
    """The two-sided confidence level a critical z value corresponds to."""
    return 2.0 * NormalDist().cdf(critical_z) - 1.0


def _validate_arm_counts(successes: int, n: int) -> None:
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be between 0 and n={n}, got {successes}")


def wilson_interval(successes: int, n: int, conf: float = DEFAULT_CONF) -> Interval:
    """Wilson score interval for a binomial proportion.

    Preferred over Wald because arms here are small (N <= 16) with proportions
    often at 0 or 1, exactly where a Wald interval collapses to zero width.
    """
    z = _z_for(conf)
    _validate_arm_counts(successes, n)
    z_sq = z * z
    denominator = n + z_sq
    centre = (successes + z_sq / 2.0) / denominator
    half_width = (z / denominator) * math.sqrt(successes * (n - successes) / n + z_sq / 4.0)
    # The score interval always contains the estimate and never leaves [0, 1];
    # clamping to both snaps 0/n and n/n onto the exact boundary, which
    # floating-point arithmetic otherwise misses by ~1e-17.
    estimate = successes / n
    return Interval(
        min(max(0.0, centre - half_width), estimate),
        max(min(1.0, centre + half_width), estimate),
    )


def newcombe_diff_interval(
    x1: int, n1: int, x2: int, n2: int, conf: float = DEFAULT_CONF
) -> Interval:
    """Newcombe's hybrid score interval for `p1 - p2` (Newcombe 1998, method 10).

    Built from the two Wilson intervals: the distance from each estimate to the
    bound that pushes the difference outward is combined in quadrature.
    """
    first = wilson_interval(x1, n1, conf=conf)
    second = wilson_interval(x2, n2, conf=conf)
    p1, p2 = x1 / n1, x2 / n2
    difference = p1 - p2
    low = difference - math.hypot(p1 - first.low, second.high - p2)
    high = difference + math.hypot(first.high - p1, p2 - second.low)
    return Interval(max(-1.0, low), min(1.0, high))


@dataclass(frozen=True, slots=True)
class ArmResult:
    """Outcomes accumulated for one arm of one step."""

    successes: int
    n: int

    def __post_init__(self) -> None:
        if self.n < 0:
            raise ValueError(f"n must not be negative, got {self.n}")
        if not 0 <= self.successes <= self.n:
            raise ValueError(f"successes must be between 0 and n={self.n}, got {self.successes}")

    @property
    def rate(self) -> float:
        if self.n == 0:
            raise ValueError("cannot take the pass rate of an empty arm")
        return self.successes / self.n

    def extended(self, successes: int, n: int) -> ArmResult:
        """Return a new arm with `n` further draws folded in; never mutates."""
        return ArmResult(self.successes + successes, self.n + n)


@dataclass(frozen=True, slots=True)
class StepEffect:
    """The measured effect of fixing one step, and why sampling stopped."""

    step: int
    treated: ArmResult
    control: ArmResult | None
    effect: float
    ci_low: float
    ci_high: float
    n_batches: int
    stop_reason: StopReason
    # The blame decision is taken at the efficacy boundary's level for the look
    # that made it, which is not the level of the reported interval above.
    decision_conf: float = DEFAULT_CONF
    decision_ci_low: float = float("nan")

    @property
    def interval(self) -> Interval:
        """The reported effect interval: always the nominal `conf` level."""
        return Interval(self.ci_low, self.ci_high)

    @property
    def blameworthy(self) -> bool:
        """Whether this step's own sampling ended in a blame-worthy verdict."""
        return self.stop_reason == "blameworthy"


@dataclass(frozen=True, slots=True)
class SequentialConfig:
    """Pre-registered sampling plan (`docs/decisions/0001-preregistration.md`).

    A single-look fixed-N design is expressed as `batch == max_n`.
    """

    batch: int = DEFAULT_BATCH
    max_n: int = DEFAULT_MAX_N
    delta: float = DEFAULT_DELTA
    conf: float = DEFAULT_CONF
    efficacy_boundary: EfficacyBoundary = "obf"

    def __post_init__(self) -> None:
        if self.batch <= 0:
            raise ValueError(f"batch must be positive, got {self.batch}")
        if self.max_n < self.batch:
            raise ValueError(f"max_n={self.max_n} must be at least batch={self.batch}")
        if not 0.0 <= self.delta < 1.0:
            raise ValueError(f"delta must be in [0, 1), got {self.delta}")
        _z_for(self.conf)
        if self.efficacy_boundary not in ("obf", "none"):
            raise ValueError(
                f"efficacy_boundary must be 'obf' or 'none', got {self.efficacy_boundary!r}"
            )
        if self.efficacy_boundary == "obf" and self.planned_looks != OBF_LOOKS:
            raise ValueError(
                f"the 'obf' boundary is defined for exactly {OBF_LOOKS} looks, but "
                f"batch={self.batch} and max_n={self.max_n} plan {self.planned_looks}"
            )

    @property
    def planned_looks(self) -> int:
        """How many batches the plan takes if no step ever stops early."""
        return math.ceil(self.max_n / self.batch)


@dataclass(frozen=True, slots=True)
class RunEstimate:
    """Every tested step of one run, the blamed step, and what it cost."""

    step_effects: tuple[StepEffect, ...]
    blamed_step: int | None
    control_mode: ControlMode
    control_fork_step: int | None
    treated_reruns: int
    control_reruns: int
    sampler_calls: int

    @property
    def total_reruns(self) -> int:
        return self.treated_reruns + self.control_reruns


class RerunSampler(Protocol):
    """The estimator's only contact with the world.

    `sample` restores the run at `step`, applies the intervention for `arm`
    (nothing, for the control), runs the rest `n` times under `seed`, and
    returns one pass/fail per re-run. The replay runner implements this against
    real snapshots; the P4 fakes implement it from scripted probabilities.
    """

    def sample(self, step: int, arm: Arm, n: int, seed: int) -> Sequence[bool]: ...


def _derive_seed(base_seed: int, step: int, arm: Arm, offset: int) -> int:
    """A stable, collision-resistant seed per (run, step, arm, draws already taken)."""
    payload = f"{base_seed}:{step}:{arm}:{offset}".encode()
    digest = hashlib.blake2b(payload, digest_size=_SEED_BYTES).digest()
    return int.from_bytes(digest, "big") % _SEED_MODULUS


def _draw(sampler: RerunSampler, step: int, arm: Arm, n: int, seed: int) -> int:
    """Take `n` re-runs from the sampler and return how many passed."""
    outcomes = sampler.sample(step=step, arm=arm, n=n, seed=seed)
    if len(outcomes) != n:
        raise ValueError(
            f"sampler returned {len(outcomes)} outcomes for step {step} arm {arm}, expected {n}"
        )
    return sum(1 for outcome in outcomes if outcome)


def _effect_and_interval(
    treated: ArmResult, control: ArmResult | None, conf: float
) -> tuple[float, Interval]:
    if control is None:
        return treated.rate, wilson_interval(treated.successes, treated.n, conf=conf)
    interval = newcombe_diff_interval(
        treated.successes, treated.n, control.successes, control.n, conf=conf
    )
    return treated.rate - control.rate, interval


def decision_confidence(config: SequentialConfig, look: int) -> float:
    """The confidence level the blame decision uses at this (1-indexed) look.

    Without a boundary this is just the nominal level at every look -- which is
    what made a nominal 95% bound, consulted four times, not a 95% bound.
    """
    if config.efficacy_boundary == "none":
        return config.conf
    return confidence_for_z(OBF_CRITICAL_Z[look - 1])


def _stop_reason(decision: Interval, reported: Interval, delta: float) -> StopReason | None:
    """Blame on the boundary-adjusted interval; clear on the nominal one.

    Futility stopping cannot manufacture a false blame, so it needs no
    multiplicity control and stays at the nominal level (docs/decisions/0008).
    """
    if decision.low > delta:
        return "blameworthy"
    if reported.high <= delta:
        return "cleared"
    return None


def _initial_control(
    control_mode: ControlMode, shared_control: ArmResult | None
) -> ArmResult | None:
    if control_mode == "shared":
        if shared_control is None:
            raise ValueError("control_mode='shared' requires a shared_control arm")
        return shared_control
    if shared_control is not None:
        raise ValueError(
            "shared_control is only meaningful for control_mode='shared', "
            f"not {control_mode!r}"
        )
    return None if control_mode == "none" else ArmResult(0, 0)


def estimate_step(
    step: int,
    sampler: RerunSampler,
    config: SequentialConfig,
    *,
    seed: int,
    control_mode: ControlMode = "per_step",
    shared_control: ArmResult | None = None,
) -> StepEffect:
    """Sample one step's treated arm in batches until it is decisive or exhausted."""
    control = _initial_control(control_mode, shared_control)
    treated = ArmResult(0, 0)
    batches = 0

    while True:
        take = min(config.batch, config.max_n - treated.n)
        treated = treated.extended(
            _draw(sampler, step, "treated", take, _derive_seed(seed, step, "treated", treated.n)),
            take,
        )
        if control_mode == "per_step":
            assert control is not None  # per_step always starts from an empty arm
            control = control.extended(
                _draw(
                    sampler, step, "control", take, _derive_seed(seed, step, "control", control.n)
                ),
                take,
            )
        batches += 1

        effect, interval = _effect_and_interval(treated, control, config.conf)
        conf_for_decision = decision_confidence(config, batches)
        _, decision = _effect_and_interval(treated, control, conf_for_decision)
        reason = _stop_reason(decision, interval, config.delta)
        if reason is not None or treated.n >= config.max_n:
            return StepEffect(
                step=step,
                treated=treated,
                control=control,
                effect=effect,
                ci_low=interval.low,
                ci_high=interval.high,
                n_batches=batches,
                stop_reason=reason or "max_n",
                decision_conf=conf_for_decision,
                decision_ci_low=decision.low,
            )


def blame(step_effects: Iterable[StepEffect]) -> int | None:
    """The earliest step with a blame-worthy verdict, else `None`.

    The verdict travels with the `StepEffect` rather than being re-derived from
    the reported bound, because the decision was taken at the efficacy
    boundary's level for the look that made it, not at the reported level.
    """
    for effect in sorted(step_effects, key=lambda candidate: candidate.step):
        if effect.blameworthy:
            return effect.step
    return None


def _sampler_calls(effects: tuple[StepEffect, ...], control_mode: ControlMode) -> int:
    per_step_calls = sum(effect.n_batches for effect in effects)
    if control_mode == "per_step":
        return 2 * per_step_calls
    return per_step_calls + (1 if control_mode == "shared" else 0)


def estimate_run(
    tested_steps: Iterable[int],
    sampler: RerunSampler,
    config: SequentialConfig,
    control_mode: ControlMode = "shared",
    *,
    seed: int,
) -> RunEstimate:
    """Estimate every tested step of one run and name the blamed step.

    Every tested step is estimated, even after an earlier one is already
    blame-worthy: the caller may want the whole profile (the dashboard's heat
    stripe and forest plot do). A cost-minimising search can stop at the first
    blame-worthy step, since `blame` only ever looks at the earliest one.
    """
    steps = tuple(sorted(set(tested_steps)))
    if not steps:
        raise ValueError("tested_steps must not be empty")

    shared_control: ArmResult | None = None
    control_reruns = 0
    fork_step: int | None = None
    if control_mode == "shared":
        fork_step = steps[0]
        passes = _draw(
            sampler,
            fork_step,
            "control",
            config.max_n,
            _derive_seed(seed, fork_step, "control", 0),
        )
        shared_control = ArmResult(passes, config.max_n)
        control_reruns = config.max_n

    effects = tuple(
        estimate_step(
            step,
            sampler,
            config,
            seed=seed,
            control_mode=control_mode,
            shared_control=shared_control,
        )
        for step in steps
    )
    if control_mode == "per_step":
        control_reruns = sum(effect.control.n for effect in effects if effect.control is not None)

    return RunEstimate(
        step_effects=effects,
        blamed_step=blame(effects),
        control_mode=control_mode,
        control_fork_step=fork_step,
        treated_reruns=sum(effect.treated.n for effect in effects),
        control_reruns=control_reruns,
        sampler_calls=_sampler_calls(effects, control_mode),
    )
