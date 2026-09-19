"""Bisect: judge shortlist -> confirm each suspect by re-running -> earliest step.

The shape of one diagnosis, and where each piece comes from:

1. **Shortlist.** The all-at-once judge's top `m` suspects
   (`attribution/judge.py`). Every method in `bench/baselines.py` is handed
   the *same* `JudgeVerdict`, so a difference between methods is a
   difference in the confirmation step and never in judge luck. If the
   judge omits the culprit, replay cannot find it — which is why
   `docs/brief/summary.md` §2 insists recall@m is reported separately from
   accuracy.
2. **One intervention per suspect, chosen by step type alone**, with no
   knowledge of the label, the fault or the oracle:
   `docs/decisions/0013-suspect-interventions.md`.
3. **Effects** from `attribution/estimate.py`, against a shared control
   arm forked at the earliest tested step
   (`docs/decisions/0005-shared-control.md`).
4. **Blame** = the earliest step whose decision boundary clears delta, or
   `None`. Not the largest effect: a later fix can partially recover a run
   that was already doomed earlier.

This module does not know what a tau2 run is. It reaches the world through
`ForkExecutor`, which takes a `RerunRequest` and gives back a pass/fail —
the tau2 implementation lives in `adapters/`, the offline tests script it.

Draws within a batch run concurrently
-------------------------------------
The `n` draws of one batch are independent by construction, so they are
taken in a thread pool rather than one after another. That is a pure
throughput change: the estimator still sees one batch at a time, the
records still come back in draw order, and the statistics are untouched.
It matters because a fork's cost is dominated by latency, not by rate —
tau2's user simulator is a reasoning model whose turns take tens of
seconds — so a sequential evaluation would be latency-bound at a fraction
of the measured rate limit. `concurrency=1` restores the serial order
exactly, which is what the offline tests use.

Re-run identity is deterministic
--------------------------------
A fork's `run_id` is derived from the parent run, the arm, the fork step
and the seed, so re-running an interrupted evaluation asks for exactly the
same forks. An executor that already has one on the tape can return it
instead of paying for it again — the same "a resume pays for nothing
twice" rule the judge store follows.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from agent_bisect.attribution.estimate import (
    Arm,
    ControlMode,
    RunEstimate,
    SequentialConfig,
    estimate_run,
)
from agent_bisect.attribution.interventions import Resample, TruthfulToolResult
from agent_bisect.attribution.judge_view import JudgeVerdict
from agent_bisect.core.replay import Intervention, NoOpIntervention
from agent_bisect.core.runner import PrefixMode
from agent_bisect.core.tape import Step

#: Which confirmation procedure produced a result. `bisect` is the method;
#: the other two are the ablations of `docs/decisions/0001-*` (P5
#: baselines) and differ from it only in this config.
Method = Literal["bisect", "rerun_live", "no_control"]

DEFAULT_TOP_M = 3

#: Draws taken at once within one batch. 1 is strictly sequential.
DEFAULT_CONCURRENCY = 1

_ID_BYTES = 6


@dataclass(frozen=True, slots=True)
class BlameConfig:
    """Everything one diagnosis may vary. The P5 primary is the default."""

    top_m: int = DEFAULT_TOP_M
    sequential: SequentialConfig = field(default_factory=SequentialConfig)
    control_mode: ControlMode = "shared"
    prefix_tools: PrefixMode = "snapshot"
    unsafe_positional: bool = False
    method: Method = "bisect"
    #: How many draws of one batch are in flight at once. Throughput only:
    #: the draws are independent, so this cannot change a result.
    concurrency: int = DEFAULT_CONCURRENCY

    def __post_init__(self) -> None:
        if self.top_m <= 0:
            raise ValueError(f"top_m must be positive, got {self.top_m}")
        if self.concurrency <= 0:
            raise ValueError(f"concurrency must be positive, got {self.concurrency}")
        if self.unsafe_positional and self.prefix_tools == "snapshot":
            raise ValueError(
                "unsafe_positional is the re-run-live baseline's weakness; it has no "
                "meaning with prefix_tools='snapshot', where the prefix cannot drift"
            )


@dataclass(frozen=True, slots=True)
class RerunRequest:
    """One fork to run: where to cut the run, what to change, how to get there."""

    parent_run_id: str
    run_id: str
    fork_step: int
    arm: Arm
    intervention: Intervention
    seed: int
    prefix_tools: PrefixMode
    unsafe_positional: bool


@dataclass(frozen=True, slots=True)
class RerunOutcome:
    """What one fork produced. `calls` is the LLM calls its live suffix spent.

    `unguarded_calls` is how often a recorded reply was served to a request
    the recording does not match. It is 0 for every Bisect arm by
    construction and non-zero only for the re-run-live baseline, whose
    prefix drifts; carrying it makes that weakness a number rather than a
    footnote.
    """

    passed: bool
    n_steps: int
    calls: int
    unguarded_calls: int = 0


@dataclass(frozen=True, slots=True)
class RerunRecord:
    """One individual re-run, kept so a result can be audited row by row.

    Mirrors `server.schemas_runs.RerunRow` field for field.
    """

    rerun_id: str
    arm: Arm
    step: int
    seed: int
    passed: bool
    n_steps: int
    calls: int
    unguarded_calls: int = 0


class ForkExecutor(Protocol):
    """The search's only contact with the world."""

    def run(self, request: RerunRequest) -> RerunOutcome: ...


