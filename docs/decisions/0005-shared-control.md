# 0005 — One shared control arm per run

- **Date:** 2026-09-17, written before any P4 measurement.
- **Status:** accepted; implements the pre-registered estimator of `0001-preregistration.md`.

## Decision

A run under test gets **one control arm**, shared by every tested step, rather than a
fresh control arm per step. The shared control is forked at the **earliest tested step**
and drawn to the full `max_n` (16) in a single batch. Each tested step's effect is

```
effect(k) = P(pass | fix step k) − P(pass | step k as recorded)
```

with the treated arm sampled sequentially at step `k` and the control arm held fixed.
`control_mode="per_step"` is also implemented, for the ablation that checks the
assumption below on real runs.

## Why

Cost. The brief's budget is `1 + (suspects + 1) × N × calls_per_rerun` — the `+1` **is**
the shared control. With a per-step control, testing `s` steps costs `2 × s × N`
re-runs; with a shared control it costs `s × N + N`. On a 20-step run at N = 16 that is
640 re-runs versus 336.

## What "control" means, and the assumption this buys

The control for step `k` is: *restore the world at `k`, apply no intervention, run the
rest*. The prefix of a recorded failure is fixed, so the control arm is fully determined
by its **fork step** — there is nothing to vary but where you re-enter the run. The
shared control therefore has to pick one fork step, and it picks the earliest tested one
(the most conservative choice: it re-runs the largest suffix, so it is the control that
has the most opportunity to recover by luck).

This is only valid under:

> **Assumption (flat control).** For a recorded failure, `P(pass | restore at k, no
> intervention)` does not depend materially on `k` over the tested range.

The assumption is plausible because every control fork replays the same recorded prefix
and then samples the same policy on the same failing trajectory; nothing about "where you
re-entered" changes the agent's situation. It is *not* guaranteed: if the run has a
recovery point late in the trajectory, a control forked late could pass more often than
one forked early, which would bias every step's effect in the same direction (too
positive if the shared, earliest control is pessimistic).

Consequences, stated plainly:

1. **P4 does not test this assumption.** The synthetic generator of
   `0006-p4-synthetic-design.md` builds control as a single per-run pass probability, so
   flat control holds exactly by construction. P4 measures the estimator's statistics,
   not this modelling choice.
2. **P5 must test it.** The `control_mode="per_step"` ablation on real recorded failures
   is where flat control is checked: if per-step and shared controls disagree beyond
   noise, the shared control is wrong for that domain and the cost saving is not
   available.
3. **Shared control correlates the tested steps.** Every step's CI uses the same control
   draws, so a control arm that is unlucky low shifts *all* effects up together. This is
   the mechanism by which an early, truly-null step can be falsely blamed, and it is the
   main statistical risk to the earliest-step rule. It is measured, not assumed away:
   the P4 gate reports the miss breakdown (blamed earlier / later / none).

## Interval arithmetic

Per arm: Wilson score interval. For the difference of the two independent proportions:
Newcombe's hybrid score interval (Newcombe 1998, "Interval estimation for the difference
between independent proportions", method 10), built from the two Wilson intervals:

```
low  = (p̂₁ − p̂₂) − sqrt((p̂₁ − l₁)² + (u₂ − p̂₂)²)
high = (p̂₁ − p̂₂) + sqrt((u₁ − p̂₁)² + (p̂₂ − l₂)²)
```

Chosen over Wald because arms of N ≤ 16 with proportions near 0 or 1 are the normal case
here, exactly where Wald intervals fail (zero width at 0/n and n/n) and Wilson/Newcombe
keep their nominal coverage.

## Sequential stopping and the multiple-looks problem

Batches of 4 per arm to `max_n = 16`; a step stops early when its CI lower bound exceeds
δ = 0.10 (blame-worthy) or its CI upper bound is at or below δ (cleared). Repeated looks
at the same interval inflate error rates, so the P4 evidence reports coverage **twice**:
once for a fixed N = 16 design with a single look (the pre-registered gate number) and
once for the CI as the sequential procedure actually reports it at its stopping point.
No adjustment is applied to the interval; the cost of peeking is measured and published
rather than corrected for.
