# 0010 — Replay mechanism: re-drive τ²'s real orchestrator from step 0

- **Date:** 2026-09-17, written before `core/replay.py`, `core/runner.py` and `adapters/tau2*.py` were implemented (P1b/P2, stage A — offline).
- **Status:** accepted.

## Decision

`restore(k) → apply(intervention) → run_rest(seed)` is implemented by **re-driving τ²'s
real `Orchestrator` from step 0** with a tape-backed `completion` function in place of
litellm's, not by constructing a task whose `initial_state.message_history` starts the
conversation at step k.

- Steps `< k`: LLM responses come from the tape; each incoming request's
  `canonical_request_hash` is compared with the recorded one and a mismatch raises
  `DivergenceError`. Zero network calls.
- Step `k`: the recorded payload is passed through the `Intervention` before use
  (identity for the no-op intervention; an intervention may instead return the `LIVE`
  sentinel to force a fresh sample).
- Steps `> k`: the LLM source switches to live — for the agent **and** the user
  simulator — and the new steps are recorded to the tape as a forked run
  (`parent_run_id`, `fork_step`).

## Why not `initial_state.message_history`

τ² does support starting mid-conversation: `Orchestrator.initialize()` accepts a
`message_history` and `Environment.set_state()` rebuilds the DB by replaying the tool
calls found in that history
(`vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py:483-666`,
`.../environment/environment.py:288+`). It was rejected for four concrete reasons:

1. **It rebuilds state by re-executing tools.** `set_state` replays every mutating tool
   call in the history and compares its output with the recorded `ToolMessage`. That is
   precisely the CAR-style *no-snapshot* baseline, so it cannot express Bisect's
   `prefix_tools="snapshot"` arm at all — the arm whose difference from the baseline is
   what P5 measures.
2. **Counters do not resume.** `initialize()` leaves `step_count = 0` and
   `num_errors = 0`, so a fork at k gets a different `max_steps` / `max_errors` budget
   than the recorded run had at the same point
   (`orchestrator.py:130-139`, `:734-750`). Re-driving from 0 reproduces both exactly.
3. **Arbitrary k is not always a legal history.** `validate_message_history`
   (`orchestrator.py:922-954`) requires every tool call to be followed by exactly its
   own tool messages. Our tape's step granularity is one row per *individual* tool
   execution, so a fork inside a multi-tool agent turn is a legal Bisect step but an
   illegal τ² `message_history`.
4. **No prefix verification.** Injecting a history asserts nothing about whether the
   prefix would still be produced. Re-driving hashes every prefix request against the
   recording, which is what makes divergence loud (rule 3 of `docs/brief/summary.md` §3).

Re-driving costs nothing extra: the prefix makes no network calls, and τ²'s airline and
retail tools are deterministic given the DB, so the prefix is fast.

## The seam

`tau2.utils.llm_utils.generate()` is the one function every τ² participant calls, and it
dispatches through the module-level `completion` symbol (`llm_utils.py:15`, `:409`) —
the agent (`agent/llm_agent.py:133`), the user simulator (`user/user_simulator.py`) and
the evaluator's NL-assertion judge (`evaluator/evaluator_nl_assertions.py:13,121`). So
rebinding `llm_utils.completion` covers every LLM call, which is what
`adapters/tau2_llm.route_tau2_llm` already does for the live path. Replay nests a second
rebinding inside it, so the live suffix still goes through the limiter, the ledger and
the retry policy, while tape-served calls touch none of them.

Tool executions are intercepted at `Environment.get_response` — the single call site the
orchestrator uses for tool execution (`orchestrator.py:325`).

## Step granularity

One tape row per LLM call and one per *individual* tool execution:

| actor | one row per |
|---|---|
| `agent` | one agent LLM call |
| `user` | one user-simulator LLM call |
| `tool` | one `Environment.get_response(tool_call)` — a 2-tool agent turn writes 2 rows |
| `evaluator` | one evaluator LLM call (τ²'s NL-assertion judge), after the loop |

This is finer than τ²'s own `step_count` (which advances once per orchestrator turn,
however many tool calls it carried) because a step must be an interventionable unit:
`ReplaceToolResult` targets exactly one tool result.

