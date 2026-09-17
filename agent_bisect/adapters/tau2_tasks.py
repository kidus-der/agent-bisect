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


@lru_cache(maxsize=4)
def _tasks_of(domain: str) -> tuple[tuple[str, bool], ...]:
    """`(task_id, needs_a_judge)` for a domain, in the task file's order."""
    from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir

    ensure_tau2_data_dir()
    from tau2.run import get_tasks

    return tuple((str(task.id), needs_a_judge(task)) for task in get_tasks(task_set_name=domain))


def task_ids(domain: str, *, judged: bool | None = None) -> list[str]:
    """Task ids of `domain`; `judged` filters on whether scoring costs a call."""
    return [
        task_id
        for task_id, is_judged in _tasks_of(domain)
        if judged is None or is_judged == judged
    ]


def collection_order(domains: tuple[str, ...] = DOMAINS) -> list[Task]:
    """Every task, cheapest-to-score first, in the policy's order."""
    cheap = [
        (domain, task_id) for domain in domains for task_id in task_ids(domain, judged=False)
    ]
    judged = [
        (domain, task_id) for domain in domains for task_id in task_ids(domain, judged=True)
    ]
    return cheap + judged


def shard_of(tasks: list[Task], shard: int, shards: int) -> list[Task]:
    """`tasks` dealt round-robin into `shards`, taking the `shard`-th hand.

    Round-robin rather than contiguous blocks: the order is deliberately
    cheapest-first, so contiguous slices would give one worker all the
    expensive tasks and leave it running alone at the end.
    """
    if shards < 1 or not 0 <= shard < shards:
        raise ValueError(f"shard {shard} of {shards} is not a shard")
    return tasks[shard::shards]
