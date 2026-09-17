"""Planting the one demo regression type confirmable through a tool step.

`use_correct_task_id`'s slip on the two "fresh" `update_lookup` scenarios
(`update_task_from_initialization_data`, `update_task_from_initialization_actions`)
is not a decision the scripted agent makes -- it always trusts
`get_users()`'s answer (`demo/agent.py`). The regression lives in what that
call returns instead: this module forks the clean base recording at its
`get_users()` step, replaces the answer with one that drops `user_id`'s most
recently created task, and installs it as a **standing** fault
(`docs/decisions/0016-persistent-planted-fault.md`) so a later fork taken by
the PR check's blame search reproduces it too. Confirming it back is
`attribution.TruthfulToolResult`'s job, using
`adapters.tau2_truth.Tau2TruthResolver` unmodified: a fresh, uninjected
environment answers `get_users()` truthfully regardless of the domain, so
nothing here needs its own truth provider.
"""

from __future__ import annotations

import json
from typing import Any

from agent_bisect.adapters.tau2_fault_fork import FaultedForkDriver
from agent_bisect.adapters.tau2_fault_injector import FaultSpec
from agent_bisect.attribution.interventions import ReplaceToolResult
from agent_bisect.core.replay import DivergenceError
from agent_bisect.core.runner import ForkSpec, run_fork
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, Step, TapeReader, TapeWriter

#: The label for this fault, carried in `FaultSpec.fault_type` and reported
#: in the PR comment's "caused by" line.
WRONG_LOOKUP_KEY = "wrong_lookup_key"


class NoGetUsersStepError(LookupError):
    """The run this fault targets never called `get_users()`."""


def get_users_step(reader: TapeReader, run_id: str) -> Step:
    """The first `get_users()` tool step of `run_id`, or an error."""
    for step in reader.get_steps(run_id):
        if step.actor == "tool" and step.tool_name == "get_users":
            return step
    raise NoGetUsersStepError(f"run {run_id!r} has no get_users() step to corrupt")


def corrupted_get_users_result(
    store: BlobStore, step: Step, *, user_id: str = "user_1"
) -> dict[str, Any]:
    """`get_users()`'s recorded answer with `user_id`'s newest task dropped.

    Dropping the *last* entry rather than the whole list keeps the
    corruption minimal: a user with only one task still has one, so a
    scenario the agent has no reason to distrust stays untouched.
    """
    if step.tool_result_ref is None:
        raise DivergenceError(
            step_idx=step.step_idx, actor="tool",
            expected="a recorded get_users() result", got="no tool_result_ref",
            diff="the get_users() step has no result blob to corrupt",
        )
    payload = dict(store.get_json(step.tool_result_ref))
    users = json.loads(payload["content"])
    corrupted = [
        {**user, "tasks": list(user.get("tasks") or [])[:-1]}
        if isinstance(user, dict) and user.get("user_id") == user_id
        else user
        for user in users
    ]
    return {**payload, "content": json.dumps(corrupted)}


def plant_wrong_lookup_key(
    *,
    parent_run_id: str,
    run_id: str,
    store: BlobStore,
    reader: TapeReader,
    tape: TapeWriter,
    live_completion: Any,
) -> Outcome:
    """Fork `parent_run_id` with `get_users()` corrupted, standing.

    `parent_run_id` must be a clean recording of one of the two "fresh"
    `update_lookup` scenarios. The fork's manifest carries the fault
    (`FaultedForkDriver`), so any later fork of `run_id` -- the PR check's
    blame confirmation included -- reproduces the same wrong answer.
    """
    step = get_users_step(reader, parent_run_id)
    faulted_result = corrupted_get_users_result(store, step)
    intervention = ReplaceToolResult(step=step.step_idx, new_result=faulted_result)
    fault = FaultSpec.from_mutation(
        tool_name="get_users",
        tool_args={},
        mutated=faulted_result,
        step_idx=step.step_idx,
        fault_type=WRONG_LOOKUP_KEY,
    )
    spec = ForkSpec(
        parent_run_id=parent_run_id,
        run_id=run_id,
        fork_step=step.step_idx,
        prefix_tools="snapshot",
        seed=None,
    )
    driver = FaultedForkDriver(
        spec,
        store=store,
        reader=reader,
        tape=tape,
        live_completion=live_completion,
        fault=fault,
    )
    return run_fork(driver, spec, intervention)
