"""Shared `RunSummary` list sorting: one allow-list, one None-safe sort key.

Both `FixtureRepository.list_runs` and `RealRepository.list_runs` call
`sort_runs` instead of each keeping (and risking drifting from) their own
copy of which fields are sortable -- `real_repository.py`'s used to ignore
the requested field entirely and always sort by `run_id`.
"""

from __future__ import annotations

from agent_bisect.server.schemas_runs import RunSummary

SORTABLE_RUN_FIELDS = frozenset({"run_id", "n_steps", "cost_usd", "calls", "outcome", "domain"})
_NUMERIC_FIELDS = frozenset({"n_steps", "cost_usd", "calls"})


def _sort_value(run: RunSummary, field: str) -> str | float:
    """The field's value, comparable: numeric fields become `float` (a
    sentinel `-inf` for `None` -- real mode: `cost_usd`/`calls` can be
    unknown -- so a mixed `None`/numeric column never raises comparing
    `None` against a number mid-sort); the rest are already `str`."""
    value = getattr(run, field)
    if field in _NUMERIC_FIELDS:
        return float("-inf") if value is None else float(value)
    return str(value)


def sort_runs(runs: list[RunSummary], sort: str) -> list[RunSummary]:
    """Sorts `runs` by `sort` (a name from `SORTABLE_RUN_FIELDS`, optionally
    `-`-prefixed for descending). An unrecognized field falls back to
    `run_id` rather than erroring -- it only affects ordering, not
    correctness, so a typo'd `sort` query param shouldn't be a 422."""
    field = sort.lstrip("-")
    if field not in SORTABLE_RUN_FIELDS:
        field = "run_id"
    reverse = sort.startswith("-")
    return sorted(runs, key=lambda run: _sort_value(run, field), reverse=reverse)
