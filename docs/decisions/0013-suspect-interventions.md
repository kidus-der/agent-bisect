# 0013 — Which intervention Bisect applies to a suspect step

- **Date:** 2026-09-17, written **before any P5 measurement exists** (no live blame run, no
  evaluation on either split; the planted-fault dataset is not yet frozen).
- **Status:** accepted.
- **Scope:** `attribution/search.py` — the confirmation half of Bisect, after the judge's
  shortlist and before the estimator.

## Decision

The intervention applied to a shortlisted suspect step `k` is chosen **by the recorded
actor of that step alone**, with no knowledge of the label, the fault type, the base run,
or the oracle fix:

| recorded `Step.actor` | intervention | what it does |
|---|---|---|
| `tool` | `TruthfulToolResult(k)` | re-executes the recorded tool call against the snapshot-restored state and shows the agent the **true** result |
| `agent` | `Resample(k)` | draws a fresh sample from the same model, same request — nothing else changed |
| `user` | `Resample(k)` | same, for the user-simulator turn |
| `evaluator` | not shortlisted | τ²'s NL-assertion judge runs after the loop; it cannot be a causal step of the trajectory, so it is excluded from the candidate set before the judge ever sees it |

The control arm applies `NoOpIntervention` at the earliest tested step (shared control,
`docs/decisions/0005-shared-control.md`).

## Why label-free matters

`ReplaceToolResult(k, original_result)` — restoring exactly the value `bench/inject.py`
overwrote — is the *oracle* fix. It is strictly more informative than anything a user of
the tool would have, because it requires knowing both which step was planted and what was
there before. Using it inside the search would measure "can the estimator detect a fault we
already located and already know the fix for", which is not the claim in
`docs/brief/summary.md` §1.

`TruthfulToolResult(k)` needs neither. It re-executes the call the agent actually made
against the world state as restored at `k` and returns whatever the environment says. On a
planted fault this recovers the original value (the fault was an overwrite of a
deterministic tool's output), so it is **as strong as** the oracle there; on a real,
un-planted failure it is still well defined, which the oracle is not. Every number Bisect
reports in P5 is produced with this intervention.

`ReplaceToolResult` and `ForceAction` remain in the codebase — `bench/inject.py` uses the
first to plant faults, and `attribution/repair.py` uses both for LLM-proposed repairs on
real failures. Neither is used by the search, and repair results are scored in a separate
table (`docs/brief/summary.md` §9 fact 5).

## Why `Resample` for agent and user steps

An agent turn has no "true" counterfactual value to substitute: there is no oracle for what
the model *should* have said, and forcing a hand-written action would smuggle the
experimenter's judgement into the measurement. `Resample` changes exactly one thing — the
random draw — which answers the question the brief poses for these steps: *bad luck or bad
policy?* A step whose effect is large under `Resample` was decided by a coin flip the run
lost; a step whose effect is ~0 was decided by the policy, and re-rolling it changes
nothing.

Consequence, stated in advance: on the planted-fault dataset every label is a **tool** step
(`docs/decisions/0001-preregistration.md` fixes the fault step as a tool-result step), so
agent/user suspects in a shortlist are by construction non-labels. `Resample` on them is
expected to give effects near zero, which is the correct answer — but it means Bisect's
measured accuracy on this dataset does not test the `Resample` arm's *power*, only that it
does not produce false blames. That limitation belongs in the report, not in a change to
this policy.

## Alternatives rejected

- **Ask the judge which intervention to use.** Adds a second failure mode of the judge to
  the thing being compared *against* the judge, and makes the cost of a diagnosis depend on
  judge verbosity. Rejected.
- **Try every intervention on every suspect.** Multiplies cost by the number of
  intervention types and inflates the false-blame rate through multiplicity, on a design
  whose whole point is that it controls exactly that (`docs/decisions/0008-*`). Rejected.
- **`Resample` on tool steps too.** τ²'s airline and retail tools are deterministic given
  the DB, so resampling a tool step is a no-op by construction — it would report effect 0
  for every tool step, i.e. for every planted label. Rejected as vacuous. (In the flaky
  world it would stop being vacuous and start being noise, which is worse.)
