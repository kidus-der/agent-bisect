# Model choice and the measurements behind it

- **Date:** 2026-09-17. **τ² commit:** `2174a603f6d014ef94473ffa95957f6ce27100db`.
- **GENERATED** by `scripts/decide_models.py` from `runs/p0/`; re-running it reproduces this file. Rules were fixed before measuring: `docs/decisions/0001-preregistration.md`, `docs/decisions/0004-p0-probe-protocol.md`.

## 1. Availability

| Model | Role | Available | Note |
|---|---|---|---|
| `moonshotai/kimi-k2.6` | agent | **no** | HTTP 404 'Function ... not found for account' — not on this key |
| `deepseek-ai/deepseek-v4-flash-0731` | agent | yes |  |
| `nvidia/nemotron-3-super-120b-a12b` | agent | yes |  |
| `z-ai/glm-5.3-flash` | agent | yes |  |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | user simulator | yes | |
| `openai/gpt-oss-20b` | user simulator | yes | |
| `moonshotai/kimi-k3` | judge | yes | |
| `nvidia/nemotron-3-ultra-550b-a55b` | judge | yes | |

`moonshotai/kimi-k2.6` is the first agent candidate in 0001's fallback order and is unavailable on this key, so it is skipped and its absence recorded — per the fallback rule, not as an exception to it.

## 2. Measured rate limit

**The limit is enforced per model, not account-wide.** In one 60 s window with two models at 120 rpm each (240 rpm combined), `openai/gpt-oss-20b` took 120/120 requests with zero 429s while `nvidia/nemotron-3.5-lightning-30b-a3b` took 48 HTTP 429s — a shared account bucket could not throttle one model that hard and spare the other entirely. An isolation window settled it: `nvidia/nemotron-3.5-lightning-30b-a3b` **alone** at 120 rpm still returned 10 HTTP 429s in 60 requests, so its own ceiling, not the combined rate, is what it hit.

| Phase | Model | Target rpm | Window | Sent | 200s | 429s | Other errors | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| ramp | `openai/gpt-oss-20b` | 20 | 60 s | 20 | 20 | 0 | 0 | 209 | 469 |
| ramp | `openai/gpt-oss-20b` | 40 | 60 s | 40 | 40 | 0 | 0 | 218 | 647 |
| ramp | `openai/gpt-oss-20b` | 60 | 60 s | 60 | 60 | 0 | 0 | 217 | 297 |
| ramp | `openai/gpt-oss-20b` | 90 | 60 s | 90 | 90 | 0 | 0 | 208 | 396 |
| ramp | `openai/gpt-oss-20b` | 120 | 60 s | 120 | 120 | 0 | 0 | 205 | 305 |
| ramp | `openai/gpt-oss-20b` | 160 | 60 s | 160 | 160 | 0 | 0 | 210 | 461 |
| ramp | `openai/gpt-oss-20b` | 200 | 60 s | 200 | 200 | 0 | 0 | 216 | 930 |
| pair | `openai/gpt-oss-20b` | 120 | 60 s | 120 | 120 | 0 | 0 | 223 | 529 |
| pair | `nvidia/nemotron-3.5-lightning-30b-a3b` | 120 | 60 s | 120 | 68 | 48 | 4 | 333 | 84277 |
| short | `deepseek-ai/deepseek-v4-flash-0731` | 120 | 15 s | 30 | 30 | 0 | 0 | 23490 | 31566 |
| short | `deepseek-ai/deepseek-v4-flash-0731` | 160 | 15 s | 40 | 0 | 40 | 0 | 52 | 55 |
| short | `nvidia/nemotron-3-super-120b-a12b` | 120 | 15 s | 30 | 23 | 0 | 7 | 330 | 3599 |
| short | `nvidia/nemotron-3-super-120b-a12b` | 160 | 15 s | 40 | 10 | 28 | 2 | 55 | 454 |
| short | `z-ai/glm-5.3-flash` | 120 | 15 s | 30 | 19 | 0 | 11 | 83369 | 90098 |
| short | `z-ai/glm-5.3-flash` | 160 | 15 s | 40 | 28 | 10 | 2 | 63210 | 87971 |
| short | `moonshotai/kimi-k3` | 120 | 15 s | 30 | 0 | 20 | 10 | 141 | 90098 |
| short | `nvidia/nemotron-3-ultra-550b-a55b` | 120 | 15 s | 30 | 30 | 0 | 0 | 964 | 33764 |
| isolate | `nvidia/nemotron-3.5-lightning-30b-a3b` | 120 | 30 s | 60 | 49 | 10 | 1 | 261 | 13539 |
| isolate | `moonshotai/kimi-k3` | 30 | 30 s | 15 | 0 | 5 | 10 | 90092 | 90100 |

No response header containing `rate`, `limit` or `retry` was returned by NIM on any request in any window, and no `Retry-After` was ever sent — the ceiling is only observable by hitting it.

| Model | Measured rpm | Limiter rpm (measured − 10%) |
|---|---|---|
| `deepseek-ai/deepseek-v4-flash-0731` | 120 | 108 |
| `nvidia/nemotron-3-super-120b-a12b` | 120 | 108 |
| `openai/gpt-oss-20b` | 200 | 180 |
| `z-ai/glm-5.3-flash` | 120 | 108 |

