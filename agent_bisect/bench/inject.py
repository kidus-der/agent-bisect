"""Breaking successful runs on purpose: the P3 collection pipeline.

The funnel is `docs/brief/summary.md` §3 "Dataset construction", and every
number in it is pre-registered in
`docs/decisions/0001-preregistration.md`:

1. record a run of a tau2 task; keep it only if `reward == 1.0`;
2. **stability** — re-run it 4 times and keep it only if the pass rate is
   `>= 0.75`. Without this a fault would get the credit for a run that
   was going to fail anyway;
3. pick a **tool-result step** k, stratified early / middle / late, and
   one of the **four fault types**, balanced across the dataset;
4. fork at k with `ReplaceToolResult(k, mutated)` and run the rest
   **N = 4** with fixed seeds;
5. **keep** it iff the faulted pass rate is `<= 0.25`. The item is the
   first failing faulted re-run by seed order — a complete failed
   recording with its own `run_id` — and the label is `k`, with the
   oracle fix being the original tool result.

Caps stop one easy task from becoming the dataset: at most three kept
faults per base run and at most one per position bucket.

Everything is checkpointed through `bench.journal.Journal`, so a
collection that dies resumes where it stopped, and **every** candidate is
logged with its verdict — the dataset card's funnel is the whole point,
and a rejected candidate that left no trace is a number nobody can
explain. Infrastructure failures are retried and never scored; a spent
budget or a rejected key stops the collection cleanly rather than
half-writing anything.

The tau2 wiring lives behind the `InjectRunner` protocol
(`adapters/tau2_inject.py`), so this module is domain-free and testable
without a model.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from agent_bisect.attribution.interventions import ReplaceToolResult
from agent_bisect.bench.faults import (
    FAULT_TYPES,
    FaultContext,
    FaultType,
    NoFaultPossibleError,
    plant,
)
from agent_bisect.bench.journal import Journal
from agent_bisect.bench.strata import (
    FaultBalancer,
    PositionBucket,
    attempt_order,
    bucketed,
)
from agent_bisect.core.budget import BudgetExceededError
from agent_bisect.core.job_status import done, failed, running, write_status
from agent_bisect.core.llm import AuthenticationError, TransportError
from agent_bisect.core.store import sha256_hex

#: How many times one faulted re-run may be retried through infrastructure
#: failures before the candidate is abandoned as unmeasurable.
MAX_INFRA_RETRIES = 3
#: How many times a task that died on infrastructure goes back on the
#: queue before it is parked and reported. An infra failure decides
#: nothing (`docs/decisions/0004-p0-probe-protocol.md` §3), so it must
#: not be able to remove a task from the collection by happening.
MAX_TASK_PASSES = 3
#: Seconds to wait before a re-queued pass, so a provider having a bad
#: minute is not hit again inside it.
PASS_BACKOFF_SECONDS = 60.0
#: The phase this pipeline reports itself under, in the ledger and the
#: dashboard's `runs/<phase>/status.json`.
PHASE = "P3"
_SEED_MODULUS = 2**31

#: Every counter the funnel reports, always present so the dataset card
#: can print a zero rather than omit a stage that never fired.
FUNNEL_COUNTS = (
    "base_recorded",
    "rejected_base_failed",
    "stable",
    "rejected_unstable",
    "candidates",
    "kept",
    "rejected_not_flipped",
    "rejected_unplantable",
    "rejected_repeated_call",
    "rejected_infra",
    "infra_retries",
    "requeued",
    "parked",
)


@dataclass(frozen=True)
class InjectConfig:
    """Every number the pipeline uses. All pre-registered except the seed."""

    n_reruns: int = 4
    stability_reruns: int = 4
    stable_at_or_above: float = 0.75
    keep_at_or_below: float = 0.25
    attempts_per_bucket: int = 2
    max_kept_per_run: int = 3
    seed: int = 20260917
    target_items: int = 120
    #: Keep going past the wall-clock budget until at least this many are
    #: kept (`docs/decisions/0012-p3-floor.md`, `0017`).
    floor_items: int = 60
    #: How many base recordings of a task to try before giving up on it.
    #: A task is the split unit, so a second trajectory of the same task
    #: is a legitimate second chance rather than a second sample of the
    #: same thing (`docs/decisions/0017-p3-collection-policy.md` §9).
    base_trials: int = 2
    #: Wall-clock budget for the whole collection. `None` means no limit.
    max_seconds: float | None = None
    #: Seconds to wait before re-queueing tasks that died on infrastructure.
    pass_backoff_seconds: float = PASS_BACKOFF_SECONDS
    trial: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_reruns": self.n_reruns,
            "stability_reruns": self.stability_reruns,
            "stable_at_or_above": self.stable_at_or_above,
            "keep_at_or_below": self.keep_at_or_below,
            "attempts_per_bucket": self.attempts_per_bucket,
            "base_trials": self.base_trials,
            "max_kept_per_run": self.max_kept_per_run,
            "seed": self.seed,
            "target_items": self.target_items,
            "floor_items": self.floor_items,
            "max_seconds": self.max_seconds,
        }


@dataclass(frozen=True)
class BaseRun:
    """A recorded candidate success."""

    run_id: str
    domain: str
    task_id: str
    passed: bool
    steps: int


@dataclass(frozen=True)
class RerunResult:
    """One re-run: its own recording, and whether it passed.

    `intervention_ref` is the blob hash of what was applied to it, so a
    forked run can be traced back to the change that produced it.
    """

    run_id: str
    passed: bool
    intervention_ref: str | None = None


@dataclass(frozen=True)
class ToolStep:
    """A tool-result step of a recorded run: a candidate fault site."""

    step_idx: int
    tool_name: str
    tool_args: Mapping[str, Any]
    #: The recorded tau2 `ToolMessage` payload — what gets mutated.
    result: Mapping[str, Any]
    #: Its blob hash: the oracle fix is "serve this again".
    result_ref: str
    #: The conversation after this step, for the salience heuristics.
    downstream: str = ""
    #: Just the arguments of later calls that CHANGE the world. A value
    #: that reaches one of those is a value the run acted on; a value that
    #: only ever appeared in a read is one a perception fault cannot turn
    #: into a wrong outcome (`0017` section 7).
    downstream_writes: str = ""

    @property
    def flows_into_a_write(self) -> bool:
        """Does anything this step returned reach a later write's arguments?"""
        return flows_into(self.result, self.downstream_writes)


