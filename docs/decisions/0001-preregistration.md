# 0001 — Pre-registration of gate thresholds

- **Date:** 2026-09-17 01:55 MDT, written **before any measurement** (no rate-limit ramp, no model probe, no recorded run exists yet).
- **Rule:** thresholds are never lowered, data is never dropped, and no gate is changed after results are seen. A gate that fails after 3 real fix attempts stays FAILED, with the reason in `docs/gates/Pn.md` and `docs/findings/`.

## Gates

| Phase | Gate (machine-checkable) |
|---|---|
| P0 | `bisect doctor` exits 0: key found; chosen agent ≥ 95% valid tool calls **and** airline pass rate within 35–75% (20 airline tasks); one τ² task runs end to end with a reward; measured rate limit (requests/min per model) written to `docs/decisions/models.md`. |
| P1 | 20 recorded runs; restoring any step reproduces its recorded DB hash at 100% of steps; a redaction test proves the key appears in no blob or log. |
| P2 | 20/20 runs replay step-identical with the same reward while the network is blocked; an altered request raises `DivergenceError`. |
| P3 | ≥ 120 labelled failures. Fallback floor: 60, used **only if** P0's measured throughput projects the 120-target collection past 10 h of API time. Which one applied is recorded. |
| P4 | On 200 synthetic runs (zero network): planted step found ≥ 95%; 95% CI coverage of the true effect between 92% and 98%. |
| P5 | Test split: Bisect step accuracy ≥ best judge + 15 points, with the 95% bootstrap CI of the gap above 0. Flaky world: the no-snapshot baseline is measurably worse (CI of the difference above 0). |
| P6 | Playwright e2e passes for every page; axe 0 serious/critical; Lighthouse performance ≥ 90 and accessibility ≥ 95 on Overview and Run detail; design evaluator ≥ 8.5/10 on every page (min 3 rounds, max 6); screenshots in `docs/screenshots/`. |
| P7 | 3 planted-regression PRs flagged with the planted step named 3/3; 3 no-op PRs give 0 false alarms. |
| P8 | Clean clone, network blocked: `make reproduce` regenerates every figure and table byte-identically. |

## Fixed method parameters

- **Dataset construction (P3):** stable successes have re-run pass ≥ 0.75; fault step k stratified early / middle / late; 4 fault types; a planted fault is kept if faulted pass ≤ 0.25 at N = 4; dev:test split 1:2, frozen with a manifest hash before any P5 evaluation.
- **Estimator (P4/P5):** effect(k) = P(pass | fix k) − P(pass | recorded k); Wilson intervals per arm, Newcombe 95% CI for the difference; shared control; sequential stopping in batches of 4, max N = 16; blame the **earliest** step whose CI lower bound is above δ.
- **Bisect configuration (P5):** judge shortlist m = 3, δ = 0.10.
- **Baselines (P5):** LLM judge all-at-once and step-by-step (Who&When protocols); CAR-style re-run-live (no snapshots); no-control ablation.
- **Reported metrics:** step accuracy with CIs, recall@m, cost per diagnosis (API calls).
- **Tuning discipline:** anything tuned is tuned on the dev split only; the test split is touched once.

## Model candidates (order = fallback order if a model disappears from NIM)

- **Agent:** `moonshotai/kimi-k2.6`, `deepseek-ai/deepseek-v4-flash-0731`, `nvidia/nemotron-3-super-120b-a12b`, `z-ai/glm-5.3-flash`.
- **User simulator:** `nvidia/nemotron-3.5-lightning-30b-a3b`, `openai/gpt-oss-20b`.
- **Judge:** `moonshotai/kimi-k3`, `nvidia/nemotron-3-ultra-550b-a55b`.
- **Agent selection rule (fixed now):** among candidates that are available and meet ≥ 95% valid tool calls, pick the one whose 20-task airline pass rate is inside 35–75% and closest to 55% (the window's midpoint); ties go to the higher measured requests/min, then to list order.
- **Rate limiter setting:** measured requests/min minus a 10% safety margin.
- **Local MLX models:** development and tests only, never for reported numbers.
