# Bisect dashboard API contract

`agent_bisect/server/` — a read-only FastAPI JSON API backing `bisect serve`.
Full machine-readable schema: `agent_bisect/server/openapi.json` (regenerate
with `uv run python scripts/export_openapi.py` after any route/schema
change; the web app generates its TypeScript types from that file).

## Envelope

Every JSON response has this shape:

```json
{"success": bool, "data": <payload> | null, "error": {"code": str, "message": str} | null,
 "meta": {"simulated": bool, "data_source": "fixture" | "real",
          "total": int | null, "page": int | null, "limit": int | null, "next_cursor": str | null}}
```

`meta.simulated` is `true` on every fixture-backed response, always. A field
this server can't answer yet returns HTTP 200 with `data = {"status":
"not_available", "reason": "..."}` — never a fabricated number. Unknown ids
are HTTP 404 with `error.code = "not_found"`. Bad query/path params are
HTTP 422. Both still carry the envelope shape.

## Endpoints

| Method | Path | Page group | Notes |
|---|---|---|---|
| GET | `/api/health` | global | `{"status": "ok"}` |
| GET | `/api/meta` | global | build/data-source info |
| GET | `/api/search?q=` | global | runs + static pages, ⌘K palette |
| GET | `/api/overview` | 1 Overview | headline, KPIs, recall@m, cost-vs-accuracy, hero run |
| GET | `/api/runs` | 2 Runs | `domain`, `outcome`, `status` (`recording`\|`complete`), `model`, `sort` (`-`-prefixed = desc), `page`, `limit` (≤200) |
| GET | `/api/runs/{run_id}` | 3 Run detail | manifest, outcome, steps, estimate, judge panel |
| GET | `/api/runs/{run_id}/steps/{step_idx}` | 3 | step inspector payload |
| GET | `/api/runs/{run_id}/steps/{step_idx}/intervention-diff` | 3 | `null` data if the step was never intervened on |
| GET | `/api/runs/{run_id}/steps/{step_idx}/state-diff` | 3 | structured before/after diff |
| GET | `/api/runs/{run_id}/reruns` | 3 | the treated-vs-control matrix |
| GET | `/api/runs/{run_id}/reruns/{rerun_id}/steps` | 3 | one individual re-run's steps |
| GET | `/api/benchmark` | 4 Benchmark | method comparison, heatmap, sankey, ablation, cost histogram |
| GET | `/api/dataset?page=&limit=` | 4 | labelled-failure dataset explorer |
| GET | `/api/live/snapshot` | 5 Live | calls series, budget, rate limit, jobs, events |
| GET | `/api/live/stream` | 5 | SSE, `event: snapshot` every ~2s |
| GET | `/api/pr-checks` | 6 PR checks | list |
| GET | `/api/pr-checks/{check_id}` | 6 | detail + rendered comment markdown |

`run_id`/`check_id`/`rerun_id` path params: `^[A-Za-z0-9_-]+$`, else 422/404.
`limit` ≤ 200. `sort` is checked against `run_sorting.SORTABLE_RUN_FIELDS`
(`run_id`, `n_steps`, `cost_usd`, `calls`, `outcome`, `domain`; `-`-prefixed
= descending) — one allow-list shared by `FixtureRepository` and
`RealRepository.list_runs`, so real mode can't silently ignore the
requested field; an unrecognized value falls back to `run_id` rather than
erroring, since it only affects ordering, not correctness.

**Nullable, honestly:** `RunSummary.cost_usd`/`calls`, `SparkPoint.latency_ms`/
`tokens`, and `RunDetail.reward` are `T | null`. Fixture mode always has a
real number; real mode returns `null` (never a fake `0`) wherever the
underlying data genuinely isn't known yet — per-run cost/calls (the ledger
has no `run_id` column until P1b), a step that never recorded telemetry, or
a run with no outcome row yet.

**Run status:** `RunSummary`/`RunDetail` carry `status: "recording" |
"complete"`. No outcome row yet → `"recording"`, `outcome`/`reward` null
(never a fabricated `"fail"`/`0.0`); still listed (never hidden) and in
search results (`SearchHit.status`); `outcome=pass|fail` excludes it for
free (`null` never matches), `status=recording` selects only it; excluded
from the Overview's failure accounting (unfinished isn't failed).

## Example responses

**`GET /api/health`**
```json
{"success": true, "data": {"status": "ok"}, "error": null,
 "meta": {"simulated": true, "data_source": "fixture", "total": null, "page": null, "limit": null, "next_cursor": null}}
