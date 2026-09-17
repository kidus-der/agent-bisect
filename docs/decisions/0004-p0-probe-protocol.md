# 0004 — P0 probe and rate-limit ramp protocol

- **Date:** 2026-09-17, **fixed before any probe/ramp ran** (no rate-limit
  window, no τ² task and no judge latency call had been executed when this
  file was written and committed).
- **Status:** pre-registered. These rules are applied mechanically in
  `scripts/measure_rate_limit.py`, `scripts/probe_models.py` and
  `scripts/gates/p0.py`. They are never adjusted after a number is seen. If
  no candidate satisfies the agent rule, that is reported as-is with the
  numbers; nothing is bent to manufacture a pass.
- **Extends:** `docs/decisions/0001-preregistration.md` (gate thresholds and
  the candidate fallback order), `docs/decisions/0003-tau2-pin.md` (the
  vendored τ² commit these defaults are read from).
- **Originating instruction (verbatim):** "Measure the real NIM rate limit
  (ramp until HTTP 429; record requests/min per model). Probe agent
  candidates … on 20 airline tasks … Record the choice in
  docs/decisions/models.md."

## 1. Task set and simulation settings (pinned for the whole study)

| Setting | Value | Source |
|---|---|---|
| Domain | `airline` | run prompt |
| Task set | the default/base airline task set, `data/tau2/domains/airline/tasks.json` | τ² default (`task_set_name = domain`, no split) |
| Tasks | the **first 20 tasks in the task file's own order** — ids `0`…`19` | this protocol |
| Trials per task | 1 | τ² `DEFAULT_NUM_TRIALS = 1` |
| Agent implementation | `llm_agent` | τ² `DEFAULT_AGENT_IMPLEMENTATION` / `TextRunConfig.agent` |
| User implementation | `user_simulator` | τ² `DEFAULT_USER_IMPLEMENTATION` / `TextRunConfig.user` |
| Max steps | **200** | τ² `DEFAULT_MAX_STEPS` (`TextRunConfig.max_steps`) |
| Max errors | **10** | τ² `DEFAULT_MAX_ERRORS` |
| Seed | **300** | τ² `DEFAULT_SEED` (`BaseRunConfig.seed`) |
| Agent temperature | **0.0** | τ² `DEFAULT_LLM_TEMPERATURE_AGENT` (`llm_args_agent = {"temperature": 0.0}`) |
| User temperature | **0.0** | τ² `DEFAULT_LLM_TEMPERATURE_USER` (`llm_args_user = {"temperature": 0.0}`) |
| Evaluation type | `EvaluationType.ALL` | τ² default for `run_single_task` |
| litellm `num_retries` | **0** (overrides τ²'s `DEFAULT_MAX_RETRIES = 3`) | see §5 — retries are ours, so every attempt is limiter-paced and ledgered |

All 50 airline tasks in the pinned checkout carry `reward_basis = ["DB",
"COMMUNICATE"]`, so `EvaluationType.ALL` scores them deterministically from
the database state and the transcript. **No LLM judge is involved in the
reward**, and no third-party (OpenAI) key is needed to evaluate a run.

These settings are pinned for P1–P8 as well: any later recorded run uses the
same agent/user implementations, max steps, max errors and temperatures.

## 2. Outcome definitions

- **pass** = `reward == 1.0` (exact equality on τ²'s `reward_info.reward`).
- **Pass rate** = passes / 20, over the 20 tasks above. The denominator is
  always 20; a task is never dropped from it.
- **Wilson 95% CI** is reported alongside every pass rate.

### Valid tool call rate

Pooled over the 20 tasks of one candidate:

```
valid_tool_call_rate = valid agent tool calls / all agent tool calls emitted
```

A tool call emitted by the **agent** (not the user simulator, not the
environment) counts as **valid** when all three hold:

1. its tool name exists in the airline domain's agent tool set;
2. its `arguments` string parses as JSON; and
3. the parsed arguments validate against that tool's signature/schema
   (τ²'s `Tool.params` pydantic model — the same schema that is advertised
   to the model as `openai_schema`).

Counted as **invalid calls** (numerator 0, denominator 1 each):

- a tool call written as plain text in the assistant `content` field
  instead of the structured `tool_calls` field (detected by the markers in
  `agent_bisect/adapters/tau2_llm.py::count_textual_tool_calls`: a
  `<tool_call>` / `<function…>` / `<|tool▁call|>`-style envelope, or a bare
  JSON object carrying both a tool-ish `name` key naming a domain tool and
  an `arguments`/`parameters` key, when the response emitted no structured
  tool call);
- a response that cannot be parsed into a message at all.

Explicitly **valid**: a tool call that the domain answers with a
business-logic error ("reservation not found", "flight is full", a policy
refusal). The model called a real tool correctly; the world said no.

Responses that carry no tool call and no textual tool call (ordinary
messages to the user) contribute nothing to either side of the ratio.

## 3. Infra failures vs task failures

- **Infra failure** — HTTP 429, 5xx, a connection error or a timeout that
  survives our retry budget, or a crash in *our* code. These are resumed or
  re-run and are **never** counted as a task failure. A task whose
  checkpoint was not written is simply re-run; finished tasks are never
  redone.
- **Agent-caused failure** — the agent loops, exceeds max steps, trips
  `too_many_errors`, emits an unparseable reply, or finishes with
  `reward < 1.0`. These **count as failures**.
- τ²'s own `termination_reason` is recorded per task, so the split between
  the two is auditable after the fact rather than a judgement call.

## 4. Selection rules

### 4.1 User simulator

Choose `nvidia/nemotron-3.5-lightning-30b-a3b`. Fall back to
`openai/gpt-oss-20b` **only if**, in a 2-task sanity check (airline tasks
`0` and `1`, otherwise the settings of §1), the first model either

- errors on every task, or
- returns empty user messages, or
- never ends a conversation (both tasks terminate on `max_steps`).

Whichever is chosen is then used for every candidate's 20-task probe, so
the agent comparison is against one fixed user simulator.

### 4.2 Judge

Candidates in list order: `moonshotai/kimi-k3`, then
`nvidia/nemotron-3-ultra-550b-a55b`. Take the **first** whose **median
latency over 5 calls** with a realistic ~3k-token trace prompt (built from a
real recorded probe trajectory) is **≤ 30 s**. If neither meets it, take the
**faster** of the two. Both medians are recorded either way.

### 4.3 Agent

As pre-registered in `0001-preregistration.md`: among candidates that are
**available** (listed and answering) and reach **≥ 95% valid tool calls**,
pick the one whose 20-task airline pass rate lies **inside 35–75%** and is
**closest to 55%**. Ties → higher measured requests/min → candidate list
order.

`moonshotai/kimi-k2.6` is unavailable on this key (HTTP 404 "Function … not
found for account", see `docs/decisions/models-availability.md`); per the
fallback order in 0001 it is skipped and its absence recorded. A candidate
that cannot emit structured tool calls at all is marked unusable as an agent
and its 20-task probe is skipped, with the reason recorded.

**If no candidate satisfies both conditions**, nothing is relaxed: the
numbers are reported as measured, the P0 gate is left FAILED with the reason
in `docs/gates/P0.md` and `docs/findings/p0.md`, and the orchestrator
decides.

## 5. Rate-limit ramp protocol

Tiny requests only (`max_tokens` 1–4, a one-word prompt), async, evenly
spaced inside each window.

1. **Ramp** target rates **20 → 40 → 60 → 90 → 120 → 160 → 200** requests
   per minute, one **60 s** window each, on `openai/gpt-oss-20b` first.
2. **Stop** the ramp at the first window that sees **any HTTP 429**.
3. **Cool down** until 429s stop, then **confirm** by re-running the last
   clean rate for **2 minutes** (two 60 s windows).
4. Per window record: target rate, sent, 200s, 429s, other errors, p50 and
   p95 latency, any `Retry-After` value, and every response header whose
   name contains `rate`, `limit` or `retry` (names and values only — never
   an `Authorization` or other auth header).
5. **Per model or account-wide:** run two models concurrently, each at ~60%
   of the found limit, for 60 s. 429s at a combined rate that neither model
   hit alone ⇒ account-wide; no 429s ⇒ per model.
6. For the remaining usable agent candidates and the two judges, a shorter
   ramp of **3 windows around the found limit** is enough.
7. **Total ramp budget ≤ 1,200 calls.** If no 429 appears up to 200 rpm,
   record "no 429 up to 200 rpm" and treat **200** as the measured value.
8. **Limiter setting:** measured rpm **minus 10%**, written to
   `config/limits.toml`. If the limit is account-wide, the single
   process-wide bucket covers **all models together**. Sustainable
   concurrency is derived from the measured latencies and recorded too.

## 6. Budget and resumability

- Hard cap for the whole of P0 in the ledger: **4,000 calls** (phase `P0`),
  of which the ramp may use at most 1,200.
- Every probe item is checkpointed per `(model, task_id)` under
  `runs/p0/probe/<model_slug>/<task_id>.json`; re-running skips finished
  items. On 429/5xx the job backs off and continues — it never fails the
  job.
