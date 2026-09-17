# 0008 — O'Brien–Fleming efficacy boundary for interim blame decisions

- **Date:** 2026-09-17, written and committed **before the corrected gate was run**.
- **Status:** accepted. Amends the sequential stopping rule of
  `0001-preregistration.md`; everything else in that file is untouched.
- **Trigger:** P4's first result (`docs/gates/P4.md`, FAILED at 0.890). All nine
  false early blames fired at the **first look, n = 4**, and the per-step
  false-positive rate on truly-null steps was 0.63% sequentially against 0.00%
  at a single fixed look. That is not bad luck; it is a defect in the method as
  pre-registered.

## The defect

The pre-registered plan looks at a nominal 95% interval up to four times and
acts on the first look that clears δ. A 95% bound checked four times is not a
95% bound: under repeated looks the probability that *some* look crosses is far
above the nominal level. The earliest-step rule then makes this worse than
usual, because a false crossing at an early null step is **irreversible** — no
amount of later evidence at the true step can overturn it.

Correcting this is not tuning. It fixes a stated statistical error, it is
decided before re-running, and it can only make blame *harder*, never easier.

## Decision

Efficacy (blame) decisions at interim looks use an **O'Brien–Fleming-type
boundary for K = 4 equally spaced looks at overall two-sided α = 0.05**. At
look `j` the step is blame-worthy only if the Newcombe interval computed **at
that look's confidence level** has a lower bound above δ.

| look `j` | n per treated arm | critical `z` | two-sided nominal α | confidence level used for the decision |
|---|---|---|---|---|
| 1 | 4 | 4.049 | 0.00005 | 0.99995 |
| 2 | 8 | 2.863 | 0.00420 | 0.99580 |
| 3 | 12 | 2.337 | 0.01944 | 0.98056 |
| 4 | 16 | 2.024 | 0.04297 | 0.95703 |

The final look (N = 16) therefore uses z = 2.024 — **stricter** than the nominal
1.96 — which is the price paid for having looked three times already.

Two things are deliberately *not* changed:

- **Futility ("cleared") stopping is unchanged:** a step stops as cleared when
  its **nominal 95%** interval has an upper bound at or below δ. Stopping for
  futility cannot create a false blame, so it needs no multiplicity control.
- **The reported interval is unchanged:** a step's published effect interval
  remains the **nominal 95% Newcombe CI at its final n**. That is what the
  coverage criterion measures and what the dashboard draws. Only the *decision*
  consults the boundary. Reporting a boundary-widened interval would make
  "coverage of a 95% CI" mean something different from phase to phase.

## Verification of the constants

The boundary is O'Brien & Fleming (1979), *Biometrics* 35(3):549–556, in the
form tabulated by Jennison & Turnbull (2000), *Group Sequential Methods with
Applications to Clinical Trials*, Table 2.3, which gives the constant
`C_B(4, 0.05) = 2.024`. Checked three ways rather than taken on trust:

1. **Internal form.** OBF sets `z_j = C · sqrt(K / j)`. With C = 2.024, K = 4:
   4.0480, 2.8624, 2.3371, 2.0240 — the quoted 4.049, 2.863, 2.337, 2.024 to
   within rounding of the published constant.
2. **Published nominal levels.** The two-sided α implied by those z values is
   0.00005, 0.00420, 0.01944, 0.04297, matching the standard K = 4 OBF table.
3. **Overall α, computed here.** On the score scale the OBF boundary is a
   *constant* `b = C·sqrt(K) = 4.048`, so the overall two-sided α is
   `P(max_j |S_j| >= b)` for a random walk with unit normal increments,
   j = 1..4. Numerical integration of the restricted density (grid 5e-4) gives a
   non-crossing probability of 0.94997, i.e. **overall two-sided α = 0.0500**.

## Explicitly unchanged

δ = 0.10 · batch = 4 · max N = 16 · the earliest-step blame rule · the shared
control and its fork point (`0005`) · every generative parameter of the
synthetic model (`0006`) · the master seed 20260917 · both gate thresholds
(planted step found ≥ 0.95; coverage in [0.92, 0.98]) · the definition of the
gated coverage number (fixed N = 16, single look, nominal 95%).

Nothing here was selected by looking at outcomes: the boundary, its constants
and the confirmation seed below were all fixed in advance of the re-run.

## Implementation and reporting

- `SequentialConfig(efficacy_boundary=...)`, with `"obf"` the new default and
  `"none"` (the original, uncorrected behaviour) kept selectable so both can be
  reported side by side. `"obf"` is defined only for a plan with exactly four
  looks and raises otherwise, rather than silently extrapolating a constant that
  was verified only for K = 4.
- The **fixed N = 16 diagnostic pass takes a single look**, so it has no
  multiplicity to correct and keeps `"none"` (nominal 95%). Its numbers,
  including the gated coverage, are therefore unchanged by this decision.
- Because the decision and the reported interval now use different confidence
  levels, the blame-worthy verdict travels with the `StepEffect` that made it
  (`StepEffect.blameworthy`) instead of being re-derived from the reported
  bound. `blame()` consequently takes only the step effects.
- **Confirmation seed: 20260918** (master seed + 1), declared here, to be run
  once and reported read-only alongside the master-seed result. It is evidence
  that the outcome is not seed-specific; the gate verdict is decided on the
  master seed alone.

## Expected effect, stated before measuring

This should remove most of the ~3 points lost to peeking and cannot help the
~8-point power shortfall at N = 16 — a stricter final look may cost a little
more. **The gate is still expected to FAIL**, and if it does it stays failed:
the N = 16 power ceiling is structural and gets reported, not engineered away.
This is fix attempt 1 of 3, and no further attempt will be made unless an actual
bug is found.