## The evaluator

τ²'s reward is computed inline by `run_simulation` (`runner/simulation.py:76`).
`NLAssertionsEvaluator` calls an LLM (`evaluator_nl_assertions.py:121`), but only when
`RewardType.NL_ASSERTION` is in the task's `reward_basis`
(`evaluator/evaluator.py:215-220`). Measured on the vendored data:

- **airline: 0 of 50 tasks** have `NL_ASSERTION` in `reward_basis` — the reward for
  every airline task, including the 20 recorded in P1, is pure code (DB hash + action +
  communicate checks) and makes **no LLM call**.
- **retail: 40 of 114 tasks** both list `nl_assertions` and carry `NL_ASSERTION` in
  `reward_basis` — those do make an evaluator LLM call.

Because it goes through the same `llm_utils.completion` seam, an evaluator call is
recorded and replayed like any other, under actor `evaluator` — verified end to end on
retail task 2, whose `reward_basis` is `["DB", "NL_ASSERTION"]`: the judge's call is
recorded as the run's last step, and on replay the reward is reproduced from the
recorded verdict without asking it again. τ²'s opt-in reviewers
(`review_llm_judge*.py`, `hallucination_reviewer.py`, `auth_classifier.py`) are not on
the reward path (`auto_review=False` by default) and are never enabled.

**The evaluator also executes tools, on an environment of its own.** `EnvEvaluator`
builds a fresh DB and replays the trajectory's write actions against it to compare
hashes (`evaluator/evaluator_env.py`). Those executions are not steps of the run: the
recorder wraps the orchestrator's environment *instance*, not the class, so they are
neither recorded nor replayed, and they do not need to be — they are a deterministic
function of the trajectory, which is itself on the tape. It is worth knowing for the
flaky world (P5): a non-deterministic tool would make the evaluator's own replay drift
too, independently of anything the replay engine does.

## Determinism hazards in τ², and how each is neutralised

| Hazard | Where | Handling |
|---|---|---|
| message `timestamp` (wall clock) | `data_model/message.py:39,215,570` | Never serialised into a request (`to_litellm_messages`, `llm_utils.py:168-208`) and never part of `get_db_hash()`; only used to sort the trajectory, where the sort is stable and the clock monotonic. Covered by a pinning test. |
| `simulation_id` uuid4 | `orchestrator.py:124` | Pinned: we pass `simulation_id=<our run_id>`. |
| tool-call ids | — | Not generated locally; copied out of the LLM response (`llm_utils.py:436-442`), so they come from the tape. |
| litellm response `id` / `created` | litellm | Inside the recorded response blob and rehydrated verbatim, so identical on replay. |
| wall-clock `timeout` termination | `orchestrator.py:224-235` | Forced to `None` for record and replay; only `max_steps` (deterministic) may terminate. |
| threads | `runner/worker.py`, `runner/batch.py` | Not used: a single simulation is strictly sequential (`orchestrator.py:279-282`). Our batch driver runs whole runs in parallel, each with its own recorder. |
| dict/set ordering | `utils/utils.py:39-45` | `get_dict_hash` uses `json.dumps(..., sort_keys=True)`. |
| `random` in the text path | — | None: `set_seed` is a no-op for `LLMAgent`/`UserSimulator`, and airline/retail tools use no RNG, clock, network or filesystem. |

## Consequences

- Full-run replay is the same code path with `k = ∞`: everything from tape, tools
  re-executed and verified against their recorded result and state hash.
- `prefix_tools="snapshot"` (serve recorded tool results, restore the DB from the
  recorded snapshot, check the hash) and `prefix_tools="rerun_live"` (execute the tools
  for real, no restore) are the two modes P5's baseline comparison needs; on
  deterministic τ² they agree, and the flaky-world adapter is where they must not.
- `core/` stays free of τ²: `core/replay.py` and `core/runner.py` define
  `TapeLLM`, `TapeTools`, `Intervention` and the `ForkDriver` protocol over plain
  payloads; all τ² wiring lives in `adapters/tau2*.py`.
