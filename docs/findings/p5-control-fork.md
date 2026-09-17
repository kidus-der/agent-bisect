# P5 finding — a control forked before the planted step is not a control

- **Date:** 2026-09-17, during P5 stage A (offline). **No live P5 data exists yet.**
- **Status:** open. It changes what the pre-registered primary configuration measures, so
  the orchestrator decides, not P5.
- **Evidence:** `tests/test_p5_end_to_end.py`, two tests that record this rather than a
  feature:
  `test_a_control_forked_before_the_fault_does_not_reproduce_the_failure` and
  `test_the_shared_control_misses_the_planted_step_on_this_dataset`. Both run tau2's real
  orchestrator, environment and evaluator offline on airline task 1.

## What was found

A planted fault is a **perception** fault. `bench/inject.py` plants it with
`ReplaceToolResult(k, mutated)`: the agent is shown a different answer while the database
is left exactly as the real call left it (`attribution/interventions.py`, and
`adapters/tau2_inject.py`'s `fault_fork`). That is deliberate and it is what makes the
oracle fix well defined.

It also means the fault lives **in the recording, not in the world**. A fork of the faulted
run taken at step `j`:

- serves steps `<= j` from the tape, so a fault at `k <= j` is still shown;
- runs steps `> j` live, so a fault at `k > j` is **not** — the tool is re-executed against
  the real database and answers truthfully.

Measured on the toy item (planted step `k = 4`):

| control fork step | reproduces the recorded failure? |
|---|---|
| `j = 4` (at the fault) | yes — fails every time |
| `j = 0` (before the fault) | **no** — passes every time |

## Why it matters

The estimator's control is "restore at the step, change nothing, run the rest"
(`attribution/estimate.py`). With `control_mode="shared"`
(`docs/decisions/0005-shared-control.md`) **one** control arm is drawn, forked at the
**earliest tested step**, and every suspect is compared against it. The shared arm rests on

> `P(pass | restore at k, no intervention)` does not depend materially on `k`.

On this dataset that assumption does not merely bend, it breaks in a specific direction:
the function is a step function at the planted step. Forked before it, the control pass
rate is the *base run's* (high). Forked at or after it, it is the *failure's* (low).

The judge's shortlist usually contains a step earlier than the planted one — that is what
a shortlist is for — so the shared control is normally forked before the fault. Then

```
effect(k) = P(pass | truthful fix at k) - P(pass | shared control at j < k)
          ≈ base pass rate - base pass rate
          ≈ 0
```

and **no step is ever blamed**. The toy reproduces exactly that: with the same judge
shortlist, `control_mode="per_step"` blames the planted step and `control_mode="shared"`
blames nothing.

Per-step control is correct here, for both directions:

| tested step | treated | control (per-step) | effect |
|---|---|---|---|
| `i < k` (innocent, earlier) | resample at `i`, fault lost downstream → passes | fork at `i`, fault lost → passes | ≈ 0 ✓ |
| `k` (planted) | truthful fix at `k` → passes | fork at `k`, faulted result served → fails | ≈ 1 ✓ |
| `i > k` (innocent, later) | resample at `i`, fault on the tape → fails | fork at `i`, fault on the tape → fails | ≈ 0 ✓ |

## A sanity property worth adopting whatever is decided

**A control arm must reproduce the recorded failure.** A control fork that passes is not a
control for this failure; it is a different run. That is checkable per item, costs
nothing extra (the control arm is drawn anyway), and would have caught this before any
live spend. P5 should report the control pass rate per item beside every effect.

## Options, with a recommendation

1. **Per-step control as the P5 primary.** Correct on this dataset, and it is precisely the
   ablation `docs/decisions/0005-shared-control.md` says exists "to check the assumption on
   real runs" — the check has now been run, offline, and the assumption failed. Costs
   `2 x suspects x N` instead of `(suspects + 1) x N`: for m = 3, N = 16 that is 96 re-runs
   per item instead of 64, i.e. **+50% replay spend**. Requires a decision file recording
   the deviation from 0001 and this evidence, written before any live P5 data.
2. **Make the planted fault persist.** Plant it as a standing faulty tool (an injector on
   the environment that corrupts that one call's *returned message* every time it is
   executed, still leaving the database alone) rather than as a one-shot replaced result.
   Then every fork reproduces the failure, the shared control becomes valid again, the
   pre-registered cost saving is kept, and `TruthfulToolResult` keeps working because
   `adapters/tau2_truth.Tau2TruthResolver` re-executes on its **own** clean environment.
   This is also closer to what the failure is supposed to model — a tool that lies — and it
   composes naturally with the flaky world. It changes P3's collection, which is being
   built now.
3. **Report the null.** Run the pre-registered shared control, observe near-zero accuracy,
   and report it. Honest, but it would report a property of the forking semantics as if it
   were a property of the method, which is worse than useless to a reader.

**Recommendation: option 2 if P3 has not yet spent its collection budget, option 1 if it
has.** Option 3 only if neither is possible, and then the report must say plainly that the
number measures the control's fork point rather than the method.

## What P5 has done in the meantime

- `BaselineConfig.control_mode` is a suite-level knob, defaulting to the pre-registered
  `shared`; nothing has been silently changed.
- The offline end-to-end test asserts both behaviours, so whichever way this is decided the
  evidence stays in the suite.
- No live call has been made and no threshold has been touched.
