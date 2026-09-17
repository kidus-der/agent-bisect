"""Forking a run with a standing fault installed in its world.

`adapters.tau2_replay.Tau2ForkDriver` builds its orchestrator inside
`run_rest`, so there is no seam for putting something on the environment
*before* the recorder and the replayer wrap it — and a fault installed
after them would be invisible to both, which is exactly wrong: the tape
has to record what the agent was shown
(`docs/brief/summary.md` §3 rule 1).

So this is a second `core.runner.ForkDriver` rather than a copy: same
replayer, same recorder, same `_driving`, one extra layer underneath
them. It also carries the fault into the forked run's manifest `params`,
so the item can be re-forked and re-replayed into the same world from the
tape alone (`docs/decisions/0016-persistent-planted-fault.md`).

It imports a handful of `tau2_replay`'s private helpers rather than
re-deriving them; an `environment_hook` argument on `Tau2ForkDriver`
would remove the need for this file entirely and is the right stage-B
change.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime
from typing import Any

from agent_bisect.adapters.tau2 import INFRA_TERMINATIONS, Tau2Recorder, build_orchestrator
from agent_bisect.adapters.tau2_fault_injector import FaultSpec, fault_injected, with_injector
from agent_bisect.adapters.tau2_replay import (  # noqa: PLC2701 - see the module docstring
    InfraAbortError,
    ReplayResult,
    Tau2Replayer,
    _driving,
    _run,
    _spec_from,
    _termination_of,
)
from agent_bisect.core.replay import DivergenceError, Intervention, NoOpIntervention
from agent_bisect.core.runner import ForkSpec, fork_manifest
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, TapeReader, TapeWriter


class FaultedForkDriver:
    """`core.runner.ForkDriver` that also installs a standing fault.

    With `fault=None` it is `Tau2ForkDriver` with one more indirection;
    with a fault it is the only way to record a run whose world lies.
    """

    def __init__(
        self,
        spec: ForkSpec,
        *,
        store: BlobStore,
        reader: TapeReader,
        tape: TapeWriter,
        live_completion: Callable[..., Any],
        fault: FaultSpec | None = None,
        unsafe_positional: bool = False,
    ) -> None:
        self._spec = spec
        self._store = store
        self._reader = reader
        self._tape = tape
        self._live_completion = live_completion
        self._fault = fault
        # Only the CAR-style re-run-live baseline sets this, and only
        # because its prefix drifts by construction; see
        # `core.replay.TapeLLM`. The count of responses served past the
        # guard comes back on `result.unguarded_llm_calls`, so no Bisect
        # arm can be produced with the guard off without it showing.
        self._unsafe_positional = unsafe_positional
        self._fork_step = spec.fork_step
        self._intervention: Intervention = NoOpIntervention()
        self.result: ReplayResult | None = None
        self.injector: Any = None

    def restore(self, fork_step: int) -> None:
        self._fork_step = fork_step

    def apply(self, intervention: Intervention) -> None:
        self._intervention = intervention

    def run_rest(self, seed: int | None) -> Outcome:
        parent = self._reader.get_manifest(self._spec.parent_run_id)
        steps = self._reader.get_steps(self._spec.parent_run_id)
        if self._fork_step >= len(steps):
            raise DivergenceError(
                step_idx=self._fork_step,
                actor="run",
                expected=f"a step below {len(steps)}",
                got=f"fork_step {self._fork_step}",
                diff=f"run {parent.run_id!r} has {len(steps)} steps",
            )
        orchestrator = build_orchestrator(_spec_from(parent), self._spec.run_id)
        recorder = Tau2Recorder(
            self._spec.run_id,
            self._store,
            self._tape,
            orchestrator.environment,
            parent_run_id=parent.run_id,
            fork_step=self._fork_step,
        )
        recorder.start(self._manifest_for(parent))
        replayer = Tau2Replayer(
            environment=orchestrator.environment,
            steps=steps,
            store=self._store,
            sink=recorder,
            fork_step=self._fork_step,
            tool_mode="snapshot" if self._spec.prefix_tools == "snapshot" else "rerun_live",
            intervention=self._intervention,
            live_completion=self._live_completion,
            unsafe_positional=self._unsafe_positional,
        )
        simulation = self._drive(orchestrator, replayer, recorder)
        return self._outcome_of(simulation, recorder, replayer, parent.run_id)

    def _manifest_for(self, parent: Any) -> Any:
        """The fork's manifest, carrying the fault it was recorded under.

        `RunManifest.params` is free-form and `fork_manifest` copies it,
        so the fault travels with the run without any change to `core/`.
        """
        manifest = fork_manifest(
            parent,
            run_id=self._spec.run_id,
            fork_step=self._fork_step,
            created_at=datetime.now(UTC),
            seed=None,
        )
        if self._fault is None:
            return manifest
        return manifest.model_copy(
            update={"params": with_injector(manifest.params, self._fault)}
        )

    def _drive(self, orchestrator: Any, replayer: Tau2Replayer, recorder: Tau2Recorder) -> Any:
        """Fault underneath, recorder and replayer on top of it."""
        with ExitStack() as stack:
            if self._fault is not None:
                self.injector = stack.enter_context(
                    fault_injected(orchestrator.environment, self._fault)
                )
            stack.enter_context(_driving(replayer, orchestrator.environment, recorder))
            return _run(orchestrator)

    def _outcome_of(
        self, simulation: Any, recorder: Tau2Recorder, replayer: Tau2Replayer, parent_id: str
    ) -> Outcome:
        termination = _termination_of(simulation)
        outcome = None
        if termination not in INFRA_TERMINATIONS and simulation.reward_info is not None:
            outcome = recorder.record_outcome(
                reward=simulation.reward_info.reward,
                termination_reason=termination,
                breakdown=simulation.reward_info.model_dump(mode="json"),
            )
        self.result = ReplayResult(
            run_id=self._spec.run_id,
            steps=recorder.next_step_idx,
            outcome=outcome,
            termination_reason=termination,
            tape_llm_calls=replayer.tape_llm_calls,
            live_llm_calls=replayer.live_llm_calls,
            unguarded_llm_calls=replayer.unguarded_llm_calls,
        )
        if outcome is None:
            raise InfraAbortError(
                f"fork {self._spec.run_id!r} of {parent_id!r} ended on {termination!r}; "
                "it has no outcome and must be re-run"
            )
        return outcome
