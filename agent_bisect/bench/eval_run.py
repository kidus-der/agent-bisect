"""Driving one evaluation: judge every item, run every method, persist, report.

The pieces below it are pure or testable on fakes; this is the wiring that
walks a frozen split and leaves behind everything a reader needs:

- one blame document per `(run, method)` under `runs/blame/`
  (`attribution/blame_store.py`), so the dashboard can show any diagnosis;
- one row per `(item, method)` in the outcomes table, so `make reproduce`
  can rebuild the report without re-running anything;
- the report itself (`bench/evaluate.build_report`).

**Every control arm is sanity-checked.** A control is "restore at the
step, change nothing, run the rest"; if it *passes*, it is not a control
for this failure but a different run, and every effect measured against it
is understated. `control_reproduces_failure` compares the control arm's
pass rate with the item's recorded faulted pass rate and flags the item
when the control passes more than `CONTROL_PASS_LIMIT` of the time.
Flagged items are **reported and still scored** — the primary metric
includes them — because dropping them would quietly evaluate the subset
whose controls happened to behave. This check is what
`docs/findings/p5-control-fork.md` says would have caught the one-shot
fault before any live spend, and `docs/decisions/0016-persistent-planted-fault.md`
is what makes it pass.

**An infrastructure failure is not a verdict.** An item whose forks time
out, or whose judge call 504s, has not answered wrongly — it has not been
asked. It is **re-queued** and retried, up to `max_passes` passes with
backoff, and every fork already on the tape is reused so a retry is cheap.
Only when the passes are exhausted does the item stay unevaluated, and
then the whole run is **incomplete**: `EvaluationRun.complete` is false,
the caller publishes nothing, and it says so. Writing an infra timeout
into the results as "blamed nothing" would report a network outage as a
property of the method, which is exactly what happened on the first live
dev run — six items timed out and the summary read 0.0 accuracy for every
method as if that were a finding.

A *judge* that answers unparseably, or a search that clears no step, is a
different thing: those are real answers and they score as wrong.

tau2 is reached only through injected callables (`task_text`,
`truth_for_item`), so `bench/` keeps knowing nothing about any domain and
the offline tests can drive the whole thing on scripted models.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
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
from agent_bisect.core.job_status import running, write_status
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader

#: A control arm that passes more often than this is not a control for the
#: recorded failure. Not a threshold anything is gated on: it decides only
#: whether an item is flagged in the report.
CONTROL_PASS_LIMIT = 0.5

#: The `kind` P5's progress is written under, for the dashboard's Live page.
STATUS_KIND = "eval"
STATUS_PHASE = "P5"

#: Items evaluated at once. The binding constraint is latency, not rate:
#: a user-simulator turn measures ~76 s, and a batch pool can never hold
#: more than `batch` (4) draws, so per-item concurrency alone leaves the
#: run at a few requests per minute against a ~68-90 rpm allowance.
#: Overlapping items is what actually fills the pipe. Every per-item
#: object (recorder, truth resolver, replay dispatcher) is already
#: per-thread or per-item; only the shared `EvaluationRun` needs a lock.
DEFAULT_ITEM_CONCURRENCY = 4

#: Passes over the item list. A transient 504 on pass 1 gets two more
#: chances, and everything already bought is reused from the tape.
DEFAULT_MAX_PASSES = 3
#: Seconds before re-queueing the items that failed on infrastructure.
RETRY_BACKOFF_S = 60.0

#: `(domain, task_id) -> (task description, domain policy)`.
TaskTextFor = Callable[[str, str], tuple[str, str]]
#: `item -> how to re-execute one of its tool steps truthfully`.
TruthForItem = Callable[[DatasetItem], TruthFor | None]


@dataclass(frozen=True, slots=True)
class ControlFlag:
    """An item whose control arm did not reproduce its recorded failure."""

    item_id: str
    run_id: str
    method: EvalMethod
    control_pass_rate: float
    faulted_pass_rate: float

    def describe(self) -> str:
        return (
            f"{self.item_id} ({self.method}): control passed "
            f"{self.control_pass_rate:.2f} of the time but the recorded run "
            f"failed at {self.faulted_pass_rate:.2f}; effects here are understated"
        )


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
    control_flags: list[ControlFlag] = field(default_factory=list)

    @property
    def n_failed_items(self) -> int:
        return len(self.failures)

    @property
    def n_control_flags(self) -> int:
        return len(self.control_flags)

    @property
    def complete(self) -> bool:
        """Whether every item got a real verdict. Nothing is published unless."""
        return not self.failures

    @property
    def bisect_unguarded_calls(self) -> int:
        """Responses the bisect arms served past the request-hash guard.

        Must be 0. `scripts/gates/p5.py` fails the gate otherwise, because
        a Bisect arm that drifted from its own recording is not Bisect.
        """
        return sum(
            0 if outcome.blame is None else outcome.blame.unguarded_calls
            for outcome in self.outcomes
            if outcome.method == "bisect"
        )

    def flag_rows(self) -> list[dict[str, Any]]:
        """The control flags, for the report's scope section."""
        return [
            {
                "item_id": flag.item_id,
                "run_id": flag.run_id,
                "method": flag.method,
                "control_pass_rate": flag.control_pass_rate,
                "faulted_pass_rate": flag.faulted_pass_rate,
                "detail": flag.describe(),
            }
            for flag in self.control_flags
        ]

    def failure_rows(self) -> list[dict[str, Any]]:
        """The items that could not be evaluated, for the same section."""
        return [
            {"item_id": f.item_id, "run_id": f.run_id, "reason": f.reason}
            for f in self.failures
        ]


