"""The task text and the domain policy the agent itself was given.

The judge is shown exactly this and the trajectory — no more
(`attribution/judge_view.py`). It comes from tau2's own task and policy
documents rather than from anything the recorder derived, so a judge run
over a recording sees what a user of the tool would see.

The task's `evaluation_criteria` is deliberately **not** read: it holds the
expected actions, the NL assertions and the reward basis, which is the
answer key for the run being judged.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

#: Returned when the domain ships no policy document.
NO_POLICY = "(this domain ships no policy document)"


class TaskNotFoundError(LookupError):
    """No task with this id in this domain."""


def _find_task(domain: str, task_id: str) -> Any:
    from tau2.registry import registry

    # The loader is typed `Callable[[Optional[str]], list[Task]]` but
    # documents `func()` as valid; passing the split name explicitly as
    # `None` asks for the full set and satisfies the annotation.
    for task in registry.get_tasks_loader(domain)(None):
        if str(task.id) == str(task_id):
            return task
    raise TaskNotFoundError(f"no task {task_id!r} in domain {domain!r}")


def _describe(task: Any) -> str:
    """The instruction as the agent's counterpart received it.

    tau2 keeps the user's brief in `user_scenario.instructions`; its
    `purpose`/`task_instructions` fields are free text and differ per
    domain, so every part that exists is included and nothing is invented.
    """
    scenario = getattr(task, "user_scenario", None)
    instructions = getattr(scenario, "instructions", None)
    if instructions is None:
        return str(getattr(task, "description", "") or "")
    parts = [
        str(getattr(instructions, field, "") or "")
        for field in ("domain", "reason_for_call", "known_info", "task_instructions")
    ]
    return "\n".join(part for part in parts if part)


@lru_cache(maxsize=8)
def policy_of(domain: str) -> str:
    """The domain policy document tau2 gives the agent.

    It lives on the environment (`Environment.get_policy`), so a fresh one
    is built to read it. That is a DB rebuild and no network call, and the
    result is cached because the policy is fixed per domain.
    """
    from tau2.registry import registry

    try:
        policy = registry.get_env_constructor(domain)().get_policy()
    except Exception:  # noqa: BLE001 - a missing policy is a fact, not a crash
        return NO_POLICY
    return str(policy or NO_POLICY)


def task_text(domain: str, task_id: str) -> tuple[str, str]:
    """`(task description, domain policy)` for one recorded run."""
    return _describe(_find_task(domain, task_id)), policy_of(domain)
