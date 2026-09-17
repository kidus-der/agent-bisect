# 0016 — A planted fault is a standing faulty tool, not a one-shot edit

- **Date:** 2026-09-17 13:35, **before any P3 collection or P5 evaluation was
  spent**. No planted-fault dataset existed; the only data was the offline dry
  run and `p5-blame`'s reproducing test.
- **Status:** accepted (orchestrator decision).
- **Extends:** `docs/decisions/0001-preregistration.md` (shared control, keep
  rule, N = 4, δ = 0.10, m = 3 — all unchanged), `0005-shared-control.md`,
  `0010-replay-mechanism.md`.
- **Finding:** `docs/findings/p5-control-fork.md` (p5-blame).

## The problem

A planted fault was a one-shot `ReplaceToolResult(k, mutated)`: at the fork
step the agent is shown a corrupted result, and the database is deliberately
left alone, which is what makes the oracle fix well defined.

But it also means **the fault lives in the recording, not in the world**. A
fork of the faulted item taken at any step *j < k* runs live from *j*, so the
tool at *k* executes against the real database and answers truthfully. The
fault disappears and the fork passes. Measured on airline task 1, planted step
4: a fork at step 4 fails 4/4, a fork at step 0 passes 4/4.

The pre-registered estimator uses a **shared control** — one control arm,
forked at the earliest tested step, reused for every candidate step
(`0005-shared-control.md`). Under a one-shot fault that control measures the
*base run*, not the failure: it passes, the treated arms pass, and
`effect(k) = P(pass | fix k) − P(pass | k as recorded)` collapses to ≈ 0 for
every k. The method would report "no step caused this" on a dataset built
entirely out of known causes.

It is not only P5's control. Anything that forks a dataset item before *k* —
the P7 PR check, the dashboard's re-run view — gets the base run back.

## Options considered

1. **Per-step control** — fork a fresh control at each tested step k, so the
   control always sits at or after the fault. *Rejected*: it deviates from the
   pre-registered shared control, which cannot be changed after the fact
   (`0001` rule: "no gate is changed after results are seen", and the estimator
   parameters are fixed), and it roughly doubles P5's replay spend.
2. **Standing faulty tool** — the fault is installed in the world for the
   duration of the run, so every fork reproduces it. **Chosen.**
3. **Report the null** — collect under the one-shot fault and report that
   Bisect finds nothing. *Rejected*: it would measure the semantics of forking,
   not the method. A number that is an artefact of the harness is worse than no
   number.

## The decision

A planted fault is a **`FaultInjector`**: a world component, recorded in the
faulted run's manifest, that

- matches exactly one call by `(tool_name, canonical tool_args)`;
- corrupts the **returned message** — the mutated content, and the error flag —
  every time that call executes, not once;
- leaves the **database untouched**, exactly as before, so the oracle fix stays
  "the original tool result" and the fault remains one of perception;
- passes every other call through unchanged;
- is deterministic and serialisable, so any later fork or replay of the item
  reconstructs it from the manifest.

Consequences, all of which keep the pre-registration intact:

- the shared control, forked at the earliest tested step, now reproduces the
  failure, so effects are measurable as designed;
- N = 4, the keep rule (faulted pass ≤ 0.25), the stability bar (≥ 0.75), δ and
  m are unchanged;
- the label is still k — the **first** occurrence of the matched call;
- **candidates whose call already occurred before k are skipped**, because a
  standing fault would rewrite the prefix and the recording would no longer be
  the base run's. The funnel logs them as `rejected_repeated_call`.
- `TruthfulToolResult(k)` is unaffected: `adapters/tau2_truth.Tau2TruthResolver`
  re-executes on a clean environment of its own, which never carries the
  injector. A *later* repeat of the same call inside the treated arm does still
  hit the standing fault — that is the world the fix was applied in, and it is
  documented rather than special-cased.

## Scope condition, for the report

Counterfactual replay with a shared control assumes **the failure is
reproducible from the fork point**. That is true of a persistent fault — a tool
that is wrong for a given query, a bad configuration, a stale cache — and it is
the case this dataset models. A genuinely one-shot transient glitch does not
satisfy it, and for those the estimator needs `control_mode="per_step"`, which
P5 reports as a sensitivity analysis on the dev split. The limitation is a
property of the shared control, not of counterfactual replay, and is stated in
the README and the final report.

`control_reproduces_failure` is computed per item by P5 from its control arm
and reported. It is a diagnostic, never a filter: items are not dropped on it.