```

**`GET /api/meta`**
```json
{"success": true, "data": {"data_source": "fixture", "simulated": true, "package_version": "0.1.0",
 "tau2_commit": "a1b2c3d4e5f6", "agent_model": "nvidia/llama-3.1-nemotron-70b-instruct",
 "user_model": "meta/llama-3.1-8b-instruct", "generated_at": "2026-09-17T00:00:00Z"}, "error": null, "meta": {...}}
```

**`GET /api/overview`**
```json
{"data": {"headline": {"bisect": {"value": 0.9651, "ci_low": 0.9024, "ci_high": 0.9881},
 "best_judge": {"value": 0.8721, "ci_low": 0.7853, "ci_high": 0.9271}, "best_judge_method": "judge_step_by_step"},
 "kpis": {"runs_recorded": 266, "failures_diagnosed": 86, "calls_spent": 86490, "cost_per_diagnosis_usd": 1.5209},
 "recall_at_m": [{"m": 1, "recall": 0.7674}, "..."], "cost_vs_accuracy": ["..."], "hero_run": {"...": "the brief-12-step run"}}}
```

**`GET /api/runs?limit=1`**
```json
{"data": {"runs": [{"run_id": "brief-12-step", "domain": "airline", "task_id": "refund_after_cancellation",
 "model": "nvidia/llama-3.1-nemotron-70b-instruct", "status": "complete", "outcome": "fail", "n_steps": 12,
 "decisive_step": 7, "fault_type": "wrong_value", "planted_step": 7, "cost_usd": 0.97, "calls": 470,
 "sparkline": [{"step_idx": 1, "actor": "user", "latency_ms": 3013, "tokens": 102}, "..."],
 "blame_stripe": [{"step_idx": 1, "effect": null, "tested": false}, "..."]}]},
 "meta": {"total": 266, "page": 1, "limit": 1}}
```

**`GET /api/runs/{run_id}`**
```json
{"data": {"run_id": "brief-12-step", "domain": "airline", "agent_model": "...", "seed": 7,
 "status": "complete", "outcome": "fail", "reward": 0.0,
 "steps": [{"step_idx": 1, "actor": "user", "tool_name": null, "text": "confirms the requested change",
            "from_tape": true, "state_changed": false}, "..."],
 "estimate": {"blamed_step": 7, "step_effects": ["..."], "control_mode": "shared"}, "judge": {"...": "..."}}}
```

**`GET /api/runs/{run_id}/steps/{step_idx}`**
```json
{"data": {"step_idx": 7, "messages": [{"role": "tool", "content": "book_reservation returned"}],
 "tool_args": {"id": "X0X2K6"},
 "tool_result": {"reservation_id": "NM1VX1", "status": "confirmed", "origin": "JFK"}}}
```

**`GET /api/runs/{run_id}/steps/7/intervention-diff`** (the brief's own example)
```json
{"data": {"step_idx": 7,
 "original_tool_result": {"reservation_id": "NM1VX1", "status": "confirmed", "origin": "JFK"},
 "replaced_tool_result": {"reservation_id": "ZFA04Y", "status": "confirmed", "origin": "JFK"}}}
```

**`GET /api/runs/{run_id}/steps/7/state-diff`**
```json
{"data": {"step_idx": 7, "entries": [{"path": "user.membership", "kind": "changed", "before": "21MM", "after": "U9JL"}]}}
```

**`GET /api/runs/{run_id}/reruns`**
```json
{"data": {"reruns": [{"rerun_id": "brief-12-step-t1-0", "arm": "treated", "step": 1, "seed": 107,
 "passed": true, "n_steps": 12, "calls": 10}, "..."]}}