def control_pass_rate(outcome: MethodOutcome) -> float | None:
    """The control arm's pass rate, or `None` when it bought no control."""
    blame = outcome.blame
    if blame is None or blame.estimate is None:
        return None
    arms = [
        effect.control
        for effect in blame.estimate.step_effects
        if effect.control is not None and effect.control.n > 0
    ]
    if not arms:
        return None
    # The shared control is one arm repeated across steps, so successes and
    # draws are summed rather than averaged -- that is the same number for
    # a shared arm and the right one for per-step arms.
    return sum(arm.successes for arm in arms) / sum(arm.n for arm in arms)


def check_controls(
    item: DatasetItem, outcomes: Sequence[MethodOutcome]
) -> list[ControlFlag]:
    """Flag any control arm that did not reproduce the recorded failure."""
    flags: list[ControlFlag] = []
    for outcome in outcomes:
        rate = control_pass_rate(outcome)
        if rate is not None and rate > CONTROL_PASS_LIMIT:
            flags.append(
                ControlFlag(
                    item_id=item.item_id,
                    run_id=item.run_id,
                    method=outcome.method,
                    control_pass_rate=rate,
                    faulted_pass_rate=item.faulted_pass_rate,
                )
            )
    return flags


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
    max_passes: int = DEFAULT_MAX_PASSES,
    item_concurrency: int = DEFAULT_ITEM_CONCURRENCY,
    sleep: Callable[[float], None] = time.sleep,
) -> EvaluationRun:
    """Judge and evaluate every item, retrying the ones infrastructure lost."""
    run = EvaluationRun()
    outstanding = list(items)
    for attempt in range(1, max_passes + 1):
        run.failures.clear()
        _evaluate_pass(
            outstanding, run, reader=reader, store=store,
            judge_backend=judge_backend, executor=executor, task_text=task_text,
            config=config, seed=seed, runs_dir=runs_dir, judge_config=judge_config,
            step_by_step=step_by_step, truth_for_item=truth_for_item,
            progress=progress, total=len(items), done=len(items) - len(outstanding),
            item_concurrency=item_concurrency,
        )
        if run.complete or attempt == max_passes:
            return run
        outstanding = [
            item for item in items
            if item.item_id in {failure.item_id for failure in run.failures}
        ]
        # Everything that succeeded stays; only the lost items come back,
        # and their finished forks are reused from the tape.
        run.outcomes = [
            outcome for outcome in run.outcomes
            if outcome.item_id not in {item.item_id for item in outstanding}
        ]
        run.control_flags = [
            flag for flag in run.control_flags
            if flag.item_id not in {item.item_id for item in outstanding}
        ]
        sleep(RETRY_BACKOFF_S)
    return run


