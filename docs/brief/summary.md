# Bisect — design brief summary

Source: `docs/brief/bisect-brief.html` (6 tabs: 01 Overview · 02 How it works · 03 Prior art · 04 The build · 05 Tech & models · 06 Phases & gates; compiled 16 Sep 2026). Read in full by the `brief-reader` subagent on 2026-09-17; condensed and persisted by the orchestrator. Charts in the brief's tabs 01, 02 and 05 are simulations or mocks, not results.

## Overrides — the run prompt wins over the brief

1. **Frontend:** React 19 + Vite + TypeScript + Tailwind v4 + shadcn/ui (brief says Svelte 5 + d3).
2. **Dashboard scope:** the brief's "viewer" (run list, timeline + heat stripe, step diff, forest plot) is the floor; the run prompt §6 defines the full scope (7 page groups, live SSE page included — the brief's "no live streaming" is superseded).
3. **Pacing:** one continuous run; the brief's nightly pauses / daily cap pacing is dropped, its call magnitudes remain useful.
4. **Palette and fonts:** the run prompt §6.3 palette (cyan measurement, violet judge, amber→coral blame) and Geist / Geist Mono replace the brief's "Instrument" tokens (Archivo / IBM Plex, teal measurement). Rules kept from the brief: an estimate never appears without its interval; pass/fail always carry ✓/✕; reduced motion disables animation.

## Open questions from the brief — resolved by the run prompt / pre-registration

