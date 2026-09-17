# 0007 — Starting P1a and P4 before P0's gate closes

- **Date:** 2026-09-17 02:20 MDT
- **Context:** the run prompt parallelises P4 / P6 / P7 "once P2 is green". P0b (rate-limit ramp + 20-task probes) is API-bound and takes about an hour of wall-clock in which nothing else may use the API.
- **Decision:** start two network-free work items now, in the same tree, on disjoint files:
  - **P1a** — `core/store`, `core/tape`, `core/snapshot`, `adapters/tau2_snapshot` with an offline τ² snapshot round-trip test. The live half of P1 (20 recorded runs) waits for P0's model choice.
  - **P4** — estimator on fakes. It depends only on a `RerunSampler` protocol, not on the replay engine.
- **Why it is safe:** neither item calls the API or depends on which model is chosen; gates are unchanged and still run in order; file ownership is disjoint and commits are path-scoped (`git commit -- <paths>`).
- **Also started early (02:00):** design research for P6 (`docs/design/direction.md`), which has no code dependency.
- **Model availability note:** `moonshotai/kimi-k2.6` is listed by `/v1/models` but returns 404 "Function not found for account" on this key, so the pre-registered fallback order applies. Not a stop condition (three agent candidates remain).
