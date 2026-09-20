# 0022 — P5 scope: no re-run-live in the plain world

- **Date:** 2026-09-20, decided by the orchestrator at 05:30, recorded before the relaunch
  that applies it. Dev-split forks bought before this point are unaffected and remain on the
  tape; no result had been published.
- **Status:** accepted. A deviation from `docs/decisions/0018-p5-budget.md` §3, narrowing it.

## Decision

1. **`rerun_live` is not run on the plain world at all** — not on test (0018 §3 already said
   that) and now not on dev either.
2. **`rerun_live` is run in full on the flaky set**, all 3 items, both arms.
3. **`no_control` stays derived** from Bisect's treated draws (0018 §2). Both judge
   protocols still run on every item.
4. **N = 16 and the O'Brien–Fleming primary are unchanged.** No pre-registered estimator
   parameter moves.
5. Order: strict dev → `0014-p5-freeze.md` → strict test → flaky → gate and evidence →
   **extended only if the measured pace projects under ~4 h**, otherwise reported as *not
   run (time)*, it being secondary by `docs/decisions/0021-p3-outcome.md`.

## Why

0018 §3 kept `rerun_live` on dev as "empirical confirmation that snapshot and re-run-live
agree when tools are deterministic". Two things changed after it was written.

- **The cost is real and the claim is a tautology.** Measured on live P5 traffic, a
  user-simulator turn takes **76 s** (agent turns 9.7 s, both drifting far higher under
  load). `rerun_live` buys a second full set of 64 forks per item, so it doubles the split's
  wall-clock — to confirm an equality that holds by construction on a deterministic domain.
- **Its one load-bearing use is gone.** The flaky ablation is where the difference is
  supposed to appear and where the pre-registered criterion lives. `data/manifest_flaky.json`
  froze at **3 items** after a bounded collection lost 69 requests to timeouts and 49 to
  gateway 504s, and P3 reports the ablation as **not collected**
  (`docs/decisions/0021-p3-outcome.md`). So the plain-world confirmation now supports
  nothing downstream.

## What this costs, stated plainly

The plain world no longer carries *any* empirical evidence that snapshot and re-run-live
agree — it is asserted from the determinism of τ²'s airline and retail tools, not shown.
Anyone who doubts that determinism should doubt this too. Two things stand in its place,
and neither is the live ablation:

- the offline, deterministic engine measurement (`tests/test_tau2_flaky.py`): in the flaky
  world a snapshot restore reproduces the recorded database hash at **100%** of tool steps
  while re-executing the same calls reproduces **0%**, over 10 runs and 30 tool steps;
- the 3-item flaky run, reported as a **paired mechanism comparison without an interval**.

The P5 report must say that the flaky-world criterion of
`docs/decisions/0001-preregistration.md` is **not decidable at n = 3** — not that it was
decided and came out small.

## Bugs found before any number was published

Recorded here because they are evidence about the process, and both would have produced
confident wrong numbers:

- **Shared fork ids.** `rerun_id` hashed (parent, arm, step, seed, draw) and not the prefix
  mode, so Bisect's snapshot forks and `rerun_live`'s forks collided on the tape. Bisect
  ran first and `rerun_live` "resumed" its results, which would have reported the two
  mechanisms as identical — the exact comparison the flaky criterion rests on.
- **`no_control` bought live.** It was running as a third full set of forks despite 0018 §2
  saying to derive it, so a third of every evaluation paid for a treated arm already on the
  tape.
- **Orphaned evaluations.** Killing the supervisor left its `bisect eval` child running, so
  up to three evaluations shared one tape under one seed, each treating the others' forks
  as resumable work. A pid lock now refuses a second evaluation against the same runs
  directory.
