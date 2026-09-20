# 0014 — P5 tuning is finished; the test split may be opened

- **Date:** 2026-09-20, written after the dev split completed (6 of 6 items, 0 lost) and
  **before** `bisect eval --split test` has been run once.
- **Status:** accepted. This file's existence is what `bench/split_lock` checks; opening
  the test split also writes a one-time marker and refuses a second full run without
  `--resume`.

## What this declares

Every configuration choice P5 will use on the test split is fixed, and **nothing was tuned
on dev**. The dev split was used for exactly two things: to find bugs, and to produce the
diagnostics decision 0016 asked for.

## The configuration the test split will run under

Unchanged from the pre-registration and the decisions that preceded any live data:

| parameter | value | fixed in |
|---|---|---|
| δ | 0.10 | 0001 |
| batch / max N | 4 / 16 | 0001 |
| efficacy boundary | O'Brien–Fleming (primary), `none` as derived sensitivity | 0009 |
| shortlist m | 3 | 0001 |
| control | shared | 0005, 0016 |
| intervention per suspect | by step type, label-free | 0013 |
| planted fault | standing `FaultInjector` | 0016 |
| methods bought live | `bisect`, both judges | 0018 §2, 0022 |
| seed | 20260917 | — |

## What dev was used for, itemised

**Bugs found and fixed** (none of which changed a threshold, a prompt or a protocol):

1. the judge's output cap sat below its own chain-of-thought, so every item would have
   scored as a parse failure;
2. the judge cache key omitted `max_tokens`, so the fix for (1) was served the truncated
   answer;
3. a fork's live completion resolved to the replay dispatcher and recursed — every fork
   died, reported as a timeout;
4. infrastructure failures were scored as verdicts, publishing a network outage as 0.0
   accuracy for every method;
5. `rerun_id` omitted the prefix mode, so `rerun_live` silently reused Bisect's forks;
6. `no_control` was bought live instead of derived (0018 §2);
7. a supervisor kill orphaned its child, so up to three evaluations shared one tape;
8. a retried fork's outcome was invisible to resume, so draws were re-bought for ever.

**Diagnostics produced** (0016 item 1, and the numbers the report needs):

- `control_reproduces_failure`: **0 of 6 items flagged**. Control-arm pass rates 0.00,
  0.00, 0.00, 0.00, 0.10, 0.00 — the standing fault reproduces the recorded failure from
  any fork point, which is what 0016 exists to guarantee.
- replay integrity: **0** responses served past the request-hash guard.
- parse failures: **0**. Unevaluated items: **0**.

## Dev results, stated so they cannot later be mistaken for the test split

| method | accuracy | 95% CI | mean calls |
|---|---|---|---|
| `bisect` | 0.500 | [0.188, 0.812] | 431 |
| `judge_all_at_once` | 0.333 | [0.097, 0.700] | 1 |
| `judge_step_by_step` | 0.167 | [0.030, 0.564] | 16 |

Gap vs the better judge: **+16.7 points**, 95% CI **[0.000, 0.600]** — the interval touches
zero, as `docs/findings/p5-power.md` predicted it would at this n.

The per-item table is the finding: Bisect is **exact on 3 of 3** items whose shortlist
contained the planted step and blames nothing on the 3 where it did not. Accuracy is judge
recall@3 (0.50) multiplied by a conditional accuracy of 1.00.

**These are dev numbers and they gate nothing.** They are reported because hiding the split
you developed on is how a benchmark stops being one.

## The commitment

No parameter above moves after this file is committed. If the test split produces a
different picture, that is the result.
