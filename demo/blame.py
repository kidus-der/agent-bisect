"""The label-free shortlist and confirmation for one new demo failure.

No LLM and no secret exist in demo mode, so the judge `attribution.search
.run_blame` normally asks first is replaced with a fixed heuristic:
**first divergence**. A new failure (a `(scenario, run_index)` pair that
failed on head but passed on base) is compared step by step against its
base counterpart; the first index where `(actor, tool_name, tool_args)` or
the decoded response content differs is rank 1, the next differing index is
rank 2, up to `top_m`. This is a heuristic, not the judge P5 scores — it
uses the base run as an oracle a real PR check would not have — and it is
used only in `mode: demo` (`docs/decisions/0019-gate-rule.md`). `mode: live`
uses `attribution.judge` exactly as P5 does.

Confirmation, once shortlisted, is unchanged: `attribution.search.run_blame`
picks `TruthfulToolResult` for a tool step and `Resample` for an
agent/user step by actor alone (`docs/decisions/0013-suspect-interventions.md`),
against a shared control forked at the earliest tested step.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor
from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
from agent_bisect.attribution.estimate import SequentialConfig
from agent_bisect.attribution.judge_view import CANDIDATE_ACTORS, JudgeVerdict, RankedStep
from agent_bisect.attribution.search import BlameConfig, BlameResult, run_blame
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Step, TapeReader, TapeWriter

from demo.tasks import DOMAIN, scenario

#: Free (no cost, no rate limit -- every re-run is scripted), but each
#: re-run still spins up a real tau2 orchestrator, and a suite-level
#: regression routinely produces several new failures at once, each
#: confirmed separately -- N=8 (`docs/decisions/0019-gate-rule.md`) is
#: chosen for practical PR-check wall time, not for cost.
DEMO_SEQUENTIAL = SequentialConfig(batch=8, max_n=8, delta=0.10, efficacy_boundary="none")
DEMO_TOP_M = 3

FIRST_DIVERGENCE_PROTOCOL = "all_at_once"


class JsonBlobs(Protocol):
    """What the divergence heuristic needs from a blob store: reading one
    blob back by its ref. `core.store.BlobStore` satisfies this; a fake in
    a test needs nothing more."""

    def get_json(self, digest: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class NewFailure:
    """One `(scenario, run_index)` pair that regressed: head failed, base did not."""

    scenario_name: str
    run_index: int
    head_run_id: str
    base_run_id: str


def _decoded_content(store: JsonBlobs, ref: str | None) -> str:
    if ref is None:
        return ""
    payload = store.get_json(ref)
    if isinstance(payload, dict) and "choices" in payload:
        message = payload["choices"][0].get("message") if payload["choices"] else {}
        return json.dumps(
            {"content": message.get("content"), "tool_calls": message.get("tool_calls")},
            sort_keys=True,
        )
    return json.dumps(payload, sort_keys=True)


def _fingerprint(store: JsonBlobs, step: Step) -> tuple[Any, ...]:
    content_ref = step.tool_result_ref if step.actor == "tool" else step.response_ref
    return (step.actor, step.tool_name, step.tool_args, _decoded_content(store, content_ref))


def first_divergence_steps(
    *,
    head_store: JsonBlobs,
    base_store: JsonBlobs,
    base_steps: Sequence[Step],
    head_steps: Sequence[Step],
    top_m: int = DEMO_TOP_M,
) -> tuple[int, ...]:
    """The first `top_m` step indices where head diverges from base.

    `head_store` and `base_store` are separate blob stores -- head and base
    are recorded in different worktrees' own `runs/` directories -- so each
    side's steps are decoded against its own store.

    Only candidate actors (`agent`, `user`, `tool`) are ever returned --
    tau2's NL-assertion evaluator runs after the loop and cannot be a
    causal step of the trajectory
    (`docs/decisions/0013-suspect-interventions.md`).
    """
    divergent: list[int] = []
    for base_step, head_step in zip(base_steps, head_steps, strict=False):
        if head_step.actor not in CANDIDATE_ACTORS:
            continue
        if base_step.step_idx != head_step.step_idx:
            continue
        if _fingerprint(base_store, base_step) != _fingerprint(head_store, head_step):
            divergent.append(head_step.step_idx)
        if len(divergent) >= top_m:
            break
    if not divergent and len(head_steps) > len(base_steps):
        # head ran longer than base with an identical shared prefix: the
        # first step base never took is itself the divergence.
        extra = head_steps[len(base_steps)]
        if extra.actor in CANDIDATE_ACTORS:
            divergent.append(extra.step_idx)
    return tuple(divergent[:top_m])


def first_divergence_verdict(
    *,
    item_id: str,
    head_store: JsonBlobs,
    base_store: JsonBlobs,
    base_steps: Sequence[Step],
    head_steps: Sequence[Step],
    top_m: int = DEMO_TOP_M,
) -> JudgeVerdict:
    """A `JudgeVerdict`-shaped answer from `first_divergence_steps`, cost-free."""
    steps = first_divergence_steps(
        head_store=head_store, base_store=base_store,
        base_steps=base_steps, head_steps=head_steps, top_m=top_m,
    )
    if not steps:
        return JudgeVerdict(
            item_id=item_id, protocol=FIRST_DIVERGENCE_PROTOCOL, decisive_step=None,
            ranking=(), rationale="no divergence found against the base run", calls=0,
            steps_examined=len(head_steps), parse_failed=True,
            failure_reason="head and base trajectories agree everywhere compared",
        )
    ranking = tuple(
        RankedStep(step=step, rank=rank, score=max(0.1, 0.9 - 0.2 * (rank - 1)),
                    rationale="first point of divergence from the base run's trajectory")
        for rank, step in enumerate(steps, start=1)
    )
    return JudgeVerdict(
        item_id=item_id, protocol=FIRST_DIVERGENCE_PROTOCOL, decisive_step=steps[0],
        ranking=ranking, rationale="label-free first-divergence heuristic (demo mode)",
        calls=0, steps_examined=len(head_steps),
    )


def blame_new_failure(
    failure: NewFailure,
    *,
    head_store: BlobStore,
    head_reader: TapeReader,
    head_tape: TapeWriter,
    base_store: BlobStore,
    base_reader: TapeReader,
    live_completion: Callable[..., Any],
    seed: int,
) -> BlameResult:
    """Shortlist by first divergence, then confirm exactly as `run_blame` would.

    Forks are written to `head_store`/`head_tape` -- `failure.head_run_id`
    lives there, and so must every fork of it. `base_store`/`base_reader`
    are read only, for the divergence comparison.

    `live_completion` must be the *router's* completion -- the object
    `recording_session(...) as router` yields, called as
    `router.completion` -- never a bare completion function and never
    `llm_utils.completion` read off the seam. `Tau2ForkExecutor` no longer
    accepts a default for this (its own docstring explains why: an
    unrecorded live call stalls the replayer's step count, and reading the
    seam picks up the replay dispatcher and recurses).
    """
    spec = scenario(failure.scenario_name)
    head_steps = head_reader.get_steps(failure.head_run_id)
    base_steps = base_reader.get_steps(failure.base_run_id)
    verdict = first_divergence_verdict(
        item_id=failure.scenario_name, head_store=head_store, base_store=base_store,
        base_steps=base_steps, head_steps=head_steps,
    )
    executor = Tau2ForkExecutor(
        store=head_store, reader=head_reader, tape=head_tape, live_completion=live_completion
    )
    truth = Tau2TruthResolver(DOMAIN, spec.task_id, head_store)
    return run_blame(
        item_id=failure.scenario_name,
        run_id=failure.head_run_id,
        steps=head_steps,
        verdict=verdict,
        executor=executor,
        config=BlameConfig(top_m=DEMO_TOP_M, sequential=DEMO_SEQUENTIAL, control_mode="shared"),
        seed=seed,
        truth_for=truth,
    )
