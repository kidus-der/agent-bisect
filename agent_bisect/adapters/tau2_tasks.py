"""Which tau2 tasks to collect from, and in what order.

`docs/decisions/0017-p3-collection-policy.md` fixes the order before any
collection runs: airline first, then the retail tasks whose reward costs
no model call, then the rest. The point is not preference — it is that a
task whose reward is computed by an LLM adds a call per run *and* per
re-run, and puts a sampled quantity inside the very measurement the
stability check and the keep rule are making.

"Costs no model call" is a property of the task, not of the domain:
`NLAssertionsEvaluator` runs only when `NL_ASSERTION` is in the task's
`reward_basis` **and** the task actually lists `nl_assertions`
(`evaluator/evaluator.py`, `evaluator_nl_assertions.py`). Measured on the
pinned checkout: airline 0 of 50 judged, retail 40 of 114 — so 74 retail
tasks are as cheap to score as any airline task, even though 112 of them
carry `NL_ASSERTION` in the basis. Filtering on the basis alone would
wrongly defer all but two of them.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

#: Domains, in collection order.
DOMAINS: tuple[str, ...] = ("airline", "retail")

Task = tuple[str, str]


def _reward_basis(task: Any) -> list[str]:
    criteria = getattr(task, "evaluation_criteria", None)
    basis = getattr(criteria, "reward_basis", None) or []
    return [str(getattr(entry, "value", entry)) for entry in basis]


def needs_a_judge(task: Any) -> bool:
    """True when scoring this task makes an LLM call."""
    criteria = getattr(task, "evaluation_criteria", None)
    return "NL_ASSERTION" in _reward_basis(task) and bool(
        getattr(criteria, "nl_assertions", None)
    )


def writes_to_the_world(task: Any) -> bool:
    """True when the task's reward depends on the database being changed.

    A task with no required actions and nothing to communicate is scored
    almost entirely by the database being *unchanged*, so an agent that
    is merely misinformed still passes: there is nothing for a perception
    fault to break. Tasks that require writes are where a wrong value
    turns into a wrong action, which is what a planted fault has to do.
    """
    criteria = getattr(task, "evaluation_criteria", None)
    return bool(getattr(criteria, "actions", None))


@lru_cache(maxsize=4)
def _tasks_of(domain: str) -> tuple[tuple[str, bool, bool], ...]:
    """`(task_id, needs_a_judge, writes)` for a domain, in the file's order."""
    from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir

    ensure_tau2_data_dir()
    from tau2.run import get_tasks

    return tuple(
        (str(task.id), needs_a_judge(task), writes_to_the_world(task))
        for task in get_tasks(task_set_name=domain)
    )


def task_ids(
    domain: str, *, judged: bool | None = None, writes: bool | None = None
) -> list[str]:
    """Task ids of `domain`, filtered on what scoring costs and on writes."""
    return [
        task_id
        for task_id, is_judged, does_write in _tasks_of(domain)
        if (judged is None or is_judged == judged)
        and (writes is None or does_write == writes)
    ]


def collection_order(domains: tuple[str, ...] = DOMAINS) -> list[Task]:
    """Every task, best-yielding and cheapest-to-score first.

    Three bands, in order: tasks that are cheap to score **and** require
    writes; cheap tasks that require none; then the judged tasks. The
    middle band is where a planted perception fault has least to bite on
    (`docs/decisions/0017-p3-collection-policy.md` §7), so it goes after
    the band where a wrong value becomes a wrong action.
    """
    bands = (
        [(domain, task_id) for domain in domains
         for task_id in task_ids(domain, judged=False, writes=True)],
        [(domain, task_id) for domain in domains
         for task_id in task_ids(domain, judged=False, writes=False)],
        [(domain, task_id) for domain in domains
         for task_id in task_ids(domain, judged=True)],
    )
    return [task for band in bands for task in band]


def shard_of(tasks: list[Task], shard: int, shards: int) -> list[Task]:
    """`tasks` dealt round-robin into `shards`, taking the `shard`-th hand.

    Round-robin rather than contiguous blocks: the order is deliberately
    cheapest-first, so contiguous slices would give one worker all the
    expensive tasks and leave it running alone at the end.
    """
    if shards < 1 or not 0 <= shard < shards:
        raise ValueError(f"shard {shard} of {shards} is not a shard")
    return tasks[shard::shards]


@lru_cache(maxsize=4)
def write_tools(domain: str) -> frozenset[str]:
    """The domain's tools that change the world.

    A planted fault matters when its value flows into one of these: a
    wrong price the agent only reads is a wrong price nobody acts on, and
    a wrong price it pays with is a failed task.
    """
    from agent_bisect.adapters.tau2 import RunSpec, build_orchestrator

    environment = build_orchestrator(
        RunSpec(
            domain=domain,
            task_id=task_ids(domain)[0],
            agent_model="unused/agent",
            user_model="unused/user",
        ),
        f"write-tools-{domain}",
    ).environment
    return frozenset(
        tool.name
        for tool in environment.get_tools()
        if environment._is_mutating_tool(tool.name)  # noqa: SLF001 - tau2's own predicate
    )
