"""What a set of recorded runs looks like, for planning the next phase.

P3 plants one fault on one tool-result step of a successful run, "stratified
early / middle / late" (`docs/brief/summary.md` §3, "Dataset construction").
Whether that is affordable depends on numbers only the recordings can give:
how many runs passed, how long they are, what they cost, and how many
tool-result steps each one actually offers to break.

Everything here reads the tape; nothing re-runs anything. `core/` stays
free of tau2 — a step's actor and tool name are on the row, and whether a
recorded result was an error is in its blob.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader

Bucket = Literal["early", "middle", "late"]
_BUCKETS = 3


def bucket_of(position: int, total: int) -> Bucket:
    """Which third of a run of `total` steps `position` falls in.

    Thirds by position, not by step index, so a short run still has an
    early and a late end rather than collapsing into one bucket.
    """
    if total <= 0 or not 0 <= position < total:
        raise ValueError(f"position {position} is outside a run of {total} steps")
    third = position * _BUCKETS // total
    return ("early", "middle", "late")[min(third, _BUCKETS - 1)]


class InjectionSite(BaseModel):
    """One tool-result step a fault could be planted on."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    step_idx: int
    tool_name: str
    bucket: Bucket
    #: The recorded result was already an error, so breaking it further
    #: says little. Counted, but kept out of `clean`.
    errored: bool


class InjectionBuckets(BaseModel):
    """How many sites a set of runs offers, and where in the runs they are."""

    model_config = ConfigDict(frozen=True)

    total: int = 0
    early: int = 0
    middle: int = 0
    late: int = 0
    #: Sites whose recorded result was not already an error.
    clean: int = 0

    @classmethod
    def of(cls, sites: list[InjectionSite]) -> InjectionBuckets:
        return cls(
            total=len(sites),
            early=sum(1 for site in sites if site.bucket == "early"),
            middle=sum(1 for site in sites if site.bucket == "middle"),
            late=sum(1 for site in sites if site.bucket == "late"),
            clean=sum(1 for site in sites if not site.errored),
        )


class RunStats(BaseModel):
    """A set of recorded runs, summarised."""

    model_config = ConfigDict(frozen=True)

    runs: int = 0
    passed: int = 0
    failed: int = 0
    mean_steps: float = 0.0
    mean_llm_calls: float = 0.0
    mean_agent_calls: float = 0.0
    mean_user_calls: float = 0.0
    mean_evaluator_calls: float = 0.0
    mean_tool_steps: float = 0.0
    #: Span from a run's first reserved call to its last, in seconds. It
    #: excludes environment construction and reward computation, and under
    #: a concurrent batch it includes time the run spent waiting on the
    #: rate limiter -- which is real elapsed time for that run.
    mean_call_span_s: float = 0.0
    injection_sites: InjectionBuckets = InjectionBuckets()
    #: Mean injection sites per run, for reading the budget off directly.
    mean_injection_sites: float = 0.0


def recorded_run_ids(root: Path, reader: TapeReader) -> list[str]:
    """Every recording on the tape: no forks, and an outcome to report."""
    index = root / "index.sqlite"
    if not index.exists():
        return []
    connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        run_ids = sorted(row[0] for row in connection.execute("SELECT run_id FROM runs"))
    finally:
        connection.close()
    return [
        run_id
        for run_id in run_ids
        if reader.get_manifest(run_id).parent_run_id is None
        and reader.get_outcome(run_id) is not None
    ]


def injection_sites(reader: TapeReader, blobs: BlobStore, run_id: str) -> list[InjectionSite]:
    """The tool-result steps of `run_id` a fault could be planted on."""
    steps = reader.get_steps(run_id)
    total = len(steps)
    sites = []
    for step in steps:
        if step.actor != "tool" or step.tool_result_ref is None:
            continue
        result = blobs.get_json(step.tool_result_ref)
        sites.append(
            InjectionSite(
                run_id=run_id,
                step_idx=step.step_idx,
                tool_name=step.tool_name or "?",
                bucket=bucket_of(step.step_idx, total),
                errored=bool(result.get("error")),
            )
        )
    return sites


def _call_spans(root: Path, run_ids: list[str]) -> dict[str, float]:
    """First-to-last reserved call, per run, from the ledger."""
    ledger = root / "ledger.sqlite"
    if not ledger.exists():
        return {}
    connection = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT run_id, MIN(ts), MAX(ts) FROM calls "
            "WHERE run_id IS NOT NULL GROUP BY run_id"
        ).fetchall()
    except sqlite3.OperationalError:
        # A ledger written before run attribution existed has no column.
        return {}
    finally:
        connection.close()
    wanted = set(run_ids)
    return {run_id: last - first for run_id, first, last in rows if run_id in wanted}


def _mean(values: list[float] | list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarise_runs(reader: TapeReader, blobs: BlobStore, root: Path) -> RunStats:
    """Summarise every recorded run under `root`."""
    run_ids = recorded_run_ids(root, reader)
    if not run_ids:
        return RunStats()

    steps_per_run: list[int] = []
    tools_per_run: list[int] = []
    by_actor: dict[str, list[int]] = {"agent": [], "user": [], "evaluator": []}
    sites: list[InjectionSite] = []
    passed = 0
    for run_id in run_ids:
        steps = reader.get_steps(run_id)
        steps_per_run.append(len(steps))
        tools_per_run.append(sum(1 for step in steps if step.actor == "tool"))
        for actor in by_actor:
            by_actor[actor].append(sum(1 for step in steps if step.actor == actor))
        sites.extend(injection_sites(reader, blobs, run_id))
        outcome = reader.get_outcome(run_id)
        passed += 1 if outcome is not None and outcome.passed else 0

    spans = _call_spans(root, run_ids)
    means = {actor: _mean(counts) for actor, counts in by_actor.items()}
    return RunStats(
        runs=len(run_ids),
        passed=passed,
        failed=len(run_ids) - passed,
        mean_steps=_mean(steps_per_run),
        mean_llm_calls=sum(means.values()),
        mean_agent_calls=means["agent"],
        mean_user_calls=means["user"],
        mean_evaluator_calls=means["evaluator"],
        mean_tool_steps=_mean(tools_per_run),
        mean_call_span_s=_mean(list(spans.values())),
        injection_sites=InjectionBuckets.of(sites),
        mean_injection_sites=len(sites) / len(run_ids),
    )
