# 0006 — P4 synthetic generator: parameters fixed before measurement

- **Date:** 2026-09-17, written and committed **before the P4 gate was run for the first
  time**. Nothing in this file may be changed in response to a gate result; see the rule
  in `0001-preregistration.md`.
- **Gate being served:** P4 — "On 200 synthetic runs (zero network): planted step found
  ≥ 95%; 95% CI coverage of the true effect between 92% and 98%."

## The generative model

A synthetic run is a `FakeRunSpec`: `n_steps`, a planted causal step `k*`, a control pass
probability `c`, and a true treated pass probability for every step. A
`ScriptedSampler` turns a spec into a `RerunSampler`: `sample(step, arm, n, seed)` draws
`n` independent Bernoulli outcomes at `c` for `arm="control"` and at the step's treated
probability for `arm="treated"`. Steps are 1-indexed, matching the brief's "step 7 of 12".

| Parameter | Value | Justification (written before any result) |
|---|---|---|
| `n_steps` `S` | uniform on {8, …, 30} | The brief's worked example is 12 steps; recorded τ² airline/retail trajectories in that range. Wide enough that multiple testing over ~20 steps is exercised, which is the honest stress on the earliest-step rule. |
| planted step `k*` | uniform on {2, …, S−3} | At least one earlier step, so a "blamed an earlier step" miss is *possible* and gets counted. At least three later steps, so partial-recovery steps exist — the situation that makes the earliest-step rule necessary rather than decorative. |
| control rate `c` | uniform on [0.00, 0.15] | P3 keeps a planted fault only if its faulted pass rate is ≤ 0.25 at N = 4; the brief's demo control is 0.10. The range spans "never recovers" to "occasionally passes by luck". |
| treated rate at `k*` | uniform on [0.60, 0.95] | Fixing the planted fault restores a run that P3 required to be stable at pass ≥ 0.75. The floor is set *below* that, at 0.60, deliberately: the gate must not be measured only on easy cases. Brief demo: 0.88. |
| later steps `k*+j` (j ≥ 1) | `max(c, r · 0.65^(j−1))`, with `r` uniform on [0.15, 0.45] drawn once per run | "Later fixes can partially recover" (brief, fact 1). The brief's demo tail is 0.40, 0.30, 0.18, 0.12, 0.10 against `c` = 0.10 — a ratio of ≈ 0.65 decaying to the control rate. |
| earlier steps `< k*` | exactly `c` | Fixing a step before the fault changes nothing causal, so its true effect is exactly 0. |

Ground truth per step: `true_effect(k) = treated_prob(k) − c`. By construction the
earliest step whose true effect exceeds δ = 0.10 is exactly `k*`, so the pre-registered
blame rule and the label agree — the gate measures estimation error, not a definitional
mismatch.

Randomness: `numpy.random.default_rng([master_seed, run_index])` per run spec, and a
per-draw seed derived with BLAKE2b from `(sampler_seed, step, arm, draws_taken)`. No
global RNG state, no `numpy.random.seed`.

## Fixed named fixture

`BRIEF_12_STEP_RUN` reproduces the brief's worked example verbatim: 12 steps, planted
step 7, control 0.10, treated
`[0.10, 0.12, 0.12, 0.18, 0.10, 0.10, 0.88, 0.40, 0.30, 0.18, 0.12, 0.10]`. Note this
fixture carries small noise on the pre-`k*` steps (0.12, 0.18) that the generator above
does not; it is a UI/demo fixture, not part of the 200-run gate sample.

## The gate run

- **Master seed: 20260917.** Fixed here, before the first run. 200 runs.
- Every step of every run is tested — no judge shortlist at P4, so the multiple-testing
  burden is the worst case (~20 tested steps per run).
- Estimator config as pre-registered: `batch = 4`, `max_n = 16`, `δ = 0.10`,
  `conf = 0.95`, `control_mode = "shared"` (see `0005-shared-control.md`).
- Two passes over the same 200 runs, with the same sampler seeds:
  1. **sequential** — `batch = 4`, the procedure as it would actually run;
  2. **fixed N = 16** — `batch = 16`, one single look, no early stopping.

## The three numbers, and which one is the gate

1. **planted-step-found rate** — fraction of the 200 runs where `blame()` on the
   *sequential* pass equals `k*`, with a Wilson 95% CI. **Gate: ≥ 0.95.**
2. **coverage, fixed N = 16** — over all tested (run, step) pairs of the fixed pass, the
   fraction whose reported 95% CI contains the true effect. **This is the pre-registered
   gate number. Gate: within [0.92, 0.98].**
3. **coverage, sequential** — the same fraction for the CI as reported by the sequential
   procedure at whatever N it stopped at. Reported for comparison only, *not* gated,
   because repeated looks are known to distort it; publishing the distortion is the
   point.

Also reported, ungated: mean re-runs per run for each pass and the saving from early
stopping; and the miss breakdown (blamed an earlier step / a later step / no step).

## Discipline

If the gate fails, up to three fix attempts are permitted, and only for genuine bugs in
the estimator or the gate script. The thresholds, δ, N, the batch size, the parameters in
the table above and the master seed are **not** touchable after a result has been seen. A
failure that survives three bug-fix attempts is published as FAILED with its analysis.