#: Given the recorded tool step, what the tool really answers there.
TruthFor = Callable[[Step], Mapping[str, Any]]


def choose_intervention(step: Step, truth_for: TruthFor | None = None) -> Intervention:
    """The intervention for a suspect, by step type alone.

    Label-free by construction: nothing here reads a planted step, a fault
    type or an original tool result. See
    `docs/decisions/0013-suspect-interventions.md`.
    """
    if step.actor == "tool":
        fix = TruthfulToolResult(step=step.step_idx)
        return fix if truth_for is None else fix.with_truth(truth_for)
    if step.actor in ("agent", "user"):
        return Resample(step=step.step_idx)
    raise ValueError(
        f"step {step.step_idx} is an {step.actor} step; tau2's evaluator runs after the "
        "loop and cannot be a causal step of the trajectory"
    )


def rerun_id(parent_run_id: str, *, arm: Arm, step: int, seed: int, draw: int) -> str:
    """A stable id for one fork, so a resumed evaluation asks for the same one."""
    digest = hashlib.blake2b(
        f"{parent_run_id}:{arm}:{step}:{seed}:{draw}".encode(), digest_size=_ID_BYTES
    ).hexdigest()
    return f"{parent_run_id}-{arm[0]}{step}-{digest}"


def _draw_seed(seed: int, draw: int) -> int:
    """A distinct, stable seed per individual re-run within one batch."""
    return int.from_bytes(
        hashlib.blake2b(f"{seed}:{draw}".encode(), digest_size=4).digest(), "big"
    )


class ForkRerunSampler:
    """`estimate.RerunSampler` over real forks, recording every individual re-run."""

    def __init__(
        self,
        *,
        parent_run_id: str,
        executor: ForkExecutor,
        interventions: Mapping[int, Intervention],
        config: BlameConfig,
    ) -> None:
        self._parent_run_id = parent_run_id
        self._executor = executor
        self._interventions = dict(interventions)
        self._config = config
        self._records: list[RerunRecord] = []

    @property
    def records(self) -> tuple[RerunRecord, ...]:
        return tuple(self._records)

    @property
    def replay_calls(self) -> int:
        return sum(record.calls for record in self._records)

    @property
    def unguarded_calls(self) -> int:
        return sum(record.unguarded_calls for record in self._records)

    def _intervention_for(self, step: int, arm: Arm) -> Intervention:
        if arm == "control":
            return NoOpIntervention()
        try:
            return self._interventions[step]
        except KeyError:
            raise ValueError(
                f"no intervention was prepared for step {step}; the sampler must never "
                "be asked for a step outside the shortlist"
            ) from None

    def _request(self, step: int, arm: Arm, seed: int, draw: int) -> RerunRequest:
        return RerunRequest(
            parent_run_id=self._parent_run_id,
            run_id=rerun_id(
                self._parent_run_id, arm=arm, step=step, seed=seed, draw=draw
            ),
            fork_step=step,
            arm=arm,
            intervention=self._intervention_for(step, arm),
            seed=_draw_seed(seed, draw),
            prefix_tools=self._config.prefix_tools,
            unsafe_positional=self._config.unsafe_positional,
        )

    def _record_of(self, request: RerunRequest, outcome: RerunOutcome) -> RerunRecord:
        return RerunRecord(
            rerun_id=request.run_id,
            arm=request.arm,
            step=request.fork_step,
            seed=request.seed,
            passed=outcome.passed,
            n_steps=outcome.n_steps,
            calls=outcome.calls,
            unguarded_calls=outcome.unguarded_calls,
        )

    def sample(self, step: int, arm: Arm, n: int, seed: int) -> Sequence[bool]:
        """`n` forks at `step` on `arm`, one pass/fail each.

        Taken concurrently when `config.concurrency > 1`. Records are
        appended in draw order whatever order they finished in, so the
        stored result does not depend on the scheduler.
        """
        requests = [self._request(step, arm, seed, draw) for draw in range(n)]
        if self._config.concurrency == 1 or n == 1:
            outcomes = [self._executor.run(request) for request in requests]
        else:
            with ThreadPoolExecutor(
                max_workers=min(self._config.concurrency, n),
                thread_name_prefix=f"fork-{arm[0]}{step}",
            ) as pool:
                # `map` re-raises the first exception in submission order
                # once the pool has drained, so an infra abort still
                # surfaces and no fork is left running behind it.
                outcomes = list(pool.map(self._executor.run, requests))
        self._records.extend(
            self._record_of(request, outcome)
            for request, outcome in zip(requests, outcomes, strict=True)
        )
        return tuple(outcome.passed for outcome in outcomes)