class InjectRunner(Protocol):
    """What the pipeline needs from a domain. tau2's lives in adapters."""

    def record_base(self, domain: str, task_id: str, trial: int) -> BaseRun: ...

    def fresh_run(self, domain: str, task_id: str, *, attempt: int) -> RerunResult: ...

    def tool_steps(self, base_run_id: str) -> list[ToolStep]: ...

    def fault_fork(
        self,
        base_run_id: str,
        *,
        run_id: str,
        step_idx: int,
        tool_name: str,
        tool_args: Mapping[str, Any],
        faulted_result: Mapping[str, Any],
        fault_type: str,
        seed: int,
    ) -> RerunResult: ...


@dataclass(frozen=True)
class CollectionResult:
    """What one pass of the pipeline produced."""

    items: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    stopped_reason: str = "tasks exhausted"


class _Stop(Exception):
    """A clean stop: the budget, or the key. Never a half-written record."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


#: Values shorter than this match too much text to count as "used later".
MIN_FLOW_CHARS = 3


def flows_into(result: Mapping[str, Any], downstream_writes: str) -> bool:
    """True when a scalar in `result` re-appears in a later write's arguments."""
    if not downstream_writes:
        return False
    from agent_bisect.bench.salience import scalar_candidates

    body, _is_json = _parsed(result)
    return any(
        len(str(candidate.value)) >= MIN_FLOW_CHARS
        and str(candidate.value) in downstream_writes
        for candidate in scalar_candidates(body)
        if not isinstance(candidate.value, bool)
    )


def _parsed(result: Mapping[str, Any]) -> tuple[Any, bool]:
    from agent_bisect.bench.faults import parse_content

    return parse_content(str(result.get("content") or ""))


def derive_seed(base: int, *parts: str) -> int:
    """A stable seed for one sub-decision of a seeded collection."""
    digest = sha256_hex(f"{base}:{':'.join(parts)}".encode())
    return int(digest[:8], 16) % _SEED_MODULUS


