# P5 — what a live run will cost, and where the cost actually is

- **Date:** 2026-09-17, end of P5 stage A (offline). No live P5 call has been made.
- **Inputs:** P0's measured throughput (judge `nvidia/nemotron-3-ultra-550b-a55b` median
  7.5 s, ≥ 120 rpm measured, limiter 108; agent 108 rpm; user simulator 60 rpm; **21.4 LLM
  calls per full airline task**) and the estimator's own arithmetic, computed rather than
  assumed (`scripts/gates/p4.py`, `attribution/estimate.py`).

## Finding 1 — sequential stopping saves much less than the design implies

Computed exactly from `newcombe_diff_interval` at δ = 0.10, shared control at N = 16:

| situation | interval | stops? |
|---|---|---|
| innocent step, treated 0/4 vs control 0/16 | nominal CI high **0.490** | no |
| innocent step, treated 0/8 | high **0.324** | no |
| innocent step, treated 0/12 | high **0.242** | no |
| innocent step, treated 0/16 | high **0.194** | **no** |
| decisive step, treated 4/4, look 1 (OBF conf 0.99995) | decision low **+0.050** | no |
| decisive step, treated 8/8, look 2 (OBF conf 0.99580) | decision low **+0.391** | **yes** |

Two consequences, neither of them a defect — this is what the pre-registered numbers imply:

1. **Futility stopping never fires at δ = 0.10.** A Wilson upper bound on 0 successes in 16
   draws is 0.194, still above δ, so a step that is *perfectly* innocent still runs to
   `max_n`. Clearing a step at δ = 0.10 would need roughly N ≥ 35 per arm.
2. **A perfect decisive step blames at look 2, not look 1.** The O'Brien–Fleming boundary at
   the first look (nominal 0.99995) is stricter than 4/4 vs 0/16 can clear.

So the realistic cost is `(m + 1) x N` forks per item, minus 8 forks when the shortlist
actually contains the culprit: **56 forks per item at m = 3, N = 16**, against a worst case
of 64. Budget for the worst case.

## Projection

A fork replays its prefix for free and samples the suffix live. With fault steps stratified
early/middle/late, a fork costs on average a little over half a run: **≈ 12 LLM calls**.

| line | per item | 80-item test split | 40-item dev split |
|---|---|---|---|
| judge, all-at-once (incl. ~5% repair retries) | ~1 call | 84 | 42 |
| judge, step-by-step (~30 candidate steps, stops at the first yes) | ~20 calls | 1,600 | 800 |
| **Bisect** replay, m = 3, N = 16, shared control (64 forks x 12) | ~768 calls | 61,440 | 30,720 |
| **rerun_live** replay (same shape) | ~768 calls | 61,440 | 30,720 |
| **no_control** replay — **0, it is a re-analysis of Bisect's treated arms** | 0 | 0 | 0 |

At the agent's 108 rpm (and the user simulator's 60 rpm on roughly half the calls, which
is the tighter constraint), **~63,000 calls is ~9.7 h of API time**. Running all three
replay methods live on both splits is **~185,000 calls, ~28 h**. That does not fit.

## The five levers, largest first

1. **`no_control` costs nothing if it is derived.** It is `effect := treated pass rate` over
   the *same* treated draws Bisect already bought. `bench/costcurve.RecordedSampler` already
   replays stored draws through the estimator, so the ablation is a re-analysis, not a
   second experiment. **Saves ~33% of all replay spend.** Recommended unconditionally.
2. **N.** Cost is linear in N and nothing else changes. N = 8 halves the replay bill
   (~4.9 h for the test split). It is a deviation from the pre-registered max N = 16 and
   needs a decision file written before any live data; the honest framing is that N = 16
   was never justified by a power calculation either (`docs/decisions/0009`).
3. **`rerun_live` belongs in the flaky world, not the deterministic one.**
   `docs/brief/summary.md` §8 says the two agree by construction on deterministic τ²; the
   ablation only carries information where the world is flaky. Running it on the
   deterministic test split buys a number everyone already knows. **Saves another ~33%.**
4. **The step-by-step judge is 20x the all-at-once judge** but still only ~3% of the bill
   (1,600 calls vs 61,440). Not worth cutting; cut it only if judge wall-clock is binding.
5. **Items.** The gate is defined on the test split, so its size is the last thing to touch.

With levers 1 and 3, the test split is **~63,000 calls / ~9.7 h** and the dev split
**~31,500 / ~4.9 h**, plus the flaky-world comparison (2 arms x 40 items x 768 =
~61,000 calls / ~9.4 h). **Total ≈ 156,000 calls, ≈ 24 h.** Adding lever 2 (N = 8) brings it
to **≈ 78,000 calls, ≈ 12 h**.

## What changes if the control-fork decision goes the other way

`docs/findings/p5-control-fork.md` may move the primary to `control_mode="per_step"`, which
costs `2 x m x N = 96` forks per item instead of 64: **+50% on every replay line above**.
With levers 1 and 3 and N = 16 that is ~35 h; with N = 8, ~17 h. If option 2 (a persistent
faulty tool) is taken instead, the shared control stays valid and these numbers stand.
