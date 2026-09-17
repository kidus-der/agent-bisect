# 0018 — Retail's NL-assertion judge is routed to the model P0 chose

- **Date:** 2026-09-17 17:45, during the P3 collection, **before any retail
  item was kept** (0 retail candidates had reached a verdict; the 32 affected
  tasks all died before scoring).
- **Status:** accepted.
- **Extends:** `0004-p0-probe-protocol.md` §4.2 (judge choice),
  `0010-replay-mechanism.md` §"The evaluator",
  `0017-p3-collection-policy.md` §1 (task order).

## What happened

Thirty-two retail tasks died inside 30 minutes with

```
TransportError: NotFoundError: litellm.NotFoundError: 404 page not found
```

Every one was retail; no airline task was affected.

τ² scores a task's natural-language assertions with a judge whose model is a
module constant, `tau2.config.DEFAULT_LLM_NL_ASSERTIONS = "gpt-4.1-2025-04-14"`,
and it runs that judge on one condition:

```python
task_needs_nl = RewardType.NL_ASSERTION in task.evaluation_criteria.reward_basis
```

— `evaluator/evaluator.py`. **It does not also require the task to list any
assertions.** That is **112 of the 114** retail tasks, not the 40 that
`0010` counted as "both listing `nl_assertions` and carrying NL_ASSERTION".
`0017` §1 inherited that undercount and put 74 retail tasks in the cheap band;
they were not cheap, and the model their reward calls does not exist on this
account's endpoint.

## The decision

1. **`needs_a_judge` is corrected** to τ²'s own condition — the reward basis
   alone. Retail is therefore 112 judged tasks and 2 unjudged, and the task
   banding in `0017` §1 follows that.
2. **τ²'s NL-assertion judge is routed to the judge model P0 chose**
   (`config/models.toml`, `nvidia/nemotron-3-ultra-550b-a55b`), for the
   duration of a collection session, by re-pointing the constant on
   `tau2.evaluator.evaluator_nl_assertions` — where it is imported by value, so
   re-binding `tau2.config` would not reach it.

The alternative was to drop every task whose reward calls a judge, which means
dropping retail: 112 of 114. `0001` fixes the dataset as **airline and retail**,
so that is not a choice available after the fact.

The call is unchanged in every other respect. It goes through
`llm_utils.completion`, so it is rate-limited, ledgered, recorded as an
`evaluator` step and replayed from the tape like any other — only the model
answering it differs.

## What it costs, stated plainly

- Those 112 tasks now have **an LLM in their reward path**: one extra call per
  run *and* per re-run, so ~5 extra calls per stability check and ~4 per
  candidate.
- More importantly, it puts a **sampled quantity inside the measurement**. The
  stability bar (≥ 0.75) and the keep rule (≤ 0.25) are measured on rewards
  that now depend on a judge's answer, so some of the variation they see is the
  judge's rather than the agent's. Airline is unaffected: 0 of its 50 tasks
  carry NL_ASSERTION, and its reward remains pure code.
- The judge is **not τ²'s default**, so a retail reward here is not
  bit-comparable with a published τ²-bench number. Nothing in this study
  compares against one, and `docs/gates/P3.md` and the final report say which
  model scored which domain.

Because of the cost and the added variance, retail stays in the **last** band of
the collection order: airline first, then the two unjudged retail tasks, then
the judged ones. If the target is met on airline alone, retail contributes what
time allows and the dataset card reports the split by domain.