- δ = 0.10 and m = 3 are pre-registered (`docs/decisions/0001-preregistration.md`). Max N = 16, batches of 4.
- Gate pass bars are hard gates, not targets. recall@m is report-only (no numeric floor).
- Error-type classification (Who&When Pro's macro-F1) is out of scope; Bisect names the causal **step**.
- Repair proposals on real failures are scored separately from oracle fixes on planted faults.

## 1. Definition and claim

"`git bisect`, for agent runs." Rewind a failed agent run to step k, change exactly one thing, re-run the rest N times, treated vs control, and measure the step's causal effect on pass rate instead of asking a judge to guess.

Claim to prove (tab 01): "On τ²-bench failures with a known planted cause, testing each suspect step by re-running it finds the right step **X points more often** than asking an AI judge, at a stated cost per diagnosis. Here is the dataset, here is the code, and `make reproduce` rebuilds every number offline from the recordings." — "or to report honestly that it isn't."

Naming: PyPI `agent-bisect`, import `agent_bisect`, CLI `bisect` (formerly "Rewind"; renamed because agentoptics ships `rewind-agent`).

## 2. Method

- **Split the run at k.** Before k: replayed from tape, zero network calls, exact; world state restored from step k's `state_before` snapshot and hash-checked. After k: sampled live N times per arm — **treated** (fix at k) and **control** (as recorded). "Without a control you would blame a step for luck."
- **Formula:** `effect(k) = P(pass | fix step k) − P(pass | step k as recorded)`; Wilson per arm, Newcombe 95% CI for the difference.
- **Blame rule:** the **earliest** step whose CI lower bound > δ (the "decisive error" convention) — not the largest effect, because later fixes can partially recover.
- **Cost:** all-steps ≈ `(steps+1) × N × calls_per_rerun`; Bisect ≈ `1 + (suspects+1) × N × calls_per_rerun` (the 1 is the judge call; the +1 is the shared control).
- **Judge-shortlist risk:** if the judge omits the culprit, replay cannot find it → report **recall@m** separately from accuracy. "If raising m costs too much, that is a finding."
- **Where snapshots matter:** plain τ² tools are deterministic, so snapshots there buy speed. They matter for correctness under non-determinism → the **flaky-world variant** (random generated IDs, time-dependent answers, occasional tool errors) where "the no-snapshot baseline measurably drifts and Bisect doesn't." That ablation justifies the engine.
- **Brief's demo numbers (simulated):** 12 steps, planted step 7, true treated pass `[0.10,0.12,0.12,0.18,0.10,0.10,0.88,0.40,0.30,0.18,0.12,0.10]`, control 0.10; at N=4 nothing is conclusive, by N≈8 step 7 separates; steps 8–9 help a little but come later. Good template for P4 fakes and UI fixtures.

## 3. Architecture (tab 04)

Principle: "A core that knows nothing about blame." `core/` never imports `attribution/`, `bench/`, `gate/` (Branchpoint, a later project, reuses the core). Adapters feed the core; surfaces only read results.

```
agent_bisect/
  core/
    tape.py        # Step records; append-only; request hashing
    store.py       # content-addressed blobs (sha256 + zstd) + SQLite index
    snapshot.py    # Snapshotter protocol: capture() / restore() / state_hash()
    replay.py      # TapeLLM + TapeTools: serve steps before k, fail loudly on divergence
    runner.py      # restore(k) → apply(intervention) → run the rest(seed) → Outcome
    llm.py         # LiteLLM wrapper: one rate limiter, retries, recording
    budget.py      # call ledger; hard stop at the configured cap
  adapters/
    tau2.py        # τ² DB snapshotter, reward → Outcome, user simulator on tape
    tau2_flaky.py  # flaky world: random ids, clock, injected tool errors
    sdk.py         # @bisect.tool + wrapped client, for agents outside τ²
  attribution/
    interventions.py  # ReplaceToolResult · ForceAction · Resample · EditPrompt · SwapModel
    estimate.py       # treated vs shared control; Wilson / Newcombe; early stopping
    judge.py          # all-at-once + step-by-step (Who&When protocols)
    search.py         # judge shortlist → confirm by replay → earliest step clearing δ
    repair.py         # proposes the fix at step k when no oracle exists
  bench/
    inject.py      # planted faults on successful runs → labelled dataset
    baselines.py   # judge-only · re-run-live (CAR-style) · no-control ablation
    evaluate.py    # step accuracy, recall@m, cost, bootstrap CIs
  gate/action.py   # base vs head over scenarios → PR comment markdown
  server/          # FastAPI JSON API + built dashboard as static files
  cli.py           # doctor | record | replay | blame | inject | eval | serve | gate
web/               # React app, built into agent_bisect/server/static/
```

### Step record (one row per step; large payloads in the blob store by hash)

| Field | Type | Why |
|---|---|---|
| run_id · step_idx | str · int | identity; a fork gets a new run_id + parent_run_id + fork_step |
| actor | agent \| user \| tool | τ² has three parties; the simulated user is an LLM and is recorded too |
| request_hash | sha256 | canonical hash of the model request; mismatch on replay = divergence: stop, don't guess |
| request_ref · response_ref | blob hash | full messages, tool schemas, reply — verbatim |
| tool_name · tool_args · tool_result_ref | str · json · blob | target for ReplaceToolResult |
| state_before · state_after | blob hash | world snapshot around the step; restore(k) loads state_before of k |
| state_hash | str | τ²'s own DB hash, checked after every restore |
| model · params · seed | str · json · int | pinned per run; swapping the model is itself an intervention |
| latency_ms · tokens_in · tokens_out | int | cost accounting |
| outcome (run level) | reward 0–1 · pass | pass = reward 1.0 |

### Interventions

`ReplaceToolResult` (tool return value; planted faults and repair) · `ForceAction` (agent reply / tool call) · `Resample` (fresh sample, nothing changed: bad luck vs bad policy) · `EditPrompt` (system prompt from k onward; used by the PR check) · `SwapModel` (model from k onward).

### Dataset construction — "break runs on purpose"

1. Record successes (τ² airline + retail; keep reward = 1.0).
2. Check stability: re-run 4×, keep pass rate ≥ 0.75.
3. Pick a tool-result step k, stratified early / middle / late.
4. Plant one of four faults: wrong value · missing field · stale record · tool error text.
5. Re-run the rest N = 4 with the fault.
6. Keep if it flips: faulted pass ≤ 0.25. Label = k; oracle fix = the original tool result.

≥ 120 labelled failures, 1:2 dev:test, manifest hash committed before tuning.

### Five rules that outrank the tech table

1. Record everything, always (judge and repair calls too), **before use**; a crash loses nothing, a resume pays for nothing twice.
2. Tests never hit the network (pytest-socket, scripted fake model); live calls only in opt-in marked smoke tests.
3. Divergence is an error — never a silent live fallback ("that is how replay tools silently lie").
4. Pin what moves: model IDs, tau2 commit, user-sim model — in the run manifest.
5. The key never leaves `.env`; scrubbed from recordings and logs; proven by a redaction test.

## 4. CLI surface

```
bisect doctor                 # key, model tool-calling, one τ² task end to end
bisect record  --domain airline --tasks 0-19
bisect replay  RUN_ID         # zero network calls; asserts identical
bisect blame   RUN_ID --top 3 --n 8
bisect inject  --out data/faults.parquet
bisect eval    --split test   # accuracy, recall@m, cost, CIs
bisect serve                  # http://127.0.0.1:8484
bisect gate    --base main --head HEAD
```

## 5. PR check

Runs a fixed scenario suite on base and head; a pass-rate drop beyond noise (two-proportion test) triggers blame on the new failures, compares the decisive step with base, posts one comment. Brief's illustrative comment (a mock, not a result):

```
Bisect · agent regression detected
scenario suite     airline-refunds (24 tasks × 4 runs)
pass rate          base 0.83  →  head 0.54   (p = 0.002)
decisive step      step 7 · agent → get_reservation_details
effect of reverting at step 7   +0.62  95% CI [0.38, 0.81] · N = 12
what changed at step 7
  - asks for the reservation ID before looking anything up
  + looks up the most recent reservation by user_id
  caused by: system_prompt.md L31–L36 (this PR)
7 of 13 new failures share this step · 212 model calls · details → bisect serve
```

## 6. Call budget (brief's order-of-magnitude, ~10 calls per re-run, 40 req/min)

P0 ~1.5k calls (~40 min) · P1–P2 ~1k (~25 min) · P3 ~8–12k (~4–5 h) · P5 ~10–15k (~4–6 h) · P7 demo ~1k live, 0 for the scripted demo. The 40 req/min figure is a forum report; P0 measures the real limit.

## 7. UI cues worth keeping (rebuilt in React, with the run prompt's palette)

- **Hero "rewind" loop:** 12 nodes on a line with a playhead. All 12 run live → step 12 fails (red) → rewind to step 7 → steps 1–6 banded "read from tape · 0 calls" → step 7 tagged "tool result replaced · NM1VX1 → ZFA04Y" → steps 8–12 "re-run live × N" → "✓ pass" → status "blame: step 7 · effect +0.75". Reduced motion jumps to the final state.
- **Forest plot:** one row per tested step, square point estimate, 95% CI whisker, dashed δ line, solid zero line; rows are keyboard- and mouse-clickable and reveal that step's individual treated/control ✓/✕ outcomes.
- **Heat stripe:** the effect estimate per tested step; **untested steps are hatched**, never given a guessed value.
- **Viewer mock:** top bar with run id, ✕/✓ pill, "12 steps · model", "decisive: step N"; step list with actor and heat chip; detail pane with effect number and a `- old / + new` diff.
- **Architecture diagram:** adapters → core | wall | attribution/bench → surfaces, with a dashed "core never imports the right side" wall.

## 8. Prior art named in the brief (checked 16 Sep 2026; see `docs/findings/landscape.md` for the dated re-checks)

| Project | Snapshots | Replay | Causal stats | Benchmark | PR check | Note |
|---|---|---|---|---|---|---|
| causal-agent-replay (CAR) | — | ✓ | ✓ | — | — | five intervention types, CIs, Shapley; re-runs tools live; synthetic eval only → our re-run-live baseline |
| agentoptics Rewind | ◐ | ✓ | — | — | ✓ | fork at any step; fixes "proven" by an LLM judge |
| Mirrors (YC) | ◐ | ✓ | — | — | ✓ | mocks tools from production traces; no step blame |
| DoVer (Microsoft) | ✓ | ✓ | — | ✓ | — | checkpoint/edit/resume/verify; fixes 18–28% of failed Magentic-One runs |
| LangGraph time travel | ◐ | ✓ | — | — | — | graph state only |
| AgenTracer | — | — | ◐ | ✓ | — | trained 8B attributor; "replay" is LLM re-simulation |
| Braintrust · LangSmith | — | ◐ | — | — | ◐ | manual re-run of one logged call |
| **Bisect** | ✓ | ✓ | ✓ | ✓ | ✓ | plus planted-fault dataset and flaky-world ablation |

Research numbers quoted by the brief: Who&When (ICML 2025) 14.2% step-level, 53.5% agent-level, 184 static failures · later work ≈ 20–47% (AgenTracer-8B, A2P; not strictly comparable) · Who&When Pro (Jul 2026) 73.9% on 12,326 injected-error runs, error-type macro-F1 22.2% · TraceElephant (Apr 2026, 220 re-runnable failures; full traces help step-level by up to 76%) · CausalFlow (May 2026). README must credit: causal-agent-replay, DoVer, Who&When, TraceElephant, CausalFlow, AgenTracer.

## 9. Eight facts an implementer must not get wrong

1. Blame = the **earliest** step whose 95% CI lower bound clears δ, not the biggest effect.
2. Every effect needs a shared **control** arm; no control, no reported effect.
3. Replay divergence (`request_hash` mismatch) is a hard error, never a silent live fallback.
4. The flaky-world ablation is what justifies snapshots; plain τ² is deterministic.
5. Oracle fixes (planted faults) and `repair.py` proposals (real failures) are scored separately.
6. `core/` never imports `attribution/`, `bench/` or `gate/`.
7. `NVIDIA_API_KEY` never leaves `.env`; a redaction test proves it is in no blob or log.
8. P5 bar: Bisect step accuracy ≥ best judge + 15 points, with the 95% bootstrap CI of the gap above 0 — fixed before measuring.
