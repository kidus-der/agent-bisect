# P5 — what the frozen test split can resolve, computed before spending

- **Date:** 2026-09-18, **before any live P5 call**. Manifests frozen by P3:
  `data/manifest.json` (strict, 18 items, sha256 `2604e213…`) and
  `data/manifest_extended.json` (secondary, 26 items, sha256 `6fefff59…`).
- **Reproduce:** `uv run python scripts/p5_power.py` — offline, deterministic, uses the
  real `bench.metrics.paired_bootstrap_gap` over the real task-cluster structure.

## The question

`docs/decisions/0001-preregistration.md` sets the P5 gate: Bisect ≥ best judge **+ 15
points**, with the 95% paired bootstrap CI of the gap above 0. P3's collection yielded 18
items (gate FAILED on count, `docs/decisions/0021-p3-outcome.md`), giving a **test split of
12 items across 10 task clusters**. Before spending ~60,000 calls it is worth knowing what
that can detect.

## Result: the gate is a test of a large effect, not of a 15-point one

Power to pass **both** gate criteria, 400 simulations, paired on shared item difficulty:

| true gap | judge 0.10 | judge 0.25 | judge 0.40 |
|---|---|---|---|
| **+15 points (the bar)** | **0.14** | **0.12** | **0.09** |
| +25 points | 0.40 | 0.37 | 0.37 |
| +40 points | 0.82 | 0.79 | 0.76 |
| +55 points | 0.95 | 0.95 | 0.96 |

The binding criterion is the interval, not the point estimate: a true 15-point gap produces
an observed gap ≥ 15 points about half the time, but a CI clearing 0 only ~12% of the time.

The crispest statement of the same fact: **the smallest result that clears the CI is Bisect
right on 4 of 12 items where the judge is right on none** (CI `[+0.077, +0.636]`). Anything
less cannot clear it, however the point estimate falls.

The extended set (17 test items, 14 clusters) is better but not sufficient: 0.21–0.26 power
at the bar, 0.60 at +25 points, 0.94 at +40.

## What this commits us to, stated in advance

1. **The gate is not changed.** Thresholds are never lowered
   (`docs/decisions/0001-preregistration.md`). It will be run as written and the verdict
   reported as it falls.
2. **A FAIL will be reported as uninformative about the pre-registered effect size.** At
   9–14% power, failing to clear a 15-point gap is the expected outcome *whether or not*
   such a gap exists. The report must say that, and must not present a FAIL as evidence
   that Bisect does not beat the judge.
3. **A PASS is informative, and implies a large effect.** Because only a gap of roughly 40+
   points clears the CI with any reliability, a pass is evidence of a large difference, not
   a marginal one. That is the one direction in which this n can carry a conclusion.
4. **The minimum detectable effect is reported beside the gate verdict**, along with this
   table, so a reader can see what the test could have found.
5. **No post-hoc rescue.** Not pooling the strict and extended sets to raise n, not
   switching to an unclustered bootstrap to narrow the interval, not selecting the
   comparator after seeing it. Each would buy significance by weakening the design.

## Why this happened, and it is the same cause as P4

The +15-point bar and the 120-item target were both fixed in `0001` without a power
calculation, so nothing connected them: 120 items would have given ~0.55 power at the bar,
and the 60-item floor of `0012` about 0.3. The collection then returned 18. **Both the
original target and the floor were already too small for the bar they were paired with** —
the shortfall made an existing problem visible rather than creating it.

`docs/decisions/0009-p4-outcome-and-p5-primary.md` recorded exactly this for P4 ("the 0.95
bar was set without a power calculation"). Two phases failing criteria that were never
reachable at the planned n is the finding, and it belongs in the report next to the
numbers, not in a footnote.

## Recommendation to the orchestrator

Run P5 as pre-registered on the strict test split and report the verdict with §2–4 above
attached. Do **not** spend on raising n: P3's task pool is exhausted at 158 of 164 tasks
(`0021`), so more items are not available at any price.

The comparison that this dataset *can* support is the **flaky-world ablation** — snapshot
versus no-snapshot Bisect on the same items — because it is a paired comparison of two
mechanisms on a difference that is structural rather than marginal. That, plus recall@m and
cost per diagnosis, is where P5's evidence will actually be.
