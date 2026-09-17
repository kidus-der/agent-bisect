# 0012 — The P3 fallback floor is triggered: the gate is evaluated against 60

- **Date:** 2026-09-17, **before any P3 data existed**. No base run had been
  recorded for the collection, no candidate had been tried and no item had been
  kept when this was decided. The only inputs were P0's measured throughput and
  the cost model in `scripts/p3_projection.py`.
- **Status:** accepted (orchestrator decision).
- **Applies:** `docs/decisions/0001-preregistration.md`, P3 gate — "≥ 120
  labelled failures. Fallback floor: 60, used **only if** P0's measured
  throughput projects the 120-target collection past 10 h of API time. Which
  one applied is recorded."

## The rule, applied

The rule turns on a projection, and a projection is only as good as its call
count. P0's own "5.9–8.8 h" came from the brief's order-of-magnitude guess of
8–12k calls for P3 (`docs/brief/summary.md` §6). That guess **omits the
stability check**: every base run that passes is re-run four more times before
any fault is planted, which is four *full* runs per passing task and, at the
measured shape, roughly 4 of the ~17 run-equivalents a surviving task costs.

Re-derived bottom-up in `scripts/p3_projection.py`, from 23 recordings actually
on the tape (**23.2 model calls per run**) and P0's measured **1,362 calls/h**,
with P0's airline pass rate 0.60 and an assumed 0.70 of passing runs clearing
the 0.75 stability bar, two candidate attempts per position bucket:

| keep rate | tasks needed | calls | API hours |
|---|---|---|---|
| 20% | 265 | 51,840 | **38.1** |
| 35% | 165 | 32,316 | **23.7** |
| 50% | 127 | 24,883 | **18.3** |

The keep rate cannot be known before collecting, so the rule is applied to the
whole range. **Every** value exceeds the 10 h budget — the cheapest case is
18.3 h, nearly twice it.

## The decision

**The fallback is triggered. The P3 gate is evaluated against ≥ 60 labelled
failures**, not 120.

Two things this does *not* mean:

1. **Collection still aims at 120.** More labelled failures are never worse, and
   the floor is a gate threshold, not a target. Collection continues past 60
   while time allows, under the stop rule in `0017-p3-collection-policy.md`.
2. **Nothing else moves.** N = 4, the keep rule (faulted pass ≤ 0.25), the
   stability bar (≥ 0.75), the strata, δ, m and the 1:2 split are unchanged.
   `0001`'s rule that thresholds are never lowered after seeing results is
   intact: this threshold was pre-registered *with* its fallback, and the
   fallback's own condition was evaluated before any result existed.

The final report states plainly which number was reached, that the floor
applied, and why — including that P0's published projection was optimistic
because of the omitted stability check. A dataset smaller than the headline
target is a cost finding, not a quiet adjustment.

## Effect on the statistics

60 items instead of 120 roughly doubles the width of every proportion interval
P5 reports: a step accuracy near 0.85 has a 95% Wilson interval of about ±0.09
at n = 60 against ±0.06 at n = 120, and the test split (2/3 of the items) is
what P5's gate is computed on. The P5 bar — "Bisect step accuracy ≥ best judge
+ 15 points, with the 95% bootstrap CI of the gap above 0" — is unchanged and
is simply harder to clear with fewer items. That is the honest consequence of
the budget and is reported as such rather than compensated for.