@dataclass(frozen=True, slots=True)
class BlameResult:
    """One diagnosis, with everything needed to audit or redraw it."""

    item_id: str
    run_id: str
    method: Method
    blamed_step: int | None
    estimate: RunEstimate | None
    reruns: tuple[RerunRecord, ...]
    judge: JudgeVerdict
    #: The judge's top-m suspects, as handed to the search.
    shortlist: tuple[int, ...]
    #: The subset actually confirmed by re-running: a suspect the search
    #: could not intervene on is in `untestable`, never silently in both.
    tested_steps: tuple[int, ...]
    interventions: Mapping[int, str]
    untestable: tuple[str, ...]
    judge_calls: int
    replay_calls: int
    config: BlameConfig
    #: Responses served past the request-hash guard. Must be 0 for every
    #: method but `rerun_live`; `scripts/gates/p5.py` checks it.
    unguarded_calls: int = 0

    @property
    def total_calls(self) -> int:
        return self.judge_calls + self.replay_calls


def _prepare(
    steps: Sequence[Step], shortlist: Sequence[int], truth_for: TruthFor | None
) -> tuple[dict[int, Intervention], list[str]]:
    """An intervention per testable suspect, and a note per suspect that is not."""
    by_index = {step.step_idx: step for step in steps}
    interventions: dict[int, Intervention] = {}
    untestable: list[str] = []
    for suspect in shortlist:
        step = by_index.get(suspect)
        if step is None:
            untestable.append(f"step {suspect} is not in the recorded run")
            continue
        try:
            interventions[suspect] = choose_intervention(step, truth_for)
        except ValueError as exc:
            untestable.append(f"step {suspect}: {exc}")
    return interventions, untestable


def run_blame(
    *,
    item_id: str,
    run_id: str,
    steps: Sequence[Step],
    verdict: JudgeVerdict,
    executor: ForkExecutor,
    config: BlameConfig,
    seed: int,
    truth_for: TruthFor | None = None,
) -> BlameResult:
    """Confirm the judge's shortlist by re-running, and name the earliest cause.

    The judge has already been asked (`verdict`), so every method can be
    given the same shortlist. A verdict that named nothing — because the
    judge failed to answer, or answered and ranked nothing — costs no
    re-runs and blames nothing, which is a wrong answer and is recorded as
    one rather than dropped.
    """
    shortlist = verdict.shortlist(config.top_m) if verdict.ranking else ()
    interventions, untestable = _prepare(steps, shortlist, truth_for)

    if not interventions:
        return BlameResult(
            item_id=item_id,
            run_id=run_id,
            method=config.method,
            blamed_step=None,
            estimate=None,
            reruns=(),
            judge=verdict,
            shortlist=tuple(shortlist),
            tested_steps=(),
            interventions={},
            untestable=tuple(untestable),
            judge_calls=verdict.calls,
            replay_calls=0,
            config=config,
        )

    sampler = ForkRerunSampler(
        parent_run_id=run_id,
        executor=executor,
        interventions=interventions,
        config=config,
    )
    estimate = estimate_run(
        interventions.keys(),
        sampler,
        config.sequential,
        config.control_mode,
        seed=seed,
    )
    return BlameResult(
        item_id=item_id,
        run_id=run_id,
        method=config.method,
        blamed_step=estimate.blamed_step,
        estimate=estimate,
        reruns=sampler.records,
        judge=verdict,
        shortlist=tuple(shortlist),
        tested_steps=tuple(interventions),
        interventions={step: fix.name for step, fix in interventions.items()},
        untestable=tuple(untestable),
        judge_calls=verdict.calls,
        replay_calls=sampler.replay_calls,
        config=config,
        unguarded_calls=sampler.unguarded_calls,
    )
