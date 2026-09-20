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
4. **tau2's NL-assertion judge is repointed on every fork.** Retail tasks
   whose `reward_basis` includes `NL_ASSERTION` make an evaluator LLM call
   on the reward path, and it was recorded under the P0-chosen judge
   (`docs/decisions/0018-p5-budget.md`). Replaying without repointing it
   diverges on the model name alone, so `judge_routed()` wraps every fork.
   Airline has no such task and is unaffected, which is exactly why this
   is easy to miss.
5. **The item's standing fault is re-installed on every fork.** A planted
   fault is a faulty *tool*, not an edited recording
   (`docs/decisions/0016-persistent-planted-fault.md`), and it rides in the
   parent run's `RunManifest.params`. `FaultedForkDriver` puts it back
   underneath the recorder and the replayer, which is what makes a control
   forked before the planted step still reproduce the failure — the thing
   `docs/findings/p5-control-fork.md` showed a one-shot fault could not do.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from agent_bisect.adapters.tau2_fault_fork import FaultedForkDriver
from agent_bisect.adapters.tau2_fault_injector import injector_spec_from
from agent_bisect.adapters.tau2_judge import judge_routed
from agent_bisect.adapters.tau2_replay import InfraAbortError
from agent_bisect.attribution.search import RerunOutcome, RerunRequest, TruthFor
from agent_bisect.core.llm import TransportError
from agent_bisect.core.runner import ForkSpec, run_fork
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import (
    DuplicateRunError,
    Step,
    TapeReader,
    TapeWriter,
    UnknownRunError,
)

#: Attempts per fork before giving up on it. A fork is ~12 LLM calls and
#: the provider has run at a 25% retry rate for hours; with one attempt a
#: single 504 anywhere in those 12 calls loses the fork, the fork loses
#: the item, and the item loses every other fork it had already bought.
#: Retrying the fork itself is what keeps an item's progress additive.
INFRA_RETRIES = 3
#: Seconds between a fork's attempts, so a degraded endpoint is not
#: hammered by the retry that is meant to survive it.
RETRY_BACKOFF_S = 20.0
#: How many `-r<n>` suffixes to try before giving up on a free run id.
MAX_ID_ATTEMPTS = 50
#: How many `-r<n>` suffixes a resume looks back through when hunting for
#: a draw's recorded outcome. Small: ids only grow suffixes when a run
#: died mid-fork, which is rare per draw.
_ID_RETRY_LOOKBACK = 3
#: Offset folded into the seed of a retry so it is not the same draw again.
_RETRY_SEED_OFFSET = 1_000_003


