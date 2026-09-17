"""Point τ²'s NL-assertion judge at a model this account actually has.

τ² scores a task's natural-language assertions with a judge whose model
is a module constant, `tau2.config.DEFAULT_LLM_NL_ASSERTIONS =
"gpt-4.1-2025-04-14"`, and it runs that judge whenever `NL_ASSERTION` is
in the task's `reward_basis` — **regardless of whether the task lists any
assertions** (`evaluator/evaluator.py`: `task_needs_nl = RewardType.
NL_ASSERTION in task.evaluation_criteria.reward_basis`). That is 112 of
the 114 retail tasks.

On this study's endpoint that model does not exist, so every one of those
tasks dies with `404 page not found` — measured, 32 of them in the first
half hour of collection, all retail. Retail is not optional: the
pre-registered dataset is airline **and** retail.

So the constant is repointed, for the duration of a session, at the judge
model P0 chose (`docs/decisions/0004-p0-probe-protocol.md` §4.2, recorded
in `config/models.toml`). The call still goes through
`llm_utils.completion`, so it is limited, ledgered, recorded as an
`evaluator` step and replayed like any other — nothing about the seam
changes, only which model answers.

What this costs, and why it is recorded in
`docs/decisions/0018-retail-nl-judge.md`: those tasks now have an LLM in
their reward path, which is a call per run *and* per re-run and puts a
sampled quantity inside the stability check and the keep rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_bisect.core.models import DEFAULT_MODELS_PATH, load_chosen_models


@contextmanager
def judge_routed(model: str | None = None, *, path: Path = DEFAULT_MODELS_PATH) -> Iterator[str]:
    """Make τ²'s NL-assertion judge use `model` (default: the P0 choice).

    Patched on the evaluator module rather than on `tau2.config`, because
    the constant is imported by value at import time
    (`evaluator_nl_assertions.py` line 8) and re-binding the config would
    not reach it.
    """
    import tau2.evaluator.evaluator_nl_assertions as nl_assertions

    chosen = model or load_chosen_models(path).judge
    original = nl_assertions.DEFAULT_LLM_NL_ASSERTIONS
    nl_assertions.DEFAULT_LLM_NL_ASSERTIONS = chosen
    try:
        yield chosen
    finally:
        nl_assertions.DEFAULT_LLM_NL_ASSERTIONS = original
