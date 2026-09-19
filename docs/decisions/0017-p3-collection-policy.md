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
2. **retail tasks whose reward costs no model call** — 74 of 114. Measured, not
   assumed from the basis: `NLAssertionsEvaluator` runs only when
   `NL_ASSERTION` is in `reward_basis` **and** the task actually lists
   `nl_assertions`. 112 of 114 retail tasks carry `NL_ASSERTION` in the basis
   but only **40** list assertions, so filtering on the basis alone would
   wrongly defer all but two of them.
3. **the 40 judged retail tasks** last, and only if the target is still out of
   reach. Each adds an evaluator call per run *and* per re-run, and an LLM in
   the reward path adds variance to the very quantity the stability check and
   the keep rule are measuring.

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

**Amendment, 2026-09-17, before the collection that produced the dataset.**
The replay seam was made thread-safe (`adapters/tau2_replay`: a `ContextVar`
dispatcher in place of a module-global rebind), so forks parallelise and the
collection runs several tasks at once inside one process rather than one task
per process.

One consequence has to be stated rather than discovered later: the fault-type
**balancer is global and draws in whatever order the threads finish**, so a
concurrent collection is reproducible in *what it tries* — which base runs,
which steps, which mutation, all seeded — but not in *which fault type each
kept item ended up with*. The balance property itself is unaffected, and so is
every threshold. A re-run from the same seeds would produce the same steps with
a possibly different assignment of the four types across them.



Pure engineering, no protocol change. P0/P1 were latency-bound (~13 s per call)
at concurrency 3–12, far under the measured limiter (agent 108 rpm, user sim
60 rpm ⇒ ≈ 8k calls/h). The collection runs enough work in flight that the
**limiter** binds rather than latency, backing off on 429/504 storms — the
existing process-wide limiter, retry policy and ledger are unchanged and are
what protect the account. The real rate is re-measured 30 minutes in and the
projection re-run from it.

## 7. Amendment, 2026-09-17 17:20 — after 0 of 9 candidates flipped

**Written before the relaunch**, from the first collection's own record
(`runs/p3/log.jsonl`). That run spent 17,184 calls in about two hours and kept
**1 item from 12 candidates**. Two separate causes, one a bug and one a
targeting failure. Thresholds, N, the keep rule, the fault types and the caps
are **unchanged**; what changes is how work is scheduled and where faults are
planted.

### 7.1 The bug: stability was measured on a broken path

Stability was four forks at step 0 with `Resample`. `Tau2Replayer.completion`
returns early on the `LIVE` path without telling its sink, so `next_step_idx`
never advances past the fork step and the tape keeps governing a run that has
gone live — with the cursor one step ahead of reality. **68 of these forks died
with `DivergenceError`**, the tape serving a recorded *agent* step to a
*user-simulator* request (`expected nemotron-3-super … got
nemotron-3.5-lightning`, airline tools vs `null`). Across three shards **one**
base run was ever found stable. The base recordings themselves are fine:
`airline-30-t0` replays offline in 17 steps at reward 1.0.

The offline suite could not catch it. `ScriptedLLM` is a pure function of the
message history, so a resampled turn returns exactly the recorded text and the
cursor stays in lockstep by luck; the bug needs a model whose resampled answer
differs.

**Change:** stability is now **four fresh recordings** of the task. A fork at
step 0 replays nothing, so it *is* a fresh run — with an extra request-hash
check over its own resampled first turn, a check that can only fire falsely.
Cost is identical and each re-run is now a first-class recording. (The engine
bug is reported separately; `Resample` remains a first-class intervention and
P5 uses it.)

### 7.2 Infrastructure was allowed to decide

138 tasks were dropped as "infra" and never retried — 68 divergences, 62
transport failures (`504` / timeout), 7 duplicate run ids from retries
re-deriving the same deterministic fork ids. Dropping a task because a provider
had a bad minute contradicts `0004` §3, under which an infra failure decides
nothing.

**Changes:** infra failures go back on the queue for up to **three passes**
with a backoff; tasks that never clear are **parked and counted**, never
silently dropped; a collection that parked work short of its target reports
that instead of `done`; the transport error mix is counted; work in flight
halves under a storm and creeps back up (AIMD); and retried attempts claim
fresh run ids.

### 7.3 Targeting: faults were planted where they could not bite

Of the three base runs that ever reached the candidate stage, **two (airline 26
and 34) require no write actions and check no communicated facts** — they are
scored almost entirely by the database being *unchanged*, so a misinformed
agent still passes. A perception fault there has nothing to break.

**Changes, all to *where* faults are planted, none to what is done to them:**

1. **Dependency-aware salience.** A value that re-appears in the arguments of a
   later call that *changes the world* outranks every other signal, because the
   others guess what the agent might use and this one records what it did use.
2. **Candidate order.** Attempts whose step carries such a value are tried
   first, as a stable sort over the existing bucket round-robin — the order
   changes, the set of attempts does not, and every stratum is still reached.
3. **Task order.** Three bands: cheap-to-score tasks that require writes (43
   airline, 73 retail), then cheap tasks that require none (8), then the 40
   judged retail tasks.

**Measured offline first, at zero API cost**, over the 183 recordings already on
tape: **691 of 1,580 tool steps (44%) carry a value that reaches a later write**,
and **115 of 183 recordings (63%)** have at least one such step. Under the old
targeting, better than half of all attempts were spent on steps whose value
never reached a write.

### 7.4 Why this does not bias the evaluation — and the threat that remains

The labels, the keep rule, N, the stability bar, δ, m and the split are
untouched. Nothing downstream can see how a site was chosen: the judge
baselines and Bisect both receive a failed recording and its steps, with no
record of why that step was picked. Selection changes which *candidates are
tried*, not how any of them is *scored*.

