# LOOP_STATE — agent-bisect

Source of truth for progress. On restart or context compaction: re-read this file, resume from "Next action", never redo finished work.

- **Run started:** 2026-09-17 01:51 MDT
- **Orchestrator rule:** main chat coordinates only; all work is done by subagents; every subagent reports back (≤ 15 lines) before its task is marked done.
- **Spec:** the run prompt (priority 1), `docs/brief/bisect-brief.html` (priority 2), summary at `docs/brief/summary.md`.
- **Pre-registered thresholds:** `docs/decisions/0001-preregistration.md` (written before any measurement).
- **Environment note:** a GateGuard hook asks for a short "facts" statement before the first Bash call and before each new file; state the facts, then retry the same call.

- **Subagent file rule:** some subagents cannot Write report-like `.md` files (summary / findings / analysis). Policy: a subagent tries Write once; if refused it returns the content as text and the orchestrator persists it. No Bash workarounds around that rule.
- **Landscape follow-up:** the brief cites Who&When Pro (Jul 2026, 73.9%); `landscape-0` reported 36.2% as the best found → next landscape pass must reconcile this.

## Current

- **Phase:** P0 — Setup and model choice
- **Status:** IN PROGRESS
- **Next action:** collect P0a (scaffold), brief summary, landscape baseline → then launch P0b (rate-limit measurement, model probes, doctor gate).
- **Blockers:** none

## Phase board

| Phase | Status | Gate | Evidence | Calls spent | Commit |
|---|---|---|---|---|---|
| P0 Setup and model choice | IN PROGRESS | — | docs/gates/P0.md | 0 | — |
| P1 Record and snapshot | PENDING | — | docs/gates/P1.md | — | — |
| P2 Replay | PENDING | — | docs/gates/P2.md | — | — |
| P3 Interventions and planted faults | PENDING | — | docs/gates/P3.md | — | — |
| P4 Estimator | PENDING | — | docs/gates/P4.md | — | — |
| P5 Blame vs baselines | PENDING | — | docs/gates/P5.md | — | — |
| P6 Dashboard | PENDING | — | docs/gates/P6.md | — | — |
| P7 PR check | PENDING | — | docs/gates/P7.md | — | — |
| P8 Report | PENDING | — | docs/gates/P8.md | — | — |

## P0 plan

1. **P0a (scaffold, ≤ 20 API calls):** uv project (Python 3.12), package layout per spec §4, tooling (ruff, pyright, pytest, pytest-socket, hypothesis, import-linter), `nvapi-` pre-commit hook + test, tau2-bench pinned to a commit, `.env` loading, `core/llm` (LiteLLM→NIM, process-wide async token bucket, Retry-After, backoff + jitter, redaction), `core/budget` ledger, `bisect doctor` skeleton, model availability check (`GET /v1/models` + one smoke call per candidate). Node check.
2. **P0b (API-heavy, serial):** measure NIM rate limit (ramp to HTTP 429, per model); probe 4 agent candidates on 20 airline tasks; choose user simulator and judge; write `docs/decisions/models.md`; one τ² task end to end; `bisect doctor` exits 0; `scripts/gates/p0.py`; evidence in `docs/gates/P0.md`.
3. Code review + security review of `core/llm`, `core/budget`, env loading. Fix CRITICAL/HIGH.
4. Commit, push, update this file. Landscape re-check at the boundary.

## Parallel plan after P2 is green

- P3 collection runs as a detached, checkpointed, ledger-paced background job (logs in `runs/logs/`).
- P4 (fakes only), P6 (fixture data), P7 (scripted agent) build in parallel subagents meanwhile.
- P5 starts when P3's test split is frozen. P6 finishes on real data. P8 last.

## Active subagents

| Name | Task | Launched | Status |
|---|---|---|---|
| brief-reader | structured summary → docs/brief/summary.md | 01:55 | DONE — all 6 tabs read. Its Write was refused by a harness rule ("subagents return findings as text, not report files"); it returned the text and the orchestrator persisted a condensed `docs/brief/summary.md` (uncommitted). |
| p0a-scaffold | P0a scaffold | 01:55 | running |
| landscape-0 | prior-art baseline → docs/findings/landscape.md | 01:55 | DONE — 16 items, 78 lines, uncommitted (next committing agent stages it). Closest: CAR (mechanism), AgenTracer (fault injection for judge training), agentoptics/rewind (product shape, no statistics). Cite: Who&When 14.2% step-level, TraceElephant 28–30%, Ma et al. 36.2%. τ²-bench planted-fault novelty is UNVERIFIED — re-check before claiming. |
| design-research | P6 §6.2 direction → docs/design/direction.md (started early; independent of P0–P2) | 02:00 | DONE — 448 lines, uncommitted. 6 sites screenshotted (Warp, Raycast, Bklit UI, Motion, Supabase, Railway). Direction: "measurement instrument", the tape as organising metaphor, amber→coral reserved for blame. Dark palette unchanged; light theme semantic colours darkened for AA (worst 4.73:1); from-tape slate 3.08:1 → non-text use only. All 11 Bklit charts confirmed. 21st.dev shortlist needs licence check at install. Benchmark / PR-checks blueprints are extrapolated (no reference site). |

## Budget ledger (totals per phase end)

| Phase | Model | Calls | Notes |
|---|---|---|---|
| — | — | 0 | nothing spent yet |

## Decisions log (index)

- `docs/decisions/0001-preregistration.md` — gate thresholds, fixed before measurement.
- `docs/decisions/0002-plan-confirmation.md` — run launched via `/ecc:plan`; the prompt's "begin now, don't wait" taken as confirmation.

## History

- 01:51 — repo inspected: fresh scaffold (1 commit), `.env` present and git-ignored, brief untracked.
- 01:55 — state file + pre-registration written; brief-reader, p0a-scaffold, landscape-0 launched.
