# 0018 — P5 budget: what is measured live, what is derived, what is caveated

- **Date:** 2026-09-17, written **before any live P5 data exists** — no judge call, no
  re-run, no evaluation on either split.
- **Status:** accepted.
- **Why now:** `docs/findings/p5-cost.md` showed the pre-registered plan run in full is
  ~185,000 calls / ~28 h, which does not fit. These are the spending decisions that make it
  fit. None of them changes a threshold, an estimator parameter or a gate.

## 1. The estimator is untouched

δ = 0.10, batches of 4, max N = 16, m = 3, shared control, earliest-step rule, O'Brien–
Fleming boundary primary. The `efficacy_boundary = "none"` sensitivity is **derived from
the same draws** and costs nothing extra. Exactly as
`docs/decisions/0001-preregistration.md` and `0009-p4-outcome-and-p5-primary.md` fix them.

## 2. The no-control ablation is derived, not re-run

`no_control` is `effect := treated pass rate`. Its treated arm is *by definition* the arm
Bisect already bought, so it is a re-analysis of stored draws
(`bench/costcurve.RecordedSampler`), not a second experiment. **Zero extra spend.** It is
still reported as a method, because what it demonstrates — blaming a step the control would
have cleared — is a property of the procedure, not of the data.

## 3. re-run-live: dev only in the plain world, in full in the flaky world

On the plain world the standing fault is part of the world
(`docs/decisions/0016-persistent-planted-fault.md`) and τ²'s tools are deterministic, so
snapshot and re-run-live agree **by construction**. It is run on the **dev split only**, as
an empirical confirmation that they do — a result worth having and not worth buying twice.

On the **flaky world both arms run in full**: Bisect (snapshot) and re-run-live. That is
where the pre-registered gate criterion lives ("the no-snapshot baseline is measurably
worse"), and it is the ablation that justifies snapshots at all.

## 4. Both judge protocols run on every item

All-at-once (~1 call) and step-by-step (~20 calls) on every item of every split. Together
they are ~3% of the bill and they are the baselines the headline gap is measured against;
economising on the thing being compared against would be measuring our own thumb.

## 5. Per-step control is a dev-split sensitivity

`control_mode="per_step"` costs `2 x m x N` instead of `(m + 1) x N`. It runs on the **dev
split only**, reported beside the primary and never in place of it
(`docs/decisions/0016`, item 3). `bisect eval --per-step-sensitivity` refuses any other
split.

## 6. recall@m: measured to m = 3, judge-only beyond it

- **m ≤ 3** — measured: those suspects were actually re-run.
- **m > 3** — reported as **judge recall@m**: does the judge's ranked top-m contain the
  planted step. It needs no re-runs at all, because it is a property of the ranking.

The report labels it, because "recall@10" that nobody re-ran is a different quantity from
"recall@3" that was confirmed, and a reader must not have to infer which is which.

## 7. Re-run variation comes from the provider, and is caveated

A fork carries **no per-re-run seed**. Both alternatives were tried and both are wrong:
`ForkSpec.seed` re-pins the whole re-driven run and `seed` is a hashed sampling parameter,
so the fork diverges on its own first prefix step; injecting a seed at the live seam keeps
the prefix matching but makes the forked *recording* unreplayable, because its prefix and
suffix rows would want two different orchestrator seeds (found independently by P5 and by
`bench/inject.py`, commit ee41bed).

So the N draws of an arm differ **only by provider non-determinism at temperature 0**,
which `docs/decisions/0004-p0-probe-protocol.md` pinned. Consequences, stated in advance:

- P3's stability re-runs measure that variation; the P5 report **must state the measured
  within-item variation** alongside every interval.
- Every interval here **assumes exchangeable draws**. If re-runs do not vary, N draws are
  not N observations and the interval is not a 95% interval. That is a limitation to
  report, not a number to adjust.
- **The temperature is not changed after the fact.** Raising it to manufacture variance
  after seeing the data would be fitting the design to the result.

## 8. Dataset size follows P3

The plain-world dataset is whatever P3 collects under `docs/decisions/0012-p3-floor.md`
(floor 60 triggered) and `0017-p3-collection-policy.md`, split 1:2 dev:test **by task**.

The **flaky-world set is collected separately** by the injection pipeline: target 30
airline items, minimum 20, **all of them evaluated**. It is **not split**, and **nothing is
tuned on it** — it exists to answer one pre-registered question.

## 9. Order of live work in stage B

1. **Dev split** — all tuning and all diagnostics, including the
   `control_reproduces_failure` rates and the per-step sensitivity.
2. Write `docs/decisions/0014-p5-freeze.md`, recording that tuning is finished.
3. **Test split, once.** `bench/split_lock` refuses a second full run without `--resume`.
4. **Flaky set.**
5. **Gate** (`scripts/gates/p5.py`), over the committed summary.

## Projected spend under these decisions

| line | calls |
|---|---|
| dev split (judge + Bisect + re-run-live confirmation) | ~52,000 |
| test split (judge + Bisect; no-control derived) | ~63,000 |
| flaky set, 30 items x 2 arms | ~46,000 |
| **total** | **~161,000, ≈ 25 h at the measured limiter rates** |

If that is still too much, the one remaining lever that changes no conclusion is **N**
(cost is linear in it, and it halves at N = 8) — and it would need its own decision file,
written before the data, because it is a pre-registered parameter.
