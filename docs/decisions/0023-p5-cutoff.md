# 0023 — P5 test split: hold, probe, and a hard cutoff

- **Date:** 2026-09-20 18:55 MDT
- **Who:** the team lead, after the token-rate-limit measurement in `docs/findings/token-rate-limit.md`.
- **Supersedes:** my recommendation of the same afternoon to finalise P5 on the dev split immediately.

## Situation

The test split opened at 2026-09-20T21:37:56Z and has 1 of 12 items complete. The
provider's limit is token-based, not request-based (`docs/findings/token-rate-limit.md`):
8 concurrent trivial requests succeed 8/8, 8 concurrent ~2,500-token requests succeed
1/8 at the same moment and rate. With the evaluation running at 12 in flight, 92% of
calls were retrying. At the measured ceiling of 2–4 concurrent the remaining ~9,000
productive calls need 40+ hours.

## Decision — option 3: hold and probe

1. **Stop spending.** No evaluation runs while the provider is degraded.
2. **Probe every 15 minutes with a burst of 8 concurrent realistic requests** — not a
   solo call. Solo calls lie here: a single request succeeds in ~2 s throughout the
   degradation, so a solo probe would have reported "healthy" during the 92%-retry hour.
3. **Auto-relaunch** `bisect eval --split test --resume` at **8 in flight** as soon as
   **3 consecutive probes** each succeed **≥ 6/8 within 60 s**. Message the team lead on
   relaunch.
4. **CUTOFF: 06:00 MDT on 2026-09-21.** At the cutoff, whatever the state, stop and
   finalise.
5. Keep `runs/p5/status.json` at `state: paused` with the latest probe numbers, so the
   orchestrator's hourly check sees the real state.
6. **No model swap and no split changes** — either would break the freeze in
   `0014-p5-freeze.md` and the pre-registration in `0001`.

## If the test split completes before the cutoff

Flaky set (3 items, with `rerun_live`) → `scripts/gates/p5.py` → `docs/gates/P5.md` →
evidence → final report.

## If it does not — what the report must say

- Dev split: complete, and labelled **diagnostic** (it is the split the method was
  developed on; it is not gate evidence).
- Test split: **not completed** — "provider capacity collapsed to ~1 concurrent request
  on the agent model from 18:00 on 09-20". Partial test items are listed **separately and
  individually, never pooled into a number**; a 1-item accuracy is not a result.
- Gate: **not evaluable**, with the power finding (`docs/findings/p5-power.md`: the +15
  point bar is 9–14% powered at n=12) printed beside it so the non-result is not read as
  a near miss.
- Flaky-world ablation: **not collected**. The offline snapshot-vs-`rerun_live` evidence
  in `tests/test_tau2_flaky.py` is a separate, smaller claim and is labelled as such.
- Full cost and wall-clock accounting, including the ~6,000 calls orphaned by the
  rerun-id fix.
- `docs/gates/P5.md`: **FAILED-NOT-EVALUABLE**.
- `data/results/` committed for dev and for the partial test items, separately labelled.
- `make reproduce-p5` green.

## Amendment, 2026-09-20 19:45 MDT

The team lead revised the probe's shape: **8 concurrent, passing at 6, relaunching at 8 in
flight**, rather than 10 / 8 / 12. The reason is that the probe should apply the same load
the relaunch will, so a pass means "this concurrency works" rather than "a larger burst
almost works". Interval, the three-consecutive rule and the cutoff are unchanged.

One probe had already been taken under the old rule — 01:21Z, 9 of 10 in 7.5 s, a pass. It
**does not count** toward the three: a pass measured at a different burst size is not the
same measurement, and carrying it over would relaunch on two probes' evidence.

## Budget

The P5 cap may be raised from 80,000 to 120,000 calls if the relaunch needs it; the cap
is ours, the provider is free, so budget is not the binding constraint here. Any raise is
noted in the report. Spend at the time of this decision: 20,903 calls.