The honest threat to validity is this: **kept faults are, by construction,
consequential ones.** The dataset over-represents faults on values the run
acted on, and under-represents faults that a robust agent shrugs off. That is
what a planted-fault benchmark is for — a fault that changes nothing has no
causal step to find — but it means accuracy here is accuracy *on consequential
faults*, and it is not evidence about how often real agent failures are of that
kind. This is stated in `docs/gates/P3.md` and in the final report, alongside
the related point from `0016` that the shared control assumes a failure
reproducible from the fork point.

### 7.5 The clock

The 10-hour budget counts **productive collection time from the relaunch**. The
first two hours produced one item because of the `Resample` bug and the dropped
tasks, not because of the protocol, and are reported separately as such.

## 8. Amendment, 2026-09-17 21:00 — pacing, not protocol

Owner instruction: use more of the allotted NVIDIA capacity, without ever
exceeding it and without stalling. Nothing below changes a threshold, N, the
keep rule, the strata or the caps; it changes only how fast work is offered
and how failures are survived.

1. **The rate ceiling is discovered, not assumed.** P0 *bracketed* each model
   rather than locating it — the agent was clean at 120 rpm and 429'd at 160,
   the user simulator 429'd below 120 — and the limiter took the conservative
   end of each bracket. `core.rate_edge` now walks each model's rate up by
   +4 rpm after three consecutive clean windows and multiplies it by 0.8 on
   any window carrying two or more 429s, with the configured value as a hard
   floor and 1.5× it as a hard ceiling. It observes the **ledger**, which
   already records every call's model, outcome and latency, so it needs no
   hook in the request path and cannot itself fail a call. Every window is
   appended to `runs/limits/<model>.jsonl` and the settled rate is written
   back to `config/limits.toml` as `[limiter.measured_rpm_edge]`, so P5
   inherits it. **A 429 remains a signal, never a failure**: the retry policy
   is untouched.
2. **The limiter stays the binding constraint.** Threads in flight follow
   Little's law over the busiest model — rate × median latency ÷ 60, plus a
   quarter — capped at 48. Below that, latency decides the rate, which is the
   state P0 and P1 ran in. When one model's ceiling is what holds the whole
   collection back (the agent makes about three calls per user-simulator
   call, so the user simulator binds below a third of the agent's rate), the
   status file names it rather than leaving it to be inferred.
3. **It does not stall.** `scripts/supervise_p3.sh` relaunches the collection
   whenever it exits without having reached the stop rule, or whenever its
   own checkpoint clock stops moving for 20 minutes — a wedged connection
   looks alive, which is the failure a process check misses. Restarts are
   free because every finished unit is checkpointed. It stops for three
   reasons and says which: the stop rule fired, a human wrote `runs/p3/STOP`,
   or three crashes inside ten minutes, which is a bug rather than weather
   and is recorded as `state: failed` with the traceback's location.

One caution worth recording: a discovered ceiling is only valid for the
conditions it was discovered under. It is written back as
`measured_rpm_edge`, kept separate from P0's `per_model` measurement, so the
two never get confused.

## 9. Amendment, 2026-09-18 20:40 — after the budget ran out at 18 items

Written before the relaunch, from the run's own record. The collection
reached **18 kept items from 164 candidate verdicts (11%)** and then spent the
rest of a 70,000-call budget going nowhere. Four causes, none of them the ones
first suspected, and none of them a threshold:

1. **The budget was the stop, and the supervisor did not know it.** Every
   relaunch hit the ledger cap and exited cleanly in ~180 s; the supervisor
   treated that as a fault and relaunched, for hours. A spent budget and a
   rejected key are now **terminal** states: the supervisor writes
   `state: failed` and stops, and an exit with parked work waits ten minutes
   for one un-park pass, three times at most.
2. **The 1.5× ceiling did not cause storms.** Measured over 542 live windows,
   the agent model reached the 162 rpm ceiling with **zero windows carrying
   two or more 429s**; 429s were 161 of 70,000 calls (0.2%), 504s and timeouts
   48 between them. The ceiling and the decrease factor are therefore left
   alone — the hypothesis that they caused this is not supported by the data.
3. **The thread controller was chasing its own congestion.** It sized threads
   from the *current* p50 latency, so offering more work inflated latency,
   inflated latency asked for more threads, and the provider answered slower
   still: p50 went 9.5 s → 36 s while `retrying` outnumbered `ok` **43,378 to
   25,377**. Nearly two thirds of the budget went to retries. Threads are now
   sized from the *best* latency a model has shown, and a window completing
   under half of what it sent halves the answer.
4. **Re-queued tasks exhausted their run-id space.** Stability re-run ids were
   derived from the task, so each infrastructure pass re-derived the same ones
   and `free_run_id` gave up after twenty — `20 attempts already on the tape`,
   **34,108 times**, killing every affected task permanently. Stability re-runs
   are keyed in the journal by their base run, so their own ids need only be
   unique: they now carry a random suffix.

**Yield changes, within the existing caps.** Up to six candidate attempts per
stable base run (unchanged), plus a **second base-run trial** for a task whose
first recording failed or proved unstable — a task is the unit the split is
grouped by, so a second trajectory is a second chance at the *task*, not a
second sample of the same run. Late-position candidates are now tried before
early ones among the flowing candidates: 11 of the first 18 kept items were
early and **1** was late, and a stratum only reached when the budget holds out
is a stratum reported thin.

Nothing here touches N, the keep rule, the stability bar, the strata, the
per-run caps or the split. The threat to validity recorded in §7.4 still
stands and is not lessened by any of it.
