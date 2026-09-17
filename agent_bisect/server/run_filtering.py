"""Shared `/api/runs` filtering: one function, used by both repositories.

Operates on `RunSearchRow` (a `RunSummary` plus the distinct tool names
actually called in that run) rather than `RunSummary` alone: free-text
search (`q`) reaches into tool names, which live on individual steps, not
the summary DTO -- so each repository builds one row per run (data it
already has in hand while assembling the summary) and hands the list here,
instead of duplicating the filter logic the way `list_runs` used to before
`fault_type`/`q` existed.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_bisect.server.repository import RunFilter
from agent_bisect.server.schemas_runs import RunSummary

FAULT_TYPE_FILTER_VALUES = frozenset(
    {"wrong_value", "missing_field", "stale_record", "tool_error", "none"}
)
Q_MAX_LENGTH = 100


@dataclass(frozen=True, slots=True)
class RunSearchRow:
    """One run's summary plus the tool names its steps actually called."""

    summary: RunSummary
    tool_names: tuple[str, ...]


def _matches_query(row: RunSearchRow, needle: str) -> bool:
    haystack = (row.summary.run_id, row.summary.task_id, row.summary.model, *row.tool_names)
    return any(needle in field.lower() for field in haystack)


def _matches_fault_type(row: RunSearchRow, fault_type: str) -> bool:
    if fault_type == "none":
        return row.summary.fault_type is None
    return row.summary.fault_type == fault_type


def filter_runs(rows: list[RunSearchRow], filters: RunFilter) -> list[RunSearchRow]:
    """Applies every `/api/runs` filter in one place: `domain`, `outcome`,
    `status`, `model` (exact match), `fault_type` (exact match, `"none"` =
    unplanted), and `q` (case-insensitive substring over run_id/task_id/
    model/tool names)."""
    if filters.domain:
        rows = [r for r in rows if r.summary.domain == filters.domain]
    if filters.outcome:
        rows = [r for r in rows if r.summary.outcome == filters.outcome]
    if filters.status:
        rows = [r for r in rows if r.summary.status == filters.status]
    if filters.model:
        rows = [r for r in rows if r.summary.model == filters.model]
    if filters.fault_type:
        rows = [r for r in rows if _matches_fault_type(r, filters.fault_type)]
    if filters.q:
        needle = filters.q.strip().lower()
        if needle:
            rows = [r for r in rows if _matches_query(r, needle)]
    return rows
