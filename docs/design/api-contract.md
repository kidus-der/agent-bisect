# Bisect dashboard API contract

`agent_bisect/server/` — a read-only FastAPI JSON API backing `bisect serve`.
Schema: `agent_bisect/server/openapi.json` (regenerate with `uv run python
scripts/export_openapi.py` after any route/schema change).

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
| GET | `/api/runs` | 2 Runs | `domain`, `outcome`, `status` (`recording`\|`complete`), `model`, `fault_type` (4 types\|`none`), `q` (≤100 chars), `sort` (`-`-prefixed = desc), `page`, `limit` (≤200) |
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
(`run_id`, `n_steps`, `cost_usd`, `calls`, `outcome`, `domain`; `-` prefix =
descending) — one allow-list shared by both repositories; an unrecognized
value falls back to `run_id` rather than erroring. `q`/`fault_type` are
applied server-side by `run_filtering.filter_runs` (also shared by both
repositories) — `q` is a case-insensitive substring over run_id/task_id/
model/tool names, `fault_type` is exact match with `"none"` meaning
unplanted; `meta.total` always reflects the filtered count.

**Nullable, honestly:** `RunSummary.cost_usd`/`calls`, `SparkPoint.latency_ms`/
`tokens`, and `RunDetail.reward` are `T | null` — fixture mode always has a
real number; real mode returns `null` (never a fake `0`) when genuinely
unknown. `calls` is real in real mode (the ledger's `run_id` column, P1b);
`cost_usd` stays `null` (no per-model USD price exists in this codebase
yet); so does a step's telemetry the run never recorded, or a run with no
outcome row yet.

**Run status:** `RunSummary`/`RunDetail` carry `status: "recording" |
"complete"`. No outcome row → `"recording"`, `outcome`/`reward` null (never
`"fail"`/`0.0`); still listed and searchable (`SearchHit.status`);
`outcome=pass|fail` excludes it for free (`null` never matches);
`status=recording` selects only it; excluded from Overview failures.

## Example responses

Example blocks below marked GENERATED are produced verbatim from a live
fixture-mode server by `scripts/export_contract_examples.py` (arrays
trimmed to 3 entries + a real count of the rest) — never hand-typed, and
`tests/server/test_contract_doc.py` fails the build if they drift. Run
that script and commit the result after anything that could shift a
fixture-derived number.

**`GET /api/health`**
<!-- BEGIN GENERATED: health -->
```json
{"status":"ok"}
```
<!-- END GENERATED: health -->

**`GET /api/meta`**
<!-- BEGIN GENERATED: meta -->
```json
{"agent_model":"nvidia/llama-3.1-nemotron-70b-instruct","data_source":"fixture","generated_at":"2026-09-17T00:00:00Z","package_version":"0.1.0","simulated":true,"tau2_commit":"a1b2c3d4e5f6","user_model":"meta/llama-3.1-8b-instruct"}
```
<!-- END GENERATED: meta -->

**`GET /api/overview`**
<!-- BEGIN GENERATED: overview -->
```json
{"cost_vs_accuracy":[{"accuracy":0.9651,"mean_cost_usd":1.5607,"method":"bisect"},{"accuracy":0.7674,"mean_cost_usd":0.03,"method":"judge_all_at_once"},{"accuracy":0.814,"mean_cost_usd":0.5937,"method":"judge_step_by_step"},"... (2 more)"],"headline":{"best_judge":{"ci_high":0.8821,"ci_low":0.7189,"value":0.814},"best_judge_method":"judge_step_by_step","bisect":{"ci_high":0.9881,"ci_low":0.9024,"value":0.9651},"gap":{"ci_high":0.2442,"ci_low":0.0581,"value":0.1512}},"hero_run":{"blame_stripe":[{"effect":-0.0625,"step_idx":1,"tested":true},{"effect":0.125,"step_idx":2,"tested":true},{"effect":0.125,"step_idx":3,"tested":true},"... (9 more)"],"calls":470,"cost_usd":0.97,"decisive_step":7,"domain":"airline","fault_type":"wrong_value","model":"nvidia/llama-3.1-nemotron-70b-instruct","n_steps":12,"outcome":"fail","planted_step":7,"run_id":"brief-12-step","sparkline":[{"actor":"user","latency_ms":3013,"step_idx":1,"tokens":102},{"actor":"agent","latency_ms":1010,"step_idx":2,"tokens":449},{"actor":"tool","latency_ms":2743,"step_idx":3,"tokens":234},"... (9 more)"],"status":"complete","task_id":"refund_after_cancellation"},"kpis":{"calls_spent":86490,"cost_per_diagnosis_usd":1.5209,"failures_diagnosed":86,"runs_recorded":266},"recall_at_m":[{"m":1,"recall":0.7674},{"m":2,"recall":0.8023},{"m":3,"recall":0.8721},"... (7 more)"]}
```
<!-- END GENERATED: overview -->
`headline.gap` is `bisect.value - best_judge.value`, 95% **paired**
percentile-bootstrap CI (`build_paired_gap_ci`, 2000 seeded resamples) —
not a Newcombe interval, which would ignore that both methods score the
same dataset.

**`GET /api/runs?limit=1`**
<!-- BEGIN GENERATED: runs-list -->
```json
{"runs":[{"blame_stripe":[{"effect":-0.0625,"step_idx":1,"tested":true},{"effect":0.125,"step_idx":2,"tested":true},{"effect":0.125,"step_idx":3,"tested":true},"... (9 more)"],"calls":470,"cost_usd":0.97,"decisive_step":7,"domain":"airline","fault_type":"wrong_value","model":"nvidia/llama-3.1-nemotron-70b-instruct","n_steps":12,"outcome":"fail","planted_step":7,"run_id":"brief-12-step","sparkline":[{"actor":"user","latency_ms":3013,"step_idx":1,"tokens":102},{"actor":"agent","latency_ms":1010,"step_idx":2,"tokens":449},{"actor":"tool","latency_ms":2743,"step_idx":3,"tokens":234},"... (9 more)"],"status":"complete","task_id":"refund_after_cancellation"}]}
```
<!-- END GENERATED: runs-list -->

**`GET /api/runs/{run_id}`** (`brief-12-step`, the brief's own worked example)
<!-- BEGIN GENERATED: run-detail -->
```json
{"agent_model":"nvidia/llama-3.1-nemotron-70b-instruct","created_at":"2026-08-01T09:00:00Z","domain":"airline","estimate":{"blamed_step":7,"config":{"batch":4,"conf":0.95,"control_mode":"shared","delta":0.1,"efficacy_boundary":"obf","max_n":16,"shortlist_m":3},"control_fork_step":1,"control_mode":"shared","control_reruns":16,"sampler_calls":47,"step_effects":[{"ci_high":0.1759,"ci_low":-0.3033,"control":{"n":16,"successes":2},"effect":-0.0625,"n_batches":4,"step":1,"stop_reason":"max_n","treated":{"n":16,"successes":1}},{"ci_high":0.386,"ci_low":-0.153,"control":{"n":16,"successes":2},"effect":0.125,"n_batches":4,"step":2,"stop_reason":"max_n","treated":{"n":16,"successes":4}},{"ci_high":0.386,"ci_low":-0.153,"control":{"n":16,"successes":2},"effect":0.125,"n_batches":4,"step":3,"stop_reason":"max_n","treated":{"n":16,"successes":4}},"... (9 more)"],"treated_reruns":184},"fault_type":"wrong_value","judge":{"all_at_once":[{"rank":1,"rationale":"[all-at-once] tool result at step 7 looks inconsistent with the reasoning that follows it","score":0.775,"step":7},{"rank":2,"rationale":"[all-at-once] tool result at step 3 looks inconsistent with the reasoning that follows it","score":0.0,"step":3},{"rank":3,"rationale":"[all-at-once] tool result at step 11 looks inconsistent with the reasoning that follows it","score":0.022,"step":11}],"step_by_step":[{"rank":1,"rationale":"[step-by-step] tool result at step 7 looks inconsistent with the reasoning that follows it","score":0.689,"step":7},{"rank":2,"rationale":"[step-by-step] tool result at step 3 looks inconsistent with the reasoning that follows it","score":0.0,"step":3},{"rank":3,"rationale":"[step-by-step] tool result at step 11 looks inconsistent with the reasoning that follows it","score":0.0,"step":11}]},"outcome":"fail","planted_step":7,"reward":0.0,"run_id":"brief-12-step","seed":7,"status":"complete","steps":[{"actor":"user","from_tape":true,"state_changed":false,"step_idx":1,"text":"confirms the requested change","tool_name":null},{"actor":"agent","from_tape":true,"state_changed":false,"step_idx":2,"text":"calls a tool to check the current state","tool_name":null},{"actor":"tool","from_tape":true,"state_changed":true,"step_idx":3,"text":"update_reservation_baggages returned","tool_name":"update_reservation_baggages"},"... (9 more)"],"task_id":"refund_after_cancellation","tau2_commit":"a1b2c3d4e5f6","user_model":"meta/llama-3.1-8b-instruct"}
```
<!-- END GENERATED: run-detail -->
`estimate.config` is the real `SequentialConfig` used (never hard-code delta
client-side); `shortlist_m` is the pre-registered judge-shortlist size.

**`GET /api/runs/{run_id}/steps/{step_idx}`** (step 7)
<!-- BEGIN GENERATED: step-payload -->
```json
{"messages":[{"content":"book_reservation returned","role":"tool"}],"step_idx":7,"tool_args":{"id":"X0X2K6"},"tool_result":{"origin":"JFK","reservation_id":"NM1VX1","status":"confirmed"}}
```
<!-- END GENERATED: step-payload -->

**`GET /api/runs/{run_id}/steps/7/intervention-diff`** (the brief's own example)
<!-- BEGIN GENERATED: intervention-diff -->
```json
{"original_tool_result":{"origin":"JFK","reservation_id":"NM1VX1","status":"confirmed"},"replaced_tool_result":{"origin":"JFK","reservation_id":"ZFA04Y","status":"confirmed"},"step_idx":7}
```
<!-- END GENERATED: intervention-diff -->

**`GET /api/runs/{run_id}/steps/7/state-diff`**
<!-- BEGIN GENERATED: state-diff -->
```json
{"entries":[{"after":"U9JL","before":"21MM","kind":"changed","path":"user.membership"}],"step_idx":7}
```
<!-- END GENERATED: state-diff -->

**`GET /api/runs/{run_id}/reruns`**
<!-- BEGIN GENERATED: reruns -->
```json
{"reruns":[{"arm":"treated","calls":10,"n_steps":12,"passed":true,"rerun_id":"brief-12-step-t1-0","seed":107,"step":1},{"arm":"treated","calls":10,"n_steps":12,"passed":false,"rerun_id":"brief-12-step-t1-1","seed":108,"step":1},{"arm":"treated","calls":10,"n_steps":12,"passed":false,"rerun_id":"brief-12-step-t1-2","seed":109,"step":1},"... (197 more)"]}
```
<!-- END GENERATED: reruns -->

**`GET /api/benchmark`**
<!-- BEGIN GENERATED: benchmark -->
```json
{"by_position":[{"accuracy":0.9655,"method":"bisect","n":29,"position":"early"},{"accuracy":1.0,"method":"bisect","n":18,"position":"late"},{"accuracy":0.9487,"method":"bisect","n":39,"position":"middle"}],"cost_histogram":[{"calls_high":400,"calls_low":0,"count":13},{"calls_high":800,"calls_low":400,"count":34},{"calls_high":1200,"calls_low":800,"count":35},"... (2 more)"],"flaky_ablation":{"arms":[{"accuracy":{"ci_high":0.9881,"ci_low":0.9024,"value":0.9651},"name":"snapshot"},{"accuracy":{"ci_high":0.9183,"ci_low":0.7718,"value":0.8605},"name":"no_snapshot"}],"difference":{"ci_high":0.1963,"ci_low":0.0193,"value":0.1046}},"heatmap":[{"accuracy":0.9565,"fault_type":"missing_field","method":"bisect","n":23},{"accuracy":0.8261,"fault_type":"missing_field","method":"judge_all_at_once","n":23},{"accuracy":0.7391,"fault_type":"missing_field","method":"judge_step_by_step","n":23},"... (17 more)"],"methods":[{"accuracy":{"ci_high":0.9881,"ci_low":0.9024,"value":0.9651},"mean_calls":780.35,"mean_cost_usd":1.5607,"method":"bisect"},{"accuracy":{"ci_high":0.8441,"ci_low":0.6679,"value":0.7674},"mean_calls":1.0,"mean_cost_usd":0.03,"method":"judge_all_at_once"},{"accuracy":{"ci_high":0.8821,"ci_low":0.7189,"value":0.814},"mean_calls":19.79,"mean_cost_usd":0.5937,"method":"judge_step_by_step"},"... (2 more)"],"sankey":[{"count":22,"fault_type":"missing_field","label":"exact"},{"count":1,"fault_type":"missing_field","label":"none"},{"count":21,"fault_type":"stale_record","label":"exact"},"... (3 more)"]}
```
<!-- END GENERATED: benchmark -->

**`GET /api/dataset?limit=1`**
<!-- BEGIN GENERATED: dataset -->
```json
{"entries":[{"base_pass_rate":0.8812,"domain":"airline","fault_type":"stale_record","faulted_pass_rate":0.0746,"planted_step":55,"position_bucket":"late","run_id":"run-edge-60-step","split":"dev","task_id":"seat_upgrade_request"}]}
```
<!-- END GENERATED: dataset -->

**`GET /api/live/snapshot`** (illustrative — the live simulator is time-seeded,
not reproducible from the committed fixtures, so this block is hand-written
and not drift-checked)
```json
{"data": {"calls_series": [{"ts": "2026-09-17T08:33:00+00:00", "model": "nvidia/llama-3.1-nemotron-70b-instruct",
 "calls_per_minute": 17.2}, "..."], "budget": {"used": 6421, "cap": 12000},
 "rate_limit": {"limiter_rpm": 40, "current_rpm": 22.0, "headroom_rpm": 18.0},
 "jobs": [{"job_id": "job-0", "kind": "blame", "state": "running", "progress": 0.64,
  "phase": "P5", "label": "step-by-step blame search", "items_done": 10, "items_total": 16,
  "model": "nvidia/llama-3.1-nemotron-70b-instruct", "calls_spent": 80,
  "started_at": "2026-09-17T18:48:57Z", "finished_at": null, "eta_seconds": 236.2,
  "last_checkpoint_at": "2026-09-17T18:55:57Z", "error": null}, "..."], "events": ["..."]}}
```
`state` and `progress`/`started_at`/`finished_at`/`error` are validated
together (`schemas_live.JobStatus`): `queued` ⇒ `progress=0`, no
`started_at`; `running` ⇒ `0 < progress < 1`; `done` ⇒ `progress=1` and
`finished_at` set; `failed` ⇒ `error` set. Every field past `state` is
`null` when unknown, never invented.

**Real mode's `runs/<phase>/status.json` convention.** A long-running job
(the P1 recorder, a P3/P5 batch, …) may write its own progress to
`runs/<phase>/status.json` (e.g. `runs/p1/status.json`); `RealRepository`
reads one such file per phase directory present and reports it as a
`JobStatus` with `job_id`/`phase` taken from the directory name (`phase`
upper-cased) unless the file overrides them. A missing, unreadable,
invalid-JSON, or invariant-violating file is skipped, not fatal to the
rest of the snapshot; no job is invented for a phase with no file. Shape
(all keys but `kind`/`state`/`progress` optional):
```json
{"kind": "record", "state": "running", "progress": 0.45, "label": "tau2 run recording",
 "items_done": 9, "items_total": 20, "model": "nvidia/nemotron-3-super-120b-a12b",
 "calls_spent": 812, "started_at": "2026-09-17T09:00:00Z", "finished_at": null,
 "eta_seconds": 640.0, "last_checkpoint_at": "2026-09-17T09:12:00Z", "error": null}
```

**`GET /api/pr-checks`**
<!-- BEGIN GENERATED: pr-checks -->
```json
[{"base_pass_rate":0.875,"check_id":"pr-check-00","head_pass_rate":0.5833,"is_regression":true,"p_value":0.023,"pr_number":1000,"title":"reschedule_flight_change"},{"base_pass_rate":0.9167,"check_id":"pr-check-01","head_pass_rate":0.625,"is_regression":true,"p_value":0.0162,"pr_number":1001,"title":"payment_method_swap"},{"base_pass_rate":0.9167,"check_id":"pr-check-02","head_pass_rate":0.5417,"is_regression":true,"p_value":0.0035,"pr_number":1002,"title":"certificate_reissue"},"... (3 more)"]
```
<!-- END GENERATED: pr-checks -->

**`not_available` example** (real mode, before any recording exists)
```json
{"success": true, "data": {"status": "not_available",
 "reason": "no recordings yet (runs/index.sqlite not found)"}, "error": null,
 "meta": {"simulated": false, "data_source": "real", "total": null, "page": null, "limit": null, "next_cursor": null}}
```

**Real-mode `null` example** (a run recorded but not yet cost-attributed)

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

Binds `127.0.0.1` by default (`runserver.py`); non-loopback `--host` needs
an explicit flag and prints a warning. CORS: only the Vite dev origins,
GET only, no wildcard. Every response carries `X-Content-Type-Options:
nosniff` and a CSP (`default-src 'self'; frame-ancestors 'none'`). SQLite
in `real_repository.py` opens `mode=ro`; nothing in `server/` ever writes.
Every route but `/api/live/stream` is a plain `def` (FastAPI's
threadpool); that one offloads its blocking call via `asyncio.to_thread`
and closes promptly on client disconnect.
