# 0020 — User acceptance of the P4 and P6 gate outcomes

- **Date:** 2026-09-17 17:55 MDT
- **Who:** the project owner, in chat, after the measured results were known. Recorded as a post-hoc decision; the pre-registered bars and the measured numbers stay in every gate document and in the report.

## P4 — relaxed bar accepted

- Pre-registered (0001): planted step found ≥ 0.95 on 200 synthetic runs; 95% CI coverage in [0.92, 0.98].
- Measured (`docs/gates/P4.md`): found 179/200 = 0.895 (confirmation seed 0.930); coverage 0.967; false blames 0/200 after the OBF boundary (0008).
- Cause: an exact power ceiling near 0.92 at max N = 16 under the synthetic design fixed in 0006 — not a defect (`docs/findings/p4.md`).
- **Accepted bar (user, "p4, i accept"):** found ≥ 0.85 **and** wrong-step blames ≤ 0.02, coverage unchanged. Under it P4 is PASS (0.895 / 0.000 / 0.967). Status in the report: "PASS under the relaxed bar accepted post hoc by the owner; FAILED under the pre-registered bar".

## P6 — accepted as is

- Measured (`docs/gates/P6.md`): e2e 101/101, axe 0 serious/critical, Lighthouse Overview 94/98 and Run detail 95/100, screenshots present; design evaluator 6/7 pages ≥ 8.5, PR checks 8.4 at the 6-round cap (its 390 px ScenarioTable defect was fixed afterwards, unscored).
- **Accepted (user, "p6 it looks good enough for now")** after reviewing the running dashboard on fixture data. Status in the report: "accepted by the owner; design criterion FAILED by 0.1 on one page".
