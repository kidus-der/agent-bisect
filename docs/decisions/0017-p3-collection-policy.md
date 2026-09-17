# 0017 — P3 collection policy: order, budget, stop rule, flaky set

- **Date:** 2026-09-17, **before any P3 collection ran**. Fixed now so that what
  was collected cannot be chosen after seeing what came out.
- **Status:** accepted (orchestrator decision).
- **Extends:** `0001-preregistration.md` (unchanged thresholds),
  `0012-p3-floor.md` (the gate is evaluated against 60),
  `0016-persistent-planted-fault.md` (the standing fault).

Nothing here changes a threshold, N, the keep rule or the strata. It fixes
**what order tasks are tried in, how much is spent, when to stop, and what the
flaky-world set is** — the choices that would otherwise be made under time
pressure with results already visible.

## 1. Task order

1. **airline**, all 50 tasks. Every airline task's reward is pure code (DB hash,
   actions, communicate checks) — no evaluator LLM call
   (`0010-replay-mechanism.md` §"The evaluator").
2. **retail tasks without `NL_ASSERTION` in their reward basis** — 74 of 114.
   Same property: the reward costs no model call.
3. **retail tasks with `NL_ASSERTION`** — 40 — last, and only if the target is
   still out of reach. Each adds an evaluator call per run *and* per re-run, and
   an LLM in the reward path adds variance to the very quantity the stability
   check and the keep rule are measuring.

## 2. Amortising the stability check

Four full re-runs are spent per passing base run before any fault is planted,
and they are reusable across every candidate from that run. So a stable base
run is worked harder: **up to 6 candidate attempts** (seeded, spread over the
three position buckets and the four fault types by the existing round-robin and
balancer), instead of 2 per bucket.

**The caps are unchanged**: at most 3 kept faults per base run, at most 1 per
position bucket per run. More attempts buy more chances that a bucket yields
*an* item; they cannot make one task dominate the dataset.

## 3. Stop rule

Collection stops at the **first** of:

- **120 kept items** in the plain world, or
- **10 hours of collection wall-clock**,

except that if fewer than **60** items are kept when 10 hours elapse, collection
continues until 60 and then stops. The hard ledger cap for phase P3 is 60,000
calls and stops it in any case. Then the manifest is frozen.

Wall-clock, not API time: it is the budget the run actually has.

## 4. The flaky-world set

P5's pre-registered gate includes "Flaky world: the no-snapshot baseline is
measurably worse (CI of the difference above 0)", which needs items collected in
a world where the two prefix modes disagree (`0011-flaky-world.md`).

- **When:** once the plain-world collection has **60 kept items** — not 120 —
  interleaved with further plain collection.
- **Where:** airline only.
- **How:** identical rules — stable base ≥ 0.75 over 4 re-runs *in the flaky
  world*, stratified k, four fault types, the standing `FaultInjector`, keep iff
  faulted pass ≤ 0.25 at N = 4, snapshot-mode forks. Reward by the canonicalised
  DB check of `0011`.
- **Target 30 kept items, minimum 20.** Written to `data/manifest_flaky.json`
  plus its `.sha256`, and **not split into dev/test**: nothing is tuned on it,
  so a split would be a split for its own sake.
- It draws on the same 10-hour budget. Priority when time is short:
  **60 plain → 20 flaky → more plain toward 120 → flaky toward 30.**

## 5. Re-run variation is measured, not assumed

Forks carry no per-re-run seed: τ² puts the run seed into every model request,
so re-pinning it breaks the hash-checked prefix, and injecting it into the live
suffix alone makes the forked recording unreplayable (both were tried; the P3
gate's offline replay caught the second). The N draws therefore differ **only by
provider non-determinism at temperature 0**, and P5's intervals are only as
meaningful as that variation is real.

So it is reported rather than assumed, in `runs/p3/status.json` extras and in
`docs/gates/P3.md`:

- the distribution of per-task pass rates over the 4 stability re-runs — how
  many base runs are 4/4, 3/4, 2/4, 1/4, 0/4;
- how often the 4 re-runs of one fork are **step-identical** to each other (the
  same action sequence) rather than diverging;
- the same for the faulted re-runs.

If the re-runs turn out to be near-deterministic, every interval P5 reports is
narrower than the truth, and that is a finding to state, not a number to
present.

## 6. Throughput

Pure engineering, no protocol change. P0/P1 were latency-bound (~13 s per call)
at concurrency 3–12, far under the measured limiter (agent 108 rpm, user sim
60 rpm ⇒ ≈ 8k calls/h). The collection runs enough work in flight that the
**limiter** binds rather than latency, backing off on 429/504 storms — the
existing process-wide limiter, retry policy and ledger are unchanged and are
what protect the account. The real rate is re-measured 30 minutes in and the
projection re-run from it.
