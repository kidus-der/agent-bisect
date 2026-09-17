# 0015 — P1 pass rate (0.85) differs from P0's probe (0.60)

- **Date:** 2026-09-17 13:25 MDT
- **Observation:** same 20 airline tasks, same agent / user-sim models, temperature 0. P0 probe: 12/20 = 0.60 [0.39, 0.78]. P1 recordings: 17/20 = 0.85. τ²'s seed is a no-op for the LLM agent and user simulator, so the seed is not the cause.
- **Likely causes:** provider non-determinism at temperature 0 (the brief's premise), different concurrency / retry conditions, and small-sample noise (the two Wilson intervals overlap: 0.85 has [0.64, 0.95]). P0's probe scoring bugs were fixed before its final tally, so they are not a cause.
- **Decision:** the P0 gate stands as measured and recorded — it was evaluated once, on its pre-registered protocol, before this observation; the model choice is not revisited (re-selecting after seeing later data would be the kind of post-hoc change the pre-registration forbids, and every other candidate was further outside the window anyway: 0.90 and 0.80–0.85).
- **Consequences:** (1) more successful base runs for P3 (helps reach 120). (2) Run-to-run variance at temperature 0 is real, which is exactly why every effect is estimated against a control arm. (3) The report lists this under "deviations and surprises" with both numbers; the dataset card reports base-run stability per item (re-run pass rate ≥ 0.75 is already required).