**Not bracketed.** These returned 429s at the lowest rate they were tried at, so their ceiling is below it and no clean rate was located. They are recorded as unmeasured rather than as a number, and the limiter is set conservatively for them (`config/limits.toml`):

| Model | What was observed |
|---|---|
| `moonshotai/kimi-k3` | throttled even at 30 rpm alone (5 HTTP 429 and 10 timeouts of 15 requests, p50 latency at our 90s request timeout); no clean rate located at or below 120 rpm |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | ceiling below 120 rpm; not yet bracketed |

**Sustainable concurrency.** The probe ran 12 tasks at once, spread round-robin across the agent candidates. Retried attempts per model over the whole phase (a retry means the provider rejected an in-flight request, not that our rate bucket overflowed):

| Model | Retried attempts | Successful | Retry share |
|---|---|---|---|
| `deepseek-ai/deepseek-v4-flash-0731` | 0 | 205 | 0.0% |
| `nvidia/nemotron-3-super-120b-a12b` | 193 | 497 | 28.0% |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 1 | 387 | 0.3% |
| `z-ai/glm-5.3-flash` | 2 | 279 | 0.7% |

## 3. Agent probe — 20 airline tasks, 1 trial each

| Model | Pass rate | 95% CI (Wilson) | Valid tool calls | Mean messages | Calls/task | Mean agent latency |
|---|---|---|---|---|---|---|
| `deepseek-ai/deepseek-v4-flash-0731` | 18/20 = 0.90 | [0.70, 0.97] | 1.000 (0/199 invalid) | 22.9 | 12.1 | 56.6 s |
| `nvidia/nemotron-3-super-120b-a12b` | 12/20 = 0.60 | [0.39, 0.78] | 0.997 (1/314 invalid) | 43.8 | 35.0 | 18.6 s |
| `z-ai/glm-5.3-flash` | 16/20 = 0.80 | [0.58, 0.92] | 1.000 (0/159 invalid) | 26.1 | 16.8 | 49.9 s |

### Tasks that never completed

Protocol 0004 §3: an infra failure (429/5xx past our retry budget, a timeout, or τ² reporting INFRASTRUCTURE_ERROR) is re-run, never scored. Each was retried over three resume passes; these still did not finish, so the pass rate above counts them as **not passed** — the strictest reading. Both readings are given so the choice can be checked either way:

| Model | Completed | Excluding the missing task | Worst case /20 | Best case /20 |
|---|---|---|---|---|
| `z-ai/glm-5.3-flash` | 19/20 | 16/19 = 0.842 | 16/20 = 0.80 | 17/20 = 0.85 |

**The selection is invariant across every outcome of the 1 unfinished task(s):** each still-missing task belongs to a candidate whose pass rate is outside the 35–75% window whether it passes or fails, so no outcome changes which model the rule picks.

**Rule (0001 / 0004 §4.3):** among candidates that are available and reach ≥ 95% valid tool calls, take the pass rate inside (0.35, 0.75) and closest to 0.55; ties → higher measured rpm → candidate list order.

**Chosen agent: nvidia/nemotron-3-super-120b-a12b** — pass rate 0.60 is closest to 0.55 among candidates meeting the 0.95 tool-call floor

### DeepSeek tool-call re-check

`deepseek-ai/deepseek-v4-flash-0731` was re-checked with a proper `tools` payload and `tool_choice="auto"` on a prompt that clearly needs the tool: it emitted structured tool calls on attempt 1 → **usable as an agent = True**. P0a's availability smoke had recorded "no", but that test used an unrelated dummy weather tool; the re-check supersedes it.

## 4. User simulator

**Chosen: `nvidia/nemotron-3.5-lightning-30b-a3b`** — clean: no errors, no empty messages, and at least one conversation ended (user_stop, user_stop)

## 5. Judge

| Judge | Median latency over 5 calls | Budget |
|---|---|---|
| `moonshotai/kimi-k3` | 161.6 s | ≤ 30 s |
| `nvidia/nemotron-3-ultra-550b-a55b` | 7.5 s | ≤ 30 s |

Prompt: 12213 characters (~3053 tokens), built from a real recorded probe trajectory.

**Chosen: `nvidia/nemotron-3-ultra-550b-a55b`** — first candidate in list order with median latency 7.5s <= 30s

## 6. End-to-end check

`bisect doctor --live` ran airline task 0 end to end with the chosen models and got **reward = 1.0** (termination: user_stop, 22 messages, 231 s).

## 7. Throughput projection for P3

- Measured: 21.4 calls per task, 677 s per task, at concurrency 12.
- **Projected throughput: 1362 calls/hour.**
- The brief estimates P3's 120-failure collection at 8,000–12,000 calls → **5.9–8.8 hours of API time.**

**Pre-registered 60-failure fallback floor (0001, P3): NOT triggered** — the fallback applies only if the 120-target collection projects past 10 h; the upper estimate is 8.8 h, which is at or below that limit.

## 8. Calls spent

| Model | Calls |
|---|---|
| `deepseek-ai/deepseek-v4-flash-0731` | 284 |
| `moonshotai/kimi-k2.6` | 1 |
| `moonshotai/kimi-k3` | 65 |
| `nvidia/nemotron-3-super-120b-a12b` | 764 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 51 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 584 |
| `openai/gpt-oss-20b` | 811 |
| `z-ai/glm-5.3-flash` | 356 |
| **total** | **2916** |
