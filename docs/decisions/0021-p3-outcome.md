# 0021 — P3 outcome: a strict set that misses its floor, and a labelled extended set

- **Date:** 2026-09-18 22:05 MDT, written **before the freeze** and before any
  further collection under it. The numbers it quotes are the collection's own
  record at the time of writing.
- **Status:** accepted (orchestrator decision; the owner may override).
- **Applies:** `0001-preregistration.md` (P3 gate and the fixed method
  parameters), `0012-p3-floor.md` (the 60 floor), `0017-p3-collection-policy.md`
  (collection policy and its amendments), `0016-persistent-planted-fault.md`.

## Where the collection actually got to

- **292 candidates → 18 kept: a 6.2% keep rate**, at **3,738 P3 calls per kept
  item**.
- **158 of 164 tasks already have a base recording**; 119 base runs passed, 57
  proved stable, and those have largely been worked through their per-run caps.
  The pool is, for practical purposes, exhausted.
- Reaching 60 would cost roughly **157,000 further calls — 52 to 121 hours** at
  the throughput now measured.
- Strata of the 18: early 11, middle 6, late 1; `tool_error` 9, `wrong_value` 3,
  `missing_field` 3, `stale_record` 3; retail 12, airline 6.

## The decision

1. **Collect until 02:00 MDT**, bounded, under the fixed pacing controller and
   with the §9 yield changes (a second base-run trial per task, late-position
   candidates first). **No cap, threshold or keep-rule change** for the strict
   set.
2. **Freeze the strict manifest exactly as pre-registered** — faulted pass
   ≤ 0.25 at N = 4, stability ≥ 0.75, task-grouped 1:2 dev:test. The P3 gate is
   evaluated against the 60 floor and is expected to **FAIL on count**. That
   failure is recorded in `docs/gates/P3.md` with the whole funnel, not
   softened. `0001` is explicit: a gate that fails after real attempts stays
   failed, with the reason written down.
3. **Also freeze an extended set**, `data/manifest_extended.json`, **post hoc
   and labelled as such**: the strict items plus candidates whose faulted pass
   rate was ≤ 0.50 (2 of 4 re-runs failed). Those recordings are already on the
   tape, so this costs nothing further. It uses the **same task-grouped split**
   — a task lands on the same side in both manifests — and carries the same
   strata metadata.
4. **Then a bounded two-hour flaky-world collection** on airline under the
   rules of `0017` §4, frozen as `data/manifest_flaky.json` whatever it yields,
   with its count reported.

## Why the extended set is a secondary analysis and never the primary

Its threshold was chosen **after seeing the data**, which is exactly what
`0001`'s tuning discipline forbids for anything that decides a gate. It is
therefore not eligible to support the P3 gate or the headline P5 comparison,
and P5 must report it separately and say what it is.

What it is *for*: a 2-of-4 faulted re-run is a fault with a real but weaker
causal effect, and there is nothing unsound about measuring a method on weaker
effects — provided nobody pretends the bar was set in advance. Reported
honestly it strengthens the analysis, because a method that only works on
faults which flip a run 4 times out of 4 is a method with a narrower claim than
one that also works at 2 of 4.

## The finding this leaves behind

The headline is not the count. It is that **a single planted perception fault
rarely flips this agent**: 292 attempts on stable successes, each one a real
mutation of a real tool result at a step the value demonstrably flowed into a
later write, produced 18 runs that failed 3+ times in 4. The agent re-reads,
re-queries, and frequently recovers. That is a result about agent robustness
worth reporting in its own right, and it is the honest explanation for a
dataset that came in under its floor — not a collection that was run badly,
though it was also run badly twice before the bugs in §7 and §9 were found.

It also sharpens the threat to validity in `0017` §7.4: the kept items are the
faults that *did* flip a run, so they over-represent the consequential end of
an already-consequential selection. Accuracy measured on them is accuracy on
faults that matter, and the report says so.

## Outcome of the flaky-world attempt (added 2026-09-19, after it ran)

The bounded two-hour collection produced **3 kept items from 32 candidates**
and stopped with 37 tasks parked after three re-queue passes. The infrastructure
mix was **69 timeouts and 49 gateway 504s against a single 429** — it was
stopped by a provider that would not answer, not by the protocol and not by the
flaky world itself. 43 base runs, 7 stability checks, all 7 stable.

Frozen anyway as `data/manifest_flaky.json`, unsplit, sha256
`d951d8f2b1a11fbe792b73324eeac12a220afedec73158a31ad05ff34c8b3302`, and
labelled as a bounded, infrastructure-limited attempt. The three items are
spread one per position bucket (`tool_error` 2, `stale_record` 1).

**Three items cannot support the P5 flaky-world criterion.** That criterion —
"the no-snapshot baseline is measurably worse, with the CI of the difference
above 0" — needs an interval on a difference, and at n = 3 there is none worth
reporting. The honest statement is that **the ablation was not collected**, not
that it was collected and came out small. P5 should say so rather than compute
a number from three points.

What remains true, and is evidenced separately and offline, is the *mechanism*
the ablation was meant to demonstrate: in the flaky world a snapshot restore
reproduces the recorded database hash at **100%** of tool steps while
re-executing the same calls later reproduces **0%** (`tests/test_tau2_flaky.py`,
measured over 10 recorded runs and 30 tool steps). That is a property of the
engine, shown deterministically without a provider; it is not a substitute for
the live ablation, and the report distinguishes the two.
