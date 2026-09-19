"""Rebuilding dataset items for candidates that were rejected, from the tape.

`docs/decisions/0021-p3-outcome.md` freezes a labelled secondary set of
candidates whose fault flipped the run twice in four rather than three or
four — a real but weaker causal effect. Their recordings already exist, so
the set costs nothing further to build.

What it does cost is reconstruction. Most of those candidates were judged
before the pipeline began keeping the item on a rejected record, so their
journal entries carry only the verdict: the base run, the planted step,
the fault type and the faulted pass rate. Everything else has to come back
off the tape, where it has been all along:

- the **faulted recordings** themselves, found by the run-id shape the
  collection gives them, and the first of those by seed order that failed;
- the **fault**, from that fork's own manifest — `0016` puts the standing
  `FaultInjector` in `params`, precisely so a fork can be explained
  without its journal;
- the **oracle**, from the base run's recorded result at the planted step;
- the **base pass rate**, from the stability record.

A reconstructed item is marked `reconstructed: true`. It carries the same
label (`planted_step`) and the same oracle as any other item — those are
read from the tape, not inferred — but its `mutation` is summarised from
the injector rather than from the original mutator's own account of what
it changed, and it says so rather than pretending otherwise.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from agent_bisect.adapters.tau2_fault_injector import FaultSpec, injector_spec_from
from agent_bisect.attribution.interventions import ReplaceToolResult
from agent_bisect.bench.journal import Journal
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, UnknownRunError

#: The verdict a candidate gets when its fault did not flip the run hard
#: enough for the pre-registered rule.
NOT_FLIPPED = "not_flipped"


def _fork_run_ids(runs_dir: Path, base_run_id: str, step_idx: int) -> list[str]:
    """Every faulted fork of this base run at this step, in run-id order.

    Matched by prefix rather than by reconstructing the fault type: a
    retried attempt carries an extra suffix, and the point is to find the
    recordings, not to re-derive their names.
    """
    index = runs_dir / "index.sqlite"
    if not index.exists():
        return []
    connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT run_id FROM runs WHERE run_id LIKE ? ORDER BY run_id",
            (f"{base_run_id}-k{step_idx}-%",),
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - an unreadable tape yields nothing
        return []
    finally:
        connection.close()
    return [str(row[0]) for row in rows]


def _first_failing(reader: TapeReader, run_ids: list[str]) -> str | None:
    """The first of these recordings that failed, by seed order."""
    for run_id in run_ids:
        outcome = reader.get_outcome(run_id)
        if outcome is not None and not outcome.passed:
            return run_id
    return None


def _fault_of(reader: TapeReader, run_id: str) -> FaultSpec | None:
    try:
        return injector_spec_from(reader.get_manifest(run_id).params)
    except UnknownRunError:  # pragma: no cover
        return None


def _oracle_ref(reader: TapeReader, base_run_id: str, step_idx: int) -> str | None:
    try:
        return reader.get_step(base_run_id, step_idx).tool_result_ref
    except Exception:  # noqa: BLE001 - a missing step means no item, not a crash
        return None


def _stability_rate(journal: Journal, base_run_id: str) -> float | None:
    record = journal.read("stability", base_run_id)
    return None if record is None else float(record.get("rate", 0.0))


def _mutated_payload(store: BlobStore, oracle_ref: str, fault: FaultSpec) -> dict[str, Any]:
    """What the agent was shown: the true result with the fault's answer."""
    payload = dict(store.get_json(oracle_ref))
    return {**payload, "content": fault.content, "error": fault.error}


def reconstruct(
    record: Mapping[str, Any],
    *,
    journal: Journal,
    reader: TapeReader,
    store: BlobStore,
    runs_dir: Path,
) -> dict[str, Any] | None:
    """One rejected candidate as a dataset item, or `None` if it cannot be."""
    base_run_id = record.get("base_run_id")
    step_idx = record.get("planted_step")
    if base_run_id is None or step_idx is None:
        return None
    run_id = _first_failing(reader, _fork_run_ids(runs_dir, str(base_run_id), int(step_idx)))
    if run_id is None:
        return None
    fault = _fault_of(reader, run_id)
    oracle_ref = _oracle_ref(reader, str(base_run_id), int(step_idx))
    base_rate = _stability_rate(journal, str(base_run_id))
    if fault is None or oracle_ref is None or base_rate is None:
        return None
    try:
        manifest = reader.get_manifest(str(base_run_id))
        mutated = _mutated_payload(store, oracle_ref, fault)
    except Exception:  # noqa: BLE001 - a blob we cannot read is an item we cannot make
        return None
    return {
        "item_id": f"{manifest.domain}-{manifest.task_id}-k{step_idx}-{fault.fault_type}",
        "domain": manifest.domain,
        "task_id": manifest.task_id,
        "base_run_id": str(base_run_id),
        "base_pass_rate": base_rate,
        "run_id": run_id,
        "faulted_pass_rate": float(record.get("faulted_pass_rate") or 0.0),
        "planted_step": int(step_idx),
        "position_bucket": record.get("position_bucket"),
        "fault_type": fault.fault_type,
        "mutation": {
            "fault_type": fault.fault_type,
            "path": [],
            "path_str": "<reconstructed>",
            "old": None,
            "new": fault.content,
            "detail": (
                "rebuilt from the fork's recorded FaultInjector; the original "
                "mutator's account of the path it changed was not kept for "
                "rejected candidates"
            ),
        },
        "oracle": {"tool_result_ref": oracle_ref, "step_idx": int(step_idx)},
        "intervention": ReplaceToolResult(step=int(step_idx), new_result=mutated).to_ref(),
        "seeds": [],
        "n_reruns": 4,
        "reconstructed": True,
    }


def extended_items(
    journal: Journal,
    *,
    reader: TapeReader,
    store: BlobStore,
    runs_dir: Path,
    threshold: float,
) -> Iterator[dict[str, Any]]:
    """Items for every rejected candidate at or under `threshold`.

    Kept candidates are not included: the caller already has those, and
    the extended manifest is the union.
    """
    for record in journal.all("candidate"):
        if record.get("status") == "kept" or record.get("reason_code") != NOT_FLIPPED:
            continue
        rate = record.get("faulted_pass_rate")
        if rate is None or float(rate) > threshold:
            continue
        item = reconstruct(
            record, journal=journal, reader=reader, store=store, runs_dir=runs_dir
        )
        if item is not None:
            yield item
