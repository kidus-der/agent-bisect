"""`search.ForkExecutor` over a recorded tau2 run.

One `RerunRequest` becomes one real fork: `Tau2ForkDriver` re-drives tau2's
own orchestrator with the prefix served from the tape, the intervention
applied at the fork step, and the suffix sampled live
(`docs/decisions/0010-replay-mechanism.md`).

Three things this layer adds on top of the driver:

1. **Resume.** A fork's `run_id` is a deterministic function of the parent,
   the arm, the step and the seed (`attribution.search.rerun_id`), so an
   interrupted evaluation asks for exactly the forks it already has. If the
   tape already holds an outcome for that id, it is returned and nothing is
   re-run — the "a resume pays for nothing twice" rule, applied to replay
   rather than to the judge.
2. **The prefix mode travels with the request.** `prefix_tools` and
   `unsafe_positional` come off the `RerunRequest`, which is how the
   re-run-live baseline differs from Bisect and nothing else does.
3. **An infrastructure abort is not a failure.** A fork that died on
   infrastructure has no outcome, and scoring it as a failed run would put
   an infra error into the treated arm. It is retried once with a fresh
   seed and then raised, for the caller to record as an unevaluated item.
4. **The item's standing fault is re-installed on every fork.** A planted
   fault is a faulty *tool*, not an edited recording
   (`docs/decisions/0016-persistent-planted-fault.md`), and it rides in the
   parent run's `RunManifest.params`. `FaultedForkDriver` puts it back
   underneath the recorder and the replayer, which is what makes a control
   forked before the planted step still reproduce the failure — the thing
   `docs/findings/p5-control-fork.md` showed a one-shot fault could not do.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_bisect.adapters.tau2_fault_fork import FaultedForkDriver
from agent_bisect.adapters.tau2_fault_injector import injector_spec_from
from agent_bisect.adapters.tau2_replay import InfraAbortError
from agent_bisect.attribution.search import RerunOutcome, RerunRequest
from agent_bisect.core.runner import ForkSpec, run_fork
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter, UnknownRunError

#: One retry, with a different seed, before an infra abort is raised.
INFRA_RETRIES = 1
#: Offset folded into the seed of a retry so it is not the same draw again.
_RETRY_SEED_OFFSET = 1_000_003


class Tau2ForkExecutor:
    """Runs one fork per request, reusing any the tape already holds."""

    def __init__(
        self,
        *,
        store: BlobStore,
        reader: TapeReader,
        tape: TapeWriter,
        live_completion: Callable[..., Any] | None = None,
    ) -> None:
        self._store = store
        self._reader = reader
        self._tape = tape
        self._live_completion = live_completion
        self.reused = 0

    def _live(self) -> Callable[..., Any]:
        """Whatever tau2 currently calls for a completion — the router.

        A fork's live suffix must go through `route_tau2_llm`'s router, not
        past it: the router is what tags the purpose, charges the ledger,
        applies the limiter *and* hands the call to the active recorder. A
        raw completion function would be served, but the step would never
        be recorded, so the replayer's idea of where it is would stop
        advancing and the next tape step would be mistaken for the fork
        step. Resolved per call, before the replayer nests its own patch.
        """
        if self._live_completion is not None:
            return self._live_completion
        import tau2.utils.llm_utils as llm_utils

        return llm_utils.completion

    def _recorded(self, run_id: str) -> RerunOutcome | None:
        """The outcome of a fork that has already been run, if there is one."""
        try:
            outcome = self._reader.get_outcome(run_id)
        except UnknownRunError:
            return None
        if outcome is None:
            return None
        steps = self._reader.get_steps(run_id)
        self.reused += 1
        # `calls` is what this process spent, and it spent nothing: a
        # resumed fork must not be charged to the run that did not buy it.
        return RerunOutcome(passed=outcome.passed, n_steps=len(steps), calls=0)

    def _run_once(self, request: RerunRequest, seed: int) -> RerunOutcome:
        # A fork carries NO per-re-run seed, and the draw's seed reaches
        # only the fork's identity (`rerun_id`) and its recorded row.
        #
        # Two things were tried and both are wrong. Putting it on
        # `ForkSpec.seed` re-pins the whole re-driven run, and `seed` is one
        # of the sampling params `canonical_request_hash` covers, so the
        # fork diverges on its own first prefix step. Injecting it at the
        # live seam instead keeps the prefix matching but makes the forked
        # *recording* unreplayable: its prefix rows and its suffix rows
        # would want two different orchestrator seeds. Carrying a suffix
        # seed properly needs the replay engine to record it on the fork
        # manifest and re-apply it from the fork step onward, which it does
        # not do (same conclusion as `bench/inject.py`, commit ee41bed).
        #
        # So the arms' draws differ only by provider non-determinism. That
        # is a real dependency and P5 reports it: if re-runs do not vary,
        # N draws are not N observations and the interval is not a 95%
        # interval. P3's stability check (re-run 4x) is what measures it.
        spec = ForkSpec(
            parent_run_id=request.parent_run_id,
            run_id=request.run_id,
            fork_step=request.fork_step,
            prefix_tools=request.prefix_tools,
            seed=None,
        )
        driver = FaultedForkDriver(
            spec,
            store=self._store,
            reader=self._reader,
            tape=self._tape,
            live_completion=self._live(),
            fault=self._fault_of(request.parent_run_id),
            unsafe_positional=request.unsafe_positional,
        )
        outcome = run_fork(driver, spec, request.intervention)
        result = driver.result
        return RerunOutcome(
            passed=outcome.passed,
            n_steps=0 if result is None else result.steps,
            calls=0 if result is None else result.live_llm_calls,
            unguarded_calls=0 if result is None else result.unguarded_llm_calls,
        )

    def _fault_of(self, parent_run_id: str) -> Any:
        """The standing fault the parent run was recorded under, if any."""
        return injector_spec_from(self._reader.get_manifest(parent_run_id).params)

    def run(self, request: RerunRequest) -> RerunOutcome:
        """One fork: reused if the tape has it, otherwise run for real."""
        recorded = self._recorded(request.run_id)
        if recorded is not None:
            return recorded
        try:
            return self._run_once(request, request.seed)
        except InfraAbortError:
            if INFRA_RETRIES <= 0:
                raise
        # Outside the except block so the retry's own failure is not
        # chained onto the first one, which says nothing extra.
        retry = RerunRequest(
            parent_run_id=request.parent_run_id,
            run_id=f"{request.run_id}-retry",
            fork_step=request.fork_step,
            arm=request.arm,
            intervention=request.intervention,
            seed=request.seed + _RETRY_SEED_OFFSET,
            prefix_tools=request.prefix_tools,
            unsafe_positional=request.unsafe_positional,
        )
        return self._run_once(retry, retry.seed)