```

**`GET /api/benchmark`**
```json
{"data": {"methods": [{"method": "bisect", "accuracy": {"value": 0.9651, "ci_low": 0.9024, "ci_high": 0.9881},
 "mean_cost_usd": 1.5607, "mean_calls": 780.35}, {"method": "judge_all_at_once", "accuracy": {"value": 0.7674, "..."}},
 "..."], "heatmap": ["..."], "by_position": ["..."], "sankey": ["..."], "flaky_ablation": {"...": "..."},
 "cost_histogram": ["..."]}}
```

**`GET /api/dataset?limit=1`**
```json
{"data": {"entries": [{"run_id": "run-edge-60-step", "domain": "airline", "fault_type": "stale_record",
 "planted_step": 55, "position_bucket": "late", "split": "dev", "base_pass_rate": 0.8812, "faulted_pass_rate": 0.0746}]},
 "meta": {"total": 86, "page": 1, "limit": 1}}
```

**`GET /api/live/snapshot`**
```json
{"data": {"calls_series": [{"ts": "2026-09-17T08:33:00+00:00", "model": "nvidia/llama-3.1-nemotron-70b-instruct",
 "calls_per_minute": 17.2}, "..."], "budget": {"used": 6421, "cap": 12000},
 "rate_limit": {"limiter_rpm": 40, "current_rpm": 22.0, "headroom_rpm": 18.0}, "jobs": ["..."], "events": ["..."]}}
```

**`GET /api/pr-checks`**
```json
{"data": [{"check_id": "pr-check-00", "pr_number": 1000, "title": "reschedule_flight_change",
 "is_regression": true, "base_pass_rate": 0.875, "head_pass_rate": 0.5833, "p_value": 0.023}, "..."]}
```

## `not_available` example (real mode, before any recording exists)

```json
{"success": true, "data": {"status": "not_available",
 "reason": "no recordings yet (runs/index.sqlite not found)"}, "error": null,
 "meta": {"simulated": false, "data_source": "real", "total": null, "page": null, "limit": null, "next_cursor": null}}
```

## Real-mode `null` example (a run recorded but not yet cost-attributed)

```json
{"data": {"runs": [{"run_id": "real-run-1", "domain": "airline", "status": "complete", "outcome": "pass",
 "n_steps": 1, "decisive_step": null, "fault_type": null, "planted_step": null,
 "cost_usd": null, "calls": null,
 "sparkline": [{"step_idx": 0, "actor": "tool", "latency_ms": null, "tokens": null}],
 "blame_stripe": [{"step_idx": 0, "effect": null, "tested": false}]}]},
 "meta": {"simulated": false, "data_source": "real"}}
```

(`GET /api/runs?status=recording`: two fixture-mode edge-case runs the same
shape, but `"status": "recording", "outcome": null` — never `"fail"`.)

## Security

Binds `127.0.0.1` by default (`agent_bisect/server/runserver.py`); a
non-loopback `--host` is refused unless explicitly passed, and prints a
warning when it is. CORS allows only `http://127.0.0.1:5173` /
`http://localhost:5173` (the Vite dev origin), GET only, no wildcard.
Every response carries `X-Content-Type-Options: nosniff` and a CSP
(`default-src 'self'; frame-ancestors 'none'`). All SQLite access in
`real_repository.py` opens `mode=ro`; nothing in `server/` ever writes.
Every route handler except `/api/live/stream` is a plain `def`, so FastAPI
already runs it in its threadpool; `/api/live/stream`'s async generator
(`sse.py`) offloads its one blocking call (`repository.live_snapshot()`)
via `asyncio.to_thread` so it can't stall the event loop for other
concurrent requests, and closes promptly (no lingering task) on client
disconnect.
