# 0009 — P4 outcome, and which estimator configuration is primary in P5

- **Date:** 2026-09-17 02:55 MDT — before any real recorded run, planted fault, or P5 measurement exists.

## P4 outcome: FAILED (final)

- Criterion (a) planted step found ≥ 0.95: **0.890** (178/200) as first built; **0.895** (179/200) after fix attempt 1. Confirmation seed: 0.930. FAIL.
- Criterion (b) 95% CI coverage in [0.92, 0.98]: **0.967**. PASS.
- Fix attempt 1 (decision 0008) corrected a genuine defect — uncorrected repeated looks — and removed every false blame (11 → 0). The verdict did not change: 10 of the 11 rescued runs became non-detections.
- Remaining cause is structural: with max N = 16 per arm and the synthetic design fixed in 0006 (treated 0.60–0.95, control 0.00–0.15), exact power puts the ceiling near 0.92. The 0.95 bar was set without a power calculation. Attempts 2 and 3 are deliberately unused: no bug is left, and changing N, δ, the generator or the seed after seeing results would be fudging.
- Evidence: `docs/gates/P4.md`, `docs/findings/p4.md` (power table).

## P5 primary configuration (declared now)

- **Primary:** `efficacy_boundary = "obf"` (O'Brien–Fleming-type boundary for interim and final blame decisions), δ = 0.10, batches of 4, max N = 16, m = 3, shared control, earliest-step rule. Reported intervals stay nominal 95% Newcombe.
- **Sensitivity analysis, always reported beside it:** `efficacy_boundary = "none"` — the literal pre-registered rule (nominal 95% lower bound > δ at every look).
- **Why:** the corrected procedure is the statistically valid one; it is slightly stricter than the letter of 0001, so it cannot inflate Bisect's accuracy through false-positive luck. The choice is made before any P5 data exists and is not revisited after.
- **Deviation note for the report:** this is a deviation from the letter of the pre-registration (0001) and must be listed in `docs/report.md` under deviations.
- **Consequence to expect:** non-detections ("no step blamed") count as wrong in step accuracy. The power table says effects with control ≥ 0.10 and treated ≤ 0.70 are often missed at N = 16; planted faults kept by the P3 rule (base pass ≥ 0.75, faulted pass ≤ 0.25) sit in a better-powered region (oracle fix ≈ base pass rate vs control ≤ 0.25).