def _evaluate_pass(
    items: Sequence[DatasetItem],
    run: EvaluationRun,
    *,
    reader: TapeReader,
    store: BlobStore,
    judge_backend: JudgeBackend,
    executor: ForkExecutor,
    task_text: TaskTextFor,
    config: BaselineConfig,
    seed: int,
    runs_dir: Path,
    judge_config: JudgeConfig,
    step_by_step: bool,
    truth_for_item: TruthForItem | None,
    progress: Callable[[DatasetItem, int, int], None] | None,
    total: int,
    done: int,
    item_concurrency: int = 1,
) -> None:
    """One pass over `items`, appending to `run`. Items may overlap."""
    guard = threading.Lock()
    finished = [0]
    attempted = [0]

    # Written before any item starts, so a stale file from a previous run
    # can never be mistaken for this one's progress.
    _report_progress(runs_dir, done, total, run, attempted=done, failed=0)

    def evaluate_one(item: DatasetItem) -> None:
        with guard:
            attempted[0] += 1
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
        except Exception as exc:  # noqa: BLE001 - re-queued, not scored
            # Deliberately broad: whatever stopped this item -- an
            # unreadable tape, a judge that raised, a fork that died on
            # infrastructure -- it has not answered, so it is recorded as
            # a failure and retried on the next pass rather than scored.
            reason = f"{type(exc).__name__}: {exc}"
            with guard:
                run.failures.append(
                    ItemFailure(item_id=item.item_id, run_id=item.run_id, reason=reason)
                )
                _report_progress(
                    runs_dir, done + finished[0], total, run,
                    attempted=done + attempted[0], failed=len(run.failures),
                )
            # Printed as it happens: the reasons used to surface only after
            # every pass had run, which made a stalled run unreadable.
            print(f"  unevaluated {item.item_id}: {reason}", flush=True)
            return

        for outcome in outcomes:
            if outcome.blame is not None:
                save_blame(runs_dir, outcome.blame, judgement.step_by_step)
        with guard:
            run.control_flags.extend(check_controls(item, outcomes))
            run.outcomes.extend(outcomes)
            finished[0] += 1
            _report_progress(
                runs_dir, done + finished[0], total, run,
                attempted=done + attempted[0], failed=len(run.failures),
            )
        if progress is not None:
            progress(item, done + finished[0], total)

    if item_concurrency <= 1 or len(items) <= 1:
        for item in items:
            evaluate_one(item)
        return
    with ThreadPoolExecutor(
        max_workers=min(item_concurrency, len(items)), thread_name_prefix="p5-item"
    ) as pool:
        list(pool.map(evaluate_one, items))


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


def _report_progress(
    runs_dir: Path,
    done: int,
    total: int,
    run: EvaluationRun,
    *,
    attempted: int = 0,
    failed: int = 0,
) -> None:
    """Write P5's progress where the dashboard's Live page reads it.

    `items_done` counts items that **completed with a verdict**, and
    nothing else. It used to be written at the start of each item, so a
    run in which every item died still reported 6/6 and the status file
    said "healthy" while nothing had been evaluated. `items_attempted` and
    `items_failed_infra` are carried beside it so the three numbers cannot
    agree with each other and still be wrong.

    Best effort: a status file that cannot be written must not stop an
    evaluation that is otherwise fine, and the run's own outputs are the
    record that matters.
    """
    try:
        write_status(
            runs_dir,
            running(
                kind=STATUS_KIND,
                phase=STATUS_PHASE,
                items_done=done,
                items_total=total,
                items_attempted=attempted,
                items_failed_infra=failed,
                calls_spent=sum(
                    outcome.total_calls for outcome in run.outcomes
                ),
            ),
            phase=STATUS_PHASE,
        )
    except Exception:  # noqa: BLE001 - progress reporting is never load-bearing
        return