def serialized_truth(truth: TruthFor) -> TruthFor:
    """`truth` behind a lock, because the forks of one item run concurrently.

    `Tau2TruthResolver` caches one throwaway environment and restores the
    step's recorded entry state into it per call. Two treated forks
    resolving truth at the same time would restore over each other and
    could each read the other's world — a silently wrong value in the
    **treated** arm, which is the arm the whole effect estimate rests on,
    and one that would look like a plausible result rather than a bug.

    Serialising costs nothing worth having: truth resolution is one DB
    restore and one tool execution against a local environment, next to a
    fork whose live suffix is tens of seconds of model latency.

    Honest scope: with today's callers the race is **latent, not active**.
    `estimate_run` takes one step at a time and every draw within a batch
    targets that same step, so concurrent resolutions restore identical
    state and agree; separate items get separate resolvers. The wrapper is
    here so the property holds *structurally* rather than by coincidence
    of the caller — the next person to overlap two steps should not have
    to rediscover this.
    """
    lock = threading.Lock()

    def resolve(step: Step) -> Mapping[str, Any]:
        with lock:
            return truth(step)

    return resolve


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
        self.infra_retries = 0

    def _live(self) -> Callable[..., Any]:
        """The router's completion — the live source for a fork's suffix.

        It must be the **router**, and it must be handed in. Two ways to
        get this wrong, both of which we have now made:

        - a raw completion function is served but never reaches the
          recorder, so the replayer's position stops advancing and the
          next tape step is mistaken for the fork step;
        - `llm_utils.completion` is read off the seam. That used to BE the
          router, but it is now `_CompletionDispatcher`, which looks up
          the active per-thread completion — the replayer's own — and
          calls it. The fork then recurses until `RecursionError`, which
          surfaces as an item that "timed out".

        So there is no safe default: the caller binds the router from
        `recording_session` and passes it in.
        """
        if self._live_completion is None:
            raise RuntimeError(
                "Tau2ForkExecutor needs the router's completion. Bind it from "
                "`recording_session(...) as router` and pass "
                "`live_completion=router.completion`; reading it off "
                "`llm_utils.completion` picks up the replay dispatcher and recurses."
            )
        return self._live_completion

    def _free_run_id(self, run_id: str) -> str:
        """`run_id`, or the first `-r<n>` variant the tape has no manifest for.

        A fork that died mid-run leaves its manifest behind with no
        outcome, and the tape is append-only, so a retry cannot reuse the
        id: `start_run` raises `DuplicateRunError` and the whole item is
        lost. It takes a fresh id instead and the dead attempt stays on
        the tape as evidence. Same approach as `tau2_batch.free_run_id`.
        """
        candidate = run_id
        for attempt in range(1, MAX_ID_ATTEMPTS + 1):
            try:
                self._reader.get_manifest(candidate)
            except UnknownRunError:
                return candidate
            candidate = f"{run_id}-r{attempt}"
        raise RuntimeError(
            f"no free run id for {run_id!r} after {MAX_ID_ATTEMPTS} attempts"
        )

    def _recorded(self, run_id: str) -> RerunOutcome | None:
        """The outcome of a fork already run, under `run_id` or a retry of it.

        A draw that failed and then succeeded on attempt 2 has its outcome
        stored under `<id>-a1`, not `<id>`. Looking only at the base id
        made every later pass re-run that draw: control arms accumulated
        85 forks where the design needs 16, and an item's progress never
        converged. A retry's outcome is the draw's outcome, so it counts.
        """
        for candidate in self._candidate_ids(run_id):
            try:
                outcome = self._reader.get_outcome(candidate)
            except UnknownRunError:
                continue
            if outcome is None:
                continue
            steps = self._reader.get_steps(candidate)
            self.reused += 1
            # `calls` is what this process spent, and it spent nothing: a
            # resumed fork must not be charged to the run that did not buy it.
            return RerunOutcome(passed=outcome.passed, n_steps=len(steps), calls=0)
        return None

    def _candidate_ids(self, run_id: str) -> list[str]:
        """`run_id` and the ids its retries would have taken, in order."""
        ids = [run_id]
        for attempt in range(1, INFRA_RETRIES):
            base = f"{run_id}-a{attempt}"
            ids.append(base)
            ids.extend(f"{base}-r{n}" for n in range(1, _ID_RETRY_LOOKBACK + 1))
        ids.extend(f"{run_id}-r{n}" for n in range(1, _ID_RETRY_LOOKBACK + 1))
        return ids

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
            run_id=self._free_run_id(request.run_id),
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
        with judge_routed():
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
        """One fork: reused if the tape has it, otherwise run for real.

        Retried in place on infrastructure. A `DivergenceError` is never
        retried -- it means the recording and the replay disagree, which
        is a finding, not a wobble.
        """
        recorded = self._recorded(request.run_id)
        if recorded is not None:
            return recorded

        attempt = 0
        while True:
            seed = request.seed + attempt * _RETRY_SEED_OFFSET
            run_id = request.run_id if attempt == 0 else f"{request.run_id}-a{attempt}"
            candidate = RerunRequest(
                parent_run_id=request.parent_run_id,
                run_id=run_id,
                fork_step=request.fork_step,
                arm=request.arm,
                intervention=request.intervention,
                seed=seed,
                prefix_tools=request.prefix_tools,
                unsafe_positional=request.unsafe_positional,
            )
            try:
                return self._run_once(candidate, seed)
            except (InfraAbortError, DuplicateRunError, TransportError) as exc:
                attempt += 1
                self.infra_retries += 1
                if attempt >= INFRA_RETRIES:
                    raise
                failure = f"{type(exc).__name__}: {exc}"
            # Outside the except block so the next attempt's own failure is
            # not chained onto this one, which says nothing extra.
            print(
                f"    fork {request.run_id[-18:]} attempt {attempt}/{INFRA_RETRIES} "
                f"after {failure[:90]}",
                flush=True,
            )
            time.sleep(RETRY_BACKOFF_S)
