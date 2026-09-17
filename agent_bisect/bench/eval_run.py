"""Driving one evaluation: judge every item, run every method, persist, report.

The pieces below it are pure or testable on fakes; this is the wiring that
walks a frozen split and leaves behind everything a reader needs:

- one blame document per `(run, method)` under `runs/blame/`
  (`attribution/blame_store.py`), so the dashboard can show any diagnosis;
- one row per `(item, method)` in the outcomes table, so `make reproduce`
  can rebuild the report without re-running anything;
- the report itself (`bench/evaluate.build_report`).

**An item that cannot be evaluated is recorded, not skipped.** If the tape
is unreadable, the judge raises, or every fork of it dies on
infrastructure, the item still produces one `MethodOutcome` per method with
`predicted_step=None` and the reason in `note` — a wrong answer with an
explanation. Dropping it would quietly evaluate the subset that happened to
work, which is the failure mode `docs/decisions/0001-preregistration.md`
forbids ("data is never dropped").

tau2 is reached only through injected callables (`task_text`,
`truth_for_item`), so `bench/` keeps knowing nothing about any domain and
the offline tests can drive the whole thing on scripted models.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_bisect.attribution.blame_store import save_blame
from agent_bisect.attribution.judge import DEFAULT_CONFIG as DEFAULT_JUDGE_CONFIG
from agent_bisect.attribution.judge import JudgeBackend, JudgeConfig
from agent_bisect.attribution.search import ForkExecutor, TruthFor
from agent_bisect.attribution.trajectory import build_judge_input
from agent_bisect.bench.baselines import (
    BaselineConfig,
    EvalMethod,
    MethodOutcome,
    evaluate_item,
    judge_item,
)
from agent_bisect.bench.manifest import DatasetItem
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader

#: `(domain, task_id) -> (task description, domain policy)`.
TaskTextFor = Callable[[str, str], tuple[str, str]]
#: `item -> how to re-execute one of its tool steps truthfully`.
TruthForItem = Callable[[DatasetItem], TruthFor | None]


@dataclass(frozen=True, slots=True)
class ItemFailure:
    """An item that could not be evaluated, and why. Reported, never dropped."""

    item_id: str
    run_id: str
    reason: str


@dataclass(slots=True)
class EvaluationRun:
    """Everything one pass over a split produced."""

    outcomes: list[MethodOutcome] = field(default_factory=list)
    failures: list[ItemFailure] = field(default_factory=list)

    @property
    def n_failed_items(self) -> int:
        return len(self.failures)


def _unevaluated(
    item: DatasetItem, methods: Sequence[EvalMethod], reason: str
) -> list[MethodOutcome]:
    """One wrong answer per method, carrying the reason it could not be tried."""
    return [
        MethodOutcome(
            item_id=item.item_id,
            run_id=item.run_id,
            method=method,
            predicted_step=None,
            ranking=(),
            shortlist=(),
            judge_calls=0,
            replay_calls=0,
            reruns=0,
            control_reruns=0,
            parse_failed=False,
            note=f"not evaluated: {reason}",
        )
        for method in methods
    ]


def evaluate_dataset(
    items: Sequence[DatasetItem],
    *,
    reader: TapeReader,
    store: BlobStore,
    judge_backend: JudgeBackend,
    executor: ForkExecutor,
    task_text: TaskTextFor,
    config: BaselineConfig,
    seed: int,
    runs_dir: Path,
    judge_config: JudgeConfig = DEFAULT_JUDGE_CONFIG,
    step_by_step: bool = True,
    truth_for_item: TruthForItem | None = None,
    progress: Callable[[DatasetItem, int, int], None] | None = None,
) -> EvaluationRun:
    """Judge and evaluate every item of `items`, persisting as it goes."""
    run = EvaluationRun()
    total = len(items)
    for index, item in enumerate(items, start=1):
        if progress is not None:
            progress(item, index, total)
        try:
            description, policy = task_text(item.domain, item.task_id)
            judge_input = build_judge_input(
                item.run_id,
                reader=reader,
                store=store,
                item_id=item.item_id,
                task_description=description,
                policy=policy,
            )
            judgement = judge_item(
                judge_input, judge_backend, judge_config, step_by_step=step_by_step
            )
            outcomes = evaluate_item(
                item_id=item.item_id,
                run_id=item.run_id,
                steps=reader.get_steps(item.run_id),
                judgement=judgement,
                executor=executor,
                config=config,
                seed=seed,
                truth_for=None if truth_for_item is None else truth_for_item(item),
            )
        except Exception as exc:  # noqa: BLE001 - recorded as a wrong answer below
            # Deliberately broad: whatever stopped this item -- an
            # unreadable tape, a judge that raised, a fork that died on
            # infrastructure -- the item is still part of the split and
            # must be scored, with the reason attached.
            run.failures.append(
                ItemFailure(
                    item_id=item.item_id,
                    run_id=item.run_id,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )
            run.outcomes.extend(
                _unevaluated(item, config.methods, f"{type(exc).__name__}: {exc}")
            )
            continue

        for outcome in outcomes:
            if outcome.blame is not None:
                save_blame(runs_dir, outcome.blame, judgement.step_by_step)
        run.outcomes.extend(outcomes)
    return run


def outcome_rows(outcomes: Sequence[MethodOutcome]) -> list[dict[str, Any]]:
    """The tidy per-(item, method) table, for Parquet and for `make reproduce`."""
    return [
        {
            "item_id": outcome.item_id,
            "run_id": outcome.run_id,
            "method": outcome.method,
            "predicted_step": outcome.predicted_step,
            "ranking": list(outcome.ranking),
            "shortlist": list(outcome.shortlist),
            "judge_calls": outcome.judge_calls,
            "replay_calls": outcome.replay_calls,
            "total_calls": outcome.total_calls,
            "reruns": outcome.reruns,
            "control_reruns": outcome.control_reruns,
            "parse_failed": outcome.parse_failed,
            "note": outcome.note,
        }
        for outcome in outcomes
    ]


def outcomes_from_rows(rows: Sequence[dict[str, Any]]) -> list[MethodOutcome]:
    """The inverse of `outcome_rows`, so a stored table replays exactly."""
    return [
        MethodOutcome(
            item_id=str(row["item_id"]),
            run_id=str(row["run_id"]),
            method=row["method"],
            predicted_step=(
                None if row["predicted_step"] is None else int(row["predicted_step"])
            ),
            ranking=tuple(int(step) for step in row["ranking"]),
            shortlist=tuple(int(step) for step in row["shortlist"]),
            judge_calls=int(row["judge_calls"]),
            replay_calls=int(row["replay_calls"]),
            reruns=int(row["reruns"]),
            control_reruns=int(row["control_reruns"]),
            parse_failed=bool(row["parse_failed"]),
            note=str(row["note"]),
        )
        for row in rows
    ]
