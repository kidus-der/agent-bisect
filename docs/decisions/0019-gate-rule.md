# 0019 — The P7 PR-check gate rule, pre-registered

- **Date:** 2026-09-17, written **before `bisect gate` is run against any
  base/head pair**, real or planted. No gate evaluation, planted-regression
  branch, or PR exists yet.
- **Status:** accepted.
- **Scope:** `agent_bisect/gate/` — the PR check's regression rule and its
  blame trigger. Extends `docs/decisions/0001-preregistration.md` (P7 row)
  and reuses `attribution/estimate.py`'s Wilson/Newcombe machinery
  unchanged.

## The demo suite

`demo/` ships 8 scenarios on tau2's vendored **mock** domain
(`demo/tasks.py`'s `SCENARIOS`: `create_task`, `create_task_env_assertion`,
`update_task_fixed_id`, `update_task_from_history`,
`update_task_from_initialization_data`,
`update_task_from_initialization_actions`,
`update_task_history_env_assertion`, `impossible_delete`), each run
`runs_per_scenario` times (default 4) with a scripted, seeded, **stochastic**
agent (`demo/agent.py`) whose decisions are governed by an ordered rule list
in `demo/agent_policy.yaml`. Every task's `reward_basis` resolves without an
LLM call (DB / ACTION / ENV_ASSERTION / substring COMMUNICATE only — the two
mock tasks that need the NL-assertion judge, `create_task_1_nl_eval` and
`update_task_with_user_tools`, are excluded from the suite for that reason).
A run is `(scenario, run_index)`, seeded deterministically from
`(base_seed, scenario.name, run_index)` via `random.Random(str(...))`, so a
given commit and `--seed` reproduce byte-identical pass/fail on every
machine.

## The regression rule

Let `x1, n1` be head's pooled pass count and run count across all scenarios
in one gate invocation, and `x2, n2` base's. Report:

- **point estimate:** `p1 - p2` (head pass rate minus base pass rate)
- **interval:** `newcombe_diff_interval(x1, n1, x2, n2, conf=0.95)`
  (`attribution/estimate.py`, unchanged)
- **p-value:** the two-sided p-value of the pooled two-proportion z-test on
  the same counts, reported beside the interval, never in place of it

**A run is a regression iff both hold:**

1. The 95% Newcombe interval of `head − base` lies entirely below 0 (its
   `high` bound is `< 0.0`).
2. The point estimate drop is at least **10 percentage points**:
   `p2 - p1 >= 0.10`.

Both conditions are checked on the **same pooled counts**; neither is
softened by looking at individual scenarios first. A gate that fails either
condition is clean (exit 0) even if some individual scenario dropped more —
scenario-level rows are diagnostic, not gating, exactly as `EvaluationCriteria
.reward_basis` in tau2 gates the reward and other fields stay diagnostic
(`docs/decisions/0001-preregistration.md`'s own pattern, reused here).

These two numbers — Newcombe 95%, 10-point floor — are fixed now and are
never lowered after a gate result is seen (`0001`'s rule, restated for this
gate).

## Which failures get blamed

When regressed, blame runs on **new failures**: a `(scenario, run_index)`
pair whose **head** run failed while the **base** run of the same
`(scenario, run_index)` — same seed, same scripted user, same task —
passed. A head failure whose base counterpart also failed is not new and is
not blamed; it is listed in the comment's scenario table but does not feed
the decisive-step count.

## The label-free shortlist ("judge")

No LLM and no secret is available in demo mode, so the shortlist is a fixed
heuristic, not tau2's real judge:

> **First divergence.** Walk the new failure's head run and its base
> counterpart's steps in tape order. The first index at which `(actor,
> tool_name, tool_args)` differs, or — for a text turn — the decoded
> response content differs, is rank 1. The next differing index after it is
> rank 2. `top_m = 3` (unchanged from `BlameConfig`'s default); if fewer than
> 3 divergences exist the shortlist is shorter, never padded.

This is a heuristic, not the judge scored in P5: it uses the base run as an
oracle a real PR check would not have. It is documented here, in
`demo/blame.py`'s docstring, and in the PR comment's own "details" line, and
is used **only** in `mode: demo`. `mode: live` (not exercised in this phase;
`docs/decisions/0001`'s live-mode note) uses the real all-at-once judge from
`attribution/judge.py` exactly as P5 does, with `secrets.NVIDIA_API_KEY`.

## Confirmation, once shortlisted

Unchanged from `docs/decisions/0013-suspect-interventions.md`:
`TruthfulToolResult` on tool steps, `Resample` on agent/user steps, shared
control forked at the earliest tested step
(`docs/decisions/0005-shared-control.md`). `SequentialConfig(batch=8,
max_n=8, delta=0.10, efficacy_boundary="none")` — a single-look fixed-N
design, not P5's `obf` primary, because the demo suite has no
interim-monitoring requirement and every re-run here is scripted (no API
call, no cost, no rate limit) — the limit on `N` is wall time (each re-run
still drives a real tau2 orchestrator, and one gate invocation confirms
every new failure separately), not budget. N=8 gives the demo's own
agent-decision steps (`use_stated_title`, `set_completed_status`,
`escalate_impossible_requests`, confirmed through `Resample`) a real chance
to clear delta at their modest default slip probabilities, where N=4 would
not (`demo/agent.py`'s module docstring explains why `Resample` has any
power here at all: the slip draw is seeded from the *forked* run's own id,
not the scenario's). This is a deviation from P5's primary
`efficacy_boundary`, is listed as such here, and applies to `gate/` alone.

## Naming the decisive step

Across all new failures, the decisive step is the **mode** of each item's
`BlameResult.blamed_step` (ties broken by the smaller step index, then by
which shared control step was forked earliest). The comment reports how
many of the *n* new failures share it, out of *m* new failures total.

## Why these numbers

- **10 points, not P4/P5's `delta=0.10` on an individual step's effect** —
  a different quantity (suite-level pass-rate drop, not one step's
  counterfactual effect) reusing the same round number for readability; the
  two are not the same test and are not claimed to be.
- **Newcombe over a plain two-sample z CI** — one implementation, already
  validated by `tests/test_p4_gate.py` and used everywhere else in this
  project a proportion difference is reported; a second interval formula
  for the same job would be an unjustified second thing to get wrong.
- **Pooled counts, not per-scenario** — 8 scenarios × 4 runs is a small `n`
  per scenario (Wilson/Newcombe would be very wide); pooling to the suite
  level is what makes a 10-point drop detectable at N≈32 per side without
  raising `runs_per_scenario` past what a demo PR check can afford to run
  synchronously.