def collect(
    runner: InjectRunner,
    *,
    tasks: Sequence[tuple[str, str]],
    journal: Journal,
    config: InjectConfig | None = None,
    on_progress: Callable[[str], None] | None = None,
    runs_dir: Path | None = None,
    calls_spent: Callable[[], int] | None = None,
    concurrency: int = 1,
    threads_hint: Callable[[], int] | None = None,
    extras: Callable[[], dict[str, Any]] | None = None,
) -> CollectionResult:
    """Run the funnel over `tasks`, resuming from whatever is on disk.

    With `runs_dir`, progress is published to `runs/p3/status.json` at
    every checkpoint, which is what the dashboard's Live page reads
    (`core.job_status`).

    `concurrency` runs that many tasks at once. A task is one simulation
    at a time, so it is also roughly how many model calls are in flight —
    the collection is latency-bound long before the limiter binds, and
    the limiter, the ledger and the retry policy are unchanged and still
    process-wide.
    """
    collector = _Collector(
        runner, journal, config or InjectConfig(), on_progress, runs_dir, calls_spent,
        threads_hint, extras,
    )
    return collector.run(tasks, concurrency=concurrency)


class _Collector:
    """One pass of the pipeline. Split out so each stage stays short."""

    def __init__(
        self,
        runner: InjectRunner,
        journal: Journal,
        config: InjectConfig,
        on_progress: Callable[[str], None] | None,
        runs_dir: Path | None = None,
        calls_spent: Callable[[], int] | None = None,
        threads_hint: Callable[[], int] | None = None,
        extras: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._runner = runner
        self._journal = journal
        self._config = config
        self._say = on_progress or (lambda _message: None)
        self._runs_dir = runs_dir
        self._calls_spent = calls_spent
        self._threads_hint = threads_hint
        self._extras = extras
        self._started_at: str | None = None
        self._began = time.monotonic()
        #: Everything below is touched by several task threads at once.
        #: The work itself needs no lock — each task owns its own runs —
        #: but the tallies, the balance and the append-only log do.
        self._lock = threading.Lock()
        #: Tasks that died on infrastructure this pass, to be re-queued.
        self._failed_tasks: list[tuple[str, str]] = []
        self._parked: list[tuple[str, str]] = []
        self._gate = _Gate()
        #: Kept items across *every* shard, read from the shared journal.
        #: A sharded collection stops when the dataset is big enough, not
        #: when one worker's own share is.
        self._kept_total = _kept_count(journal)
        self._counts: dict[str, int] = dict.fromkeys(FUNNEL_COUNTS, 0)
        self._items: list[dict[str, Any]] = []
        self._balancer = FaultBalancer(_kept_by_fault_type(journal))
        self._repeated: set[int] = set()

    # -- the loop ----------------------------------------------------------

    def run(
        self, tasks: Sequence[tuple[str, str]], *, concurrency: int = 1
    ) -> CollectionResult:
        reason = "tasks exhausted"
        self._publish()
        try:
            reason = self._run_passes(tasks, concurrency) or reason
        except _Stop as stop_signal:
            reason = stop_signal.reason
        final = self._final_reason(reason)
        self._publish(final=final)
        return CollectionResult(
            items=self._items[: self._config.target_items],
            counts=dict(self._counts),
            stopped_reason=final,
        )

    def _should_stop(self) -> str | None:
        """The stop rule of `docs/decisions/0017-p3-collection-policy.md`.

        The wall-clock budget does not cut the collection below the floor
        the gate is evaluated against: past the deadline it keeps going
        until there are enough items to have a dataset at all.
        """
        if self._kept_total >= self._config.target_items:
            return "target reached"
        budget = self._config.max_seconds
        if budget is None or time.monotonic() - self._began < budget:
            return None
        if self._kept_total >= self._config.floor_items:
            return "time budget reached"
        return None

    # -- telling the dashboard where we are ---------------------------------

    STOPPED_CLEANLY = frozenset(
        {"tasks exhausted", "target reached", "time budget reached"}
    )

    def _final_reason(self, reason: str) -> str:
        """A collection that parked work short of its target is not done.

        Saying `done` there would tell the dashboard, and anyone reading
        it, that the dataset is as large as it is going to get — when in
        fact tasks are waiting for a provider that was failing.
        """
        if self._parked and self._kept_total < self._config.target_items:
            return (
                f"{len(self._parked)} tasks parked after {MAX_TASK_PASSES} infrastructure "
                f"passes; {self._kept_total} of {self._config.target_items} items kept"
            )
        return reason

    def _publish(self, final: str | None = None) -> None:
        """Write `runs/p3/status.json`, atomically. Never fails the run."""
        if self._runs_dir is None:
            return
        shared: dict[str, Any] = {
            "kind": "inject",
            "phase": PHASE,
            "label": "planted-fault collection",
            "items_done": self._kept_total,
            "items_total": self._config.target_items,
            "calls_spent": self._calls_spent() if self._calls_spent else None,
        }
        if self._extras is not None:
            # Reporting must never kill a collection.
            with contextlib.suppress(Exception):
                shared.update(self._extras())
        if final is None:
            status = running(**shared, started_at=self._started_at)
            self._started_at = status["started_at"]
        elif final in self.STOPPED_CLEANLY:
            status = done(**shared, started_at=self._started_at)
        else:
            status = failed(**shared, error=final, started_at=self._started_at)
        try:
            write_status(self._runs_dir, status)
        except OSError as exc:  # pragma: no cover - a full disk is not a collection failure
            self._say(f"could not write the status file: {exc}")

    def _run_passes(self, tasks: Sequence[tuple[str, str]], concurrency: int) -> str | None:
        """Work the queue, putting infrastructure failures back on it.

        An infra failure decides nothing, so it must not be able to
        remove a task from the collection simply by happening. Tasks that
        died on infrastructure are re-queued for a later pass, with a
        backoff between passes; after `MAX_TASK_PASSES` they are parked
        and reported rather than silently dropped.
        """
        outstanding = list(tasks)
        self._gate.resize(max(1, concurrency))
        for attempt in range(1, MAX_TASK_PASSES + 1):
            if attempt > 1:
                self._say(f"pass {attempt}: re-queueing {len(outstanding)} infra failures")
                self._bump("requeued", len(outstanding))
                time.sleep(self._config.pass_backoff_seconds)
            with self._lock:
                self._failed_tasks = []
            stop = (
                self._run_serial(outstanding)
                if concurrency <= 1
                else self._run_parallel(outstanding, concurrency)
            )
            if stop is not None:
                return stop
            with self._lock:
                outstanding = list(self._failed_tasks)
            if not outstanding:
                return None
        with self._lock:
            self._parked = list(outstanding)
        self._bump("parked", len(self._parked))
        self._say(f"parked {len(self._parked)} tasks after {MAX_TASK_PASSES} infra passes")
        return None

    def _run_serial(self, tasks: Sequence[tuple[str, str]]) -> str | None:
        for domain, task_id in tasks:
            stop = self._should_stop()
            if stop is not None:
                return stop
            self._finish_task(domain, task_id)
        return self._should_stop()

    def _run_parallel(self, tasks: Sequence[tuple[str, str]], workers: int) -> str | None:
        """`workers` tasks at once. The stop rule is checked per task, so a
        collection that reaches its target finishes what is in flight and
        starts nothing new rather than abandoning half-measured candidates."""
        stopped: list[str] = []

        def one(task: tuple[str, str]) -> None:
            if stopped:
                return
            stop = self._should_stop()
            if stop is not None:
                stopped.append(stop)
                return
            self._finish_task(*task)

        def gated(task: tuple[str, str]) -> None:
            with self._gate:
                one(task)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="inject") as pool:
            list(pool.map(gated, tasks))
        return stopped[0] if stopped else self._should_stop()

    def _finish_task(self, domain: str, task_id: str) -> None:
        self._one_task(domain, task_id)
        self._gate.on_success()
        self._retune()
        with self._lock:
            self._kept_total = _kept_count(self._journal)
        self._publish()

    def _retune(self) -> None:
        """Follow the rate controller's view of how much should be in flight.

        Too few and latency decides the rate, which is the state P0 and P1
        ran in; too many and the provider starts refusing. The controller
        measures both, so the gate follows it rather than a constant.
        """
        if self._threads_hint is None:
            return
        # Pacing must never kill a collection.
        with contextlib.suppress(Exception):
            self._gate.resize(self._threads_hint())

    def _one_task(self, domain: str, task_id: str) -> None:
        """One task through the funnel. Infra failures cost the task, not the run."""
        try:
            for trial in range(self._config.base_trials):
                base = self._base_run(domain, task_id, trial)
                if base is None or not self._is_stable(base):
                    continue
                self._candidates_for(base)
                return
        except _Infra as failure:
            self._bump("rejected_infra")
            with self._lock:
                self._failed_tasks.append((domain, task_id))
            self._journal.log({"kind": "task", "key": f"{domain}-{task_id}",
                               "status": "rejected", "reason_code": "infra",
                               "reason": str(failure)})

    # -- stage 1: the base recording ---------------------------------------

    def _base_run(self, domain: str, task_id: str, trial: int = 0) -> BaseRun | None:
        key = f"{domain}-{task_id}-t{self._config.trial + trial}"
        record = self._journal.read("base", key)
        if record is None:
            record = self._record_base(domain, task_id, key, trial)
        self._bump("base_recorded")
        if not record.get("passed"):
            self._bump("rejected_base_failed")
            self._journal.log({"kind": "base", "key": key, "status": "rejected",
                               "reason": "base run did not pass"})
            return None
        return BaseRun(
            run_id=record["run_id"], domain=domain, task_id=task_id,
            passed=True, steps=int(record.get("steps", 0)),
        )

    def _record_base(
        self, domain: str, task_id: str, key: str, trial: int = 0
    ) -> dict[str, Any]:
        base = self._guarded(
            lambda: self._runner.record_base(domain, task_id, self._config.trial + trial)
        )
        record = {"run_id": base.run_id, "domain": domain, "task_id": task_id,
                  "passed": base.passed, "steps": base.steps}
        self._journal.write("base", key, record)
        self._say(f"recorded {base.run_id}: {'pass' if base.passed else 'fail'}")
        return record

    # -- stage 2: stability -------------------------------------------------

    def _is_stable(self, base: BaseRun) -> bool:
        record = self._journal.read("stability", base.run_id)
        if record is None:
            record = self._measure_stability(base)
        if not record["stable"]:
            self._bump("rejected_unstable")
            self._journal.log({"kind": "stability", "key": base.run_id, "status": "rejected",
                               "reason": f"re-run pass rate {record['rate']} below "
                                         f"{self._config.stable_at_or_above}"})
            return False
        self._bump("stable")
        return True

    def _measure_stability(self, base: BaseRun) -> dict[str, Any]:
        """Four fresh recordings of the same task.

        Originally these were forks at step 0 with `Resample`, so that
        stability was measured on the same code path the effect estimate
        uses. That turned out to be both unnecessary and broken: a fork
        at step 0 replays nothing, so it *is* a fresh run with an extra
        request-hash check over the resampled first turn — and that check
        can only produce false alarms, because the whole point of
        resampling is that the turn differs. Live, it failed 68 times and
        left one base run in thirty looking stable
        (`docs/decisions/0017-p3-collection-policy.md` §7).

        A fresh recording is simpler, costs exactly the same, and each
        re-run is a first-class recording on the tape rather than a fork
        of one.
        """
        results = []
        for index in range(self._config.stability_reruns):
            results.append(self._guarded(
                lambda i=index: self._runner.fresh_run(
                    base.domain, base.task_id, attempt=i
                )
            ))
        passes = sum(1 for result in results if result.passed)
        rate = passes / len(results) if results else 0.0
        record = {
            "base_run_id": base.run_id,
            "run_ids": [result.run_id for result in results],
            "passes": passes,
            "rate": rate,
            "stable": rate >= self._config.stable_at_or_above,
        }
        self._journal.write("stability", base.run_id, record)
        self._say(f"stability {base.run_id}: {passes}/{len(results)}")
        return record

    # -- stage 3: candidates ------------------------------------------------

    def _candidates_for(self, base: BaseRun) -> None:
        found = self._runner.tool_steps(base.run_id)
        self._repeated = {step.step_idx for step in found if _repeats_before(found, step)}
        steps = {step.step_idx: step for step in found}
        order = _flowing_first(
            attempt_order(
                bucketed(sorted(steps)),
                seed=derive_seed(self._config.seed, base.run_id),
                attempts_per_bucket=self._config.attempts_per_bucket,
            ),
            steps,
        )
        kept_buckets: set[PositionBucket] = set()
        for bucket, step_idx in order:
            if len(kept_buckets) >= self._config.max_kept_per_run:
                return
            if bucket in kept_buckets or len(self._items) >= self._config.target_items:
                continue
            if self._one_candidate(base, steps[step_idx], bucket):
                kept_buckets.add(bucket)

    def _one_candidate(self, base: BaseRun, step: ToolStep, bucket: PositionBucket) -> bool:
        key = f"{base.run_id}-k{step.step_idx}"
        record = self._journal.read("candidate", key)
        if record is None:
            record = self._measure_candidate(base, step, bucket, key)
        self._bump("candidates")
        if record["status"] != "kept":
            self._bump(f"rejected_{record['reason_code']}")
            return False
        self._bump("kept")
        with self._lock:
            self._items.append(record["item"])
        return True

    def _measure_candidate(
        self, base: BaseRun, step: ToolStep, bucket: PositionBucket, key: str
    ) -> dict[str, Any]:
        if step.step_idx in self._repeated:
            # A standing fault would rewrite the prefix as well as the step
            # (`docs/decisions/0016-persistent-planted-fault.md`), so the
            # recording would no longer be the base run's.
            return self._rejected(
                key, "repeated_call",
                "this exact call already occurred before k, so a standing fault would "
                "rewrite the prefix too",
                base, step, bucket,
            )
        faulted = self._plant(base, step)
        if faulted is None:
            return self._rejected(key, "unplantable", "no fault type can be planted here",
                                  base, step, bucket)
        fault_type, mutated, mutation = faulted
        seeds = [
            derive_seed(self._config.seed, base.run_id, f"k{step.step_idx}", fault_type, str(i))
            for i in range(self._config.n_reruns)
        ]
        try:
            reruns = self._faulted_reruns(base, step, fault_type, mutated, seeds)
        except _Infra as failure:
            return self._rejected(key, "infra", str(failure), base, step, bucket)
        return self._verdict(key, base, step, bucket, fault_type, mutated, mutation, seeds, reruns)

    def _plant(self, base: BaseRun, step: ToolStep) -> tuple[FaultType, dict, dict] | None:
        """The balanced fault type that can actually be planted here."""
        context = FaultContext(
            tool_name=step.tool_name, tool_args=dict(step.tool_args),
            downstream=step.downstream, downstream_writes=step.downstream_writes,
        )
        seed = derive_seed(self._config.seed, base.run_id, f"k{step.step_idx}")
        possible: dict[FaultType, Any] = {}
        for fault_type in FAULT_TYPES:
            try:
                possible[fault_type] = plant(step.result, fault_type=fault_type,
                                             seed=seed, context=context)
            except NoFaultPossibleError:
                continue
        if not possible:
            return None
        with self._lock:
            chosen = self._balancer.take(tuple(possible))
        result = possible[chosen]
        return chosen, dict(result.payload), result.mutation.to_dict()

    def _faulted_reruns(
        self,
        base: BaseRun,
        step: ToolStep,
        fault_type: str,
        mutated: Mapping[str, Any],
        seeds: Sequence[int],
    ) -> list[RerunResult]:
        results = []
        for index, seed in enumerate(seeds):
            stem = f"{base.run_id}-k{step.step_idx}-{fault_type}"
            results.append(
                self._with_retries(base, step, mutated, fault_type, stem, index, seed)
            )
        return results

    def _with_retries(
        self,
        base: BaseRun,
        step: ToolStep,
        mutated: Mapping[str, Any],
        fault_type: str,
        stem: str,
        index: int,
        seed: int,
    ) -> RerunResult:
        """One faulted re-run, retried through infrastructure failures.

        An infra failure is never a task failure
        (`docs/decisions/0004-p0-probe-protocol.md` §3): the attempt gets
        a fresh run id so the dead recording stays on the tape as
        evidence, and only a candidate that never completes is abandoned.
        """
        last = ""
        for attempt in range(MAX_INFRA_RETRIES + 1):
            run_id = f"{stem}-s{index}" if attempt == 0 else f"{stem}-s{index}-a{attempt + 1}"
            try:
                return self._guarded(
                    lambda r=run_id: self._runner.fault_fork(
                        base.run_id, run_id=r, step_idx=step.step_idx,
                        tool_name=step.tool_name, tool_args=dict(step.tool_args),
                        faulted_result=dict(mutated), fault_type=fault_type, seed=seed,
                    )
                )
            except _Infra as failure:
                last = str(failure)
                self._bump("infra_retries")
        raise _Infra(f"{MAX_INFRA_RETRIES + 1} attempts all failed on infrastructure: {last}")

    def _verdict(
        self,
        key: str,
        base: BaseRun,
        step: ToolStep,
        bucket: PositionBucket,
        fault_type: FaultType,
        mutated: Mapping[str, Any],
        mutation: Mapping[str, Any],
        seeds: Sequence[int],
        reruns: Sequence[RerunResult],
    ) -> dict[str, Any]:
        passes = sum(1 for rerun in reruns if rerun.passed)
        rate = passes / len(reruns)
        failed = next((rerun for rerun in reruns if not rerun.passed), None)
        item = None if failed is None else {
            "item_id": f"{base.domain}-{base.task_id}-k{step.step_idx}-{fault_type}",
            "domain": base.domain,
            "task_id": base.task_id,
            "base_run_id": base.run_id,
            "base_pass_rate": self._stability_rate(base),
            "run_id": failed.run_id,
            "faulted_pass_rate": rate,
            "planted_step": step.step_idx,
            "position_bucket": bucket,
            "fault_type": fault_type,
            "mutation": dict(mutation),
            "oracle": {"tool_result_ref": step.result_ref, "step_idx": step.step_idx},
            "intervention": ReplaceToolResult(
                step=step.step_idx, new_result=dict(mutated)
            ).to_ref(),
            "intervention_ref": failed.intervention_ref,
            "seeds": list(seeds),
            "n_reruns": len(reruns),
        }
        if rate > self._config.keep_at_or_below or item is None:
            # The item is kept on the record even when the candidate is
            # not: the recording exists either way, and a fault that
            # flipped the run twice in four is evidence of a weaker
            # causal effect rather than of nothing
            # (`docs/decisions/0021-p3-outcome.md`). What it is NOT is
            # eligible for the pre-registered set, which is why the
            # status stays `rejected`.
            return self._rejected(
                key, "not_flipped", f"faulted pass rate {rate} above "
                f"{self._config.keep_at_or_below}", base, step, bucket, fault_type, rate,
                item=item, rerun_run_ids=[rerun.run_id for rerun in reruns],
            )
        record = {"status": "kept", "reason_code": "kept", "item": item,
                  "rerun_run_ids": [rerun.run_id for rerun in reruns]}
        self._journal.write("candidate", key, record)
        self._journal.log({"kind": "candidate", "key": key, "status": "kept",
                           "fault_type": fault_type, "position_bucket": bucket,
                           "planted_step": step.step_idx, "faulted_pass_rate": rate})
        self._say(f"kept {item['item_id']} ({rate})")
        return record

    def _rejected(
        self,
        key: str,
        reason_code: str,
        reason: str,
        base: BaseRun,
        step: ToolStep,
        bucket: PositionBucket,
        fault_type: str | None = None,
        rate: float | None = None,
        item: dict[str, Any] | None = None,
        rerun_run_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "status": "rejected", "reason_code": reason_code, "reason": reason,
            "base_run_id": base.run_id, "planted_step": step.step_idx,
            "position_bucket": bucket, "fault_type": fault_type,
            "faulted_pass_rate": rate,
        }
        if item is not None:
            record["item"] = item
        if rerun_run_ids:
            record["rerun_run_ids"] = rerun_run_ids
        self._journal.write("candidate", key, record)
        self._journal.log({"kind": "candidate", "key": key, "status": "rejected",
                           "reason": reason, "reason_code": reason_code,
                           "fault_type": fault_type, "position_bucket": bucket,
                           "planted_step": step.step_idx})
        return record

    def _stability_rate(self, base: BaseRun) -> float:
        record = self._journal.read("stability", base.run_id) or {}
        return float(record.get("rate", 1.0))

    # -- shared -------------------------------------------------------------

    def _bump(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + by

    def _guarded(self, call: Callable[[], Any]) -> Any:
        """Run `call`, sorting its failures into stop / retry / raise."""
        try:
            return call()
        except AuthenticationError as exc:
            raise _Stop("authentication rejected") from exc
        except BudgetExceededError as exc:
            raise _Stop("budget exhausted") from exc
        except _Stop:
            raise
        except TransportError as exc:
            self._gate.on_transport_failure()
            self._bump(f"transport_{_transport_kind(exc)}")
            raise _Infra(f"{type(exc).__name__}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - an infra failure is data, not a crash
            raise _Infra(f"{type(exc).__name__}: {exc}") from exc


class _Gate:
    """How many tasks may be in flight, adapting down under a storm.

    Additive-increase, multiplicative-decrease over the provider's own
    signals: halve on a burst of transport failures, creep back up as
    tasks complete. The limiter, the retry policy and the ledger are
    unchanged and still do their jobs — this is about not asking a
    provider that is already failing for more work, which is what turned
    a slow half-hour into 138 lost tasks.
    """

    #: Transport failures within one window before the gate reacts.
    STORM = 3
    #: Successful tasks before it lets one more thread in.
    RECOVERY = 8

    def __init__(self, allowed: int = 1, minimum: int = 2) -> None:
        self._ceiling = max(allowed, minimum)
        self._allowed = self._ceiling
        self._minimum = min(minimum, self._ceiling)
        self._in_flight = 0
        self._failures = 0
        self._successes = 0
        self._condition = threading.Condition()

    @property
    def allowed(self) -> int:
        with self._condition:
            return self._allowed

    def resize(self, allowed: int) -> None:
        with self._condition:
            self._ceiling = max(allowed, self._minimum)
            self._allowed = self._ceiling
            self._condition.notify_all()

    def __enter__(self) -> _Gate:
        with self._condition:
            while self._in_flight >= self._allowed:
                self._condition.wait(timeout=5.0)
            self._in_flight += 1
        return self

    def __exit__(self, *_exc: object) -> None:
        with self._condition:
            self._in_flight -= 1
            self._condition.notify()

    def on_transport_failure(self) -> None:
        with self._condition:
            self._failures += 1
            self._successes = 0
            if self._failures >= self.STORM and self._allowed > self._minimum:
                self._allowed = max(self._minimum, self._allowed // 2)
                self._failures = 0

    def on_success(self) -> None:
        with self._condition:
            self._failures = 0
            self._successes += 1
            if self._successes >= self.RECOVERY and self._allowed < self._ceiling:
                self._allowed += 1
                self._successes = 0
                self._condition.notify()


class _Infra(Exception):
    """An infrastructure failure: retried, and never scored as a run failure."""


def _flowing_first(
    order: Sequence[tuple[PositionBucket, int]], steps: Mapping[int, ToolStep]
) -> list[tuple[PositionBucket, int]]:
    """The same attempts, those that can actually bite tried first.

    A stable sort, so the round-robin over position buckets is preserved
    inside each group and every stratum is still reached — this changes
    the ORDER attempts are spent in, never which ones exist
    (`docs/decisions/0017-p3-collection-policy.md` §7).
    """
    # Late candidates first among the flowing ones: 11 of the first 18
    # kept items were early and 1 was late, and a stratum that is only
    # reached when the budget holds out is a stratum reported thin.
    rank = {"late": 0, "middle": 1, "early": 2}
    return sorted(
        order,
        key=lambda entry: (not steps[entry[1]].flows_into_a_write, rank.get(entry[0], 3)),
    )


def _transport_kind(exc: Exception) -> str:
    """`429`, `504`, `timeout` or `other`, for the funnel's error mix."""
    text = str(exc).lower()
    for code in ("429", "504", "503", "502"):
        if code in text:
            return code
    return "timeout" if "timeout" in text else "other"


def _repeats_before(steps: Sequence[ToolStep], step: ToolStep) -> bool:
    """Was this exact `(tool, args)` call already made earlier in the run?

    A standing fault matches by call, not by step, so faulting a repeated
    call would corrupt its earlier occurrences too — rewriting the prefix
    the item is supposed to share with its base run.
    """
    return any(
        other.step_idx < step.step_idx
        and other.tool_name == step.tool_name
        and dict(other.tool_args) == dict(step.tool_args)
        for other in steps
    )


def _kept_count(journal: Journal) -> int:
    """Kept items on disk, across every shard sharing this journal."""
    return sum(1 for record in journal.all("candidate") if record.get("status") == "kept")


def _kept_by_fault_type(journal: Journal) -> dict[str, int]:
    """The balance already on disk, so a resumed collection continues it."""
    counts: dict[str, int] = {}
    for record in journal.all("candidate"):
        if record.get("status") != "kept":
            continue
        fault_type = record["item"]["fault_type"]
        counts[fault_type] = counts.get(fault_type, 0) + 1
    return counts
