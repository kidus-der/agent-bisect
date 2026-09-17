"""The tau2 half of the injection pipeline: `bench.inject`'s `InjectRunner`.

Four operations, all of them existing machinery wired together — nothing
about recording, replaying or forking is reimplemented here:

- **record_base** — `adapters.tau2.record_run`, one tau2 task end to end.
- **resample** — a fork at step 0 with `Resample`: the run again, sampled
  fresh, on the same code path the effect estimate uses.
- **tool_steps** — the recorded tool-result steps, each with its payload,
  its blob hash (the oracle fix) and the text of everything that came
  after it (the salience heuristics read it).
- **fault_fork** — a fork at k with `ReplaceToolResult(k, mutated)`: the
  agent is shown a different answer while the database is left exactly as
  the real call left it.

Must be used inside `adapters.tau2.recording_session()`, which installs
the router once for the whole batch; the live completion is read from the
seam at call time rather than captured, so a nested replay patch can
never be mistaken for it.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_bisect.adapters.tau2 import (
    INFRA_TERMINATIONS,
    RecordedRun,
    RunSpec,
    Tau2Recorder,
    build_orchestrator,
    record_run,
    tau2_commit,
)
from agent_bisect.adapters.tau2_batch import BatchItem, free_run_id
from agent_bisect.adapters.tau2_fault_fork import FaultedForkDriver
from agent_bisect.adapters.tau2_fault_injector import FaultSpec, fault_injected
from agent_bisect.adapters.tau2_flaky import FlakyConfig, flaky_world
from agent_bisect.adapters.tau2_replay import Tau2ForkDriver
from agent_bisect.attribution.interventions import (
    ReplaceToolResult,
    Resample,
    shaped_completion,
)
from agent_bisect.bench.inject import BaseRun, RerunResult, ToolStep
from agent_bisect.core.runner import ForkSpec, PrefixMode, run_fork
from agent_bisect.core.store import BlobStore, sha256_hex
from agent_bisect.core.tape import RunManifest, Step, TapeReader, TapeWriter


class BaseRecordingAbortedError(RuntimeError):
    """A base recording ended on infrastructure and has no outcome.

    Raised rather than reported as a failed run: an infra failure scored
    as an agent failure is what `docs/decisions/0004-p0-probe-protocol.md`
    §3 forbids, and the pipeline's retry is the right answer.
    """


@dataclass
class Tau2InjectRunner:
    """`bench.inject.InjectRunner` over real tau2 runs."""

    store: BlobStore
    tape: TapeWriter
    reader: TapeReader
    agent_model: str
    user_model: str
    seed: int = 300
    temperature: float = 0.0
    max_steps: int = 200
    max_errors: int = 10
    #: `snapshot` is Bisect; `rerun_live` is the CAR-style baseline.
    prefix_tools: PrefixMode = "snapshot"
    #: Left unset, the live completion is read off tau2's seam per call.
    live_completion: Callable[..., Any] | None = None
    #: Set to collect in the flaky world (`docs/decisions/0011-flaky-world.md`).
    #: The seed here is a base: each run gets its own, derived from its id
    #: and recorded in its manifest, so a recording is self-consistent
    #: while re-executing the same calls later is not.
    flaky: FlakyConfig | None = None

    # -- recording ---------------------------------------------------------

    def record_base(self, domain: str, task_id: str, trial: int) -> BaseRun:
        item = BatchItem(domain=domain, task_id=task_id, trial=trial)
        run_id = free_run_id(self.reader, item)
        recorded = (
            self._record_flaky(domain, task_id, run_id)
            if self.flaky is not None
            else record_run(
                self._spec(domain, task_id), run_id=run_id, store=self.store, tape=self.tape
            )
        )
        if recorded.outcome is None:
            raise BaseRecordingAbortedError(
                f"{run_id} ended on {recorded.termination_reason}; it has no outcome"
            )
        return BaseRun(
            run_id=run_id,
            domain=domain,
            task_id=task_id,
            passed=recorded.outcome.passed,
            steps=recorded.steps,
        )

    def _record_flaky(self, domain: str, task_id: str, run_id: str) -> Any:
        """`record_run`, with the flaky world installed under the recorder.

        `record_run` builds its own orchestrator, so there is no seam for
        putting the world on the environment before the recorder wraps
        `get_response` — and installed after it, the tape would record the
        deterministic answer while the agent saw the flaky one. The world's
        own seed and its generated-id trail go into the manifest, which is
        what makes the recording explainable and its reward canonicalisable.
        """
        from tau2.evaluator.evaluator import EvaluationType
        from tau2.runner.simulation import run_simulation

        spec = self._spec(domain, task_id)
        config = self._flaky_for(run_id)
        orchestrator = build_orchestrator(spec, run_id)
        recorder = Tau2Recorder(run_id, self.store, self.tape, orchestrator.environment)
        with flaky_world(orchestrator.environment, config) as world:
            recorder.start(self._flaky_manifest(spec, run_id, config))
            with recorder.bind(orchestrator.environment):
                simulation = run_simulation(orchestrator, evaluation_type=EvaluationType.ALL)
            termination = str(
                getattr(simulation.termination_reason, "value", simulation.termination_reason)
            )
            outcome = None
            if termination not in INFRA_TERMINATIONS and simulation.reward_info is not None:
                outcome = recorder.record_outcome(
                    reward=simulation.reward_info.reward,
                    termination_reason=termination,
                    breakdown={
                        **simulation.reward_info.model_dump(mode="json"),
                        "flaky": world.manifest(),
                    },
                )
        return RecordedRun(
            run_id=run_id,
            steps=recorder.next_step_idx,
            outcome=outcome,
            termination_reason=termination,
            llm_calls_by_actor=recorder.llm_calls_by_actor,
        )

    def _flaky_for(self, run_id: str) -> FlakyConfig:
        """This run's own flaky world: same settings, its own RNG."""
        assert self.flaky is not None
        seed = int(sha256_hex(f"{self.flaky.seed}:{run_id}".encode())[:8], 16)
        return FlakyConfig(**{**self.flaky.as_dict(), "seed": seed})

    def _flaky_manifest(self, spec: RunSpec, run_id: str, config: FlakyConfig) -> RunManifest:
        return RunManifest(
            run_id=run_id,
            domain=spec.domain,
            task_id=spec.task_id,
            agent_model=spec.agent_model,
            user_model=spec.user_model,
            params={**spec.manifest_params, "flaky": config.as_dict()},
            seed=spec.seed,
            tau2_commit=tau2_commit(),
            created_at=datetime.now(UTC),
        )

    def _spec(self, domain: str, task_id: str) -> RunSpec:
        return RunSpec(
            domain=domain,
            task_id=task_id,
            agent_model=self.agent_model,
            user_model=self.user_model,
            seed=self.seed,
            temperature=self.temperature,
            max_steps=self.max_steps,
            max_errors=self.max_errors,
        )

    # -- reading the tape --------------------------------------------------

    def tool_steps(self, base_run_id: str) -> list[ToolStep]:
        """Every tool-result step of the run, with what followed it."""
        steps = self.reader.get_steps(base_run_id)
        texts = [self._text_of(step) for step in steps]
        found: list[ToolStep] = []
        for index, step in enumerate(steps):
            if step.actor != "tool" or step.tool_result_ref is None:
                continue
            found.append(
                ToolStep(
                    step_idx=step.step_idx,
                    tool_name=step.tool_name or "",
                    tool_args=dict(step.tool_args or {}),
                    result=self.store.get_json(step.tool_result_ref),
                    result_ref=step.tool_result_ref,
                    downstream="\n".join(texts[index + 1 :]),
                )
            )
        return found

    def _text_of(self, step: Step) -> str:
        """One step as plain text, for "was this value used later?".

        A later call's *arguments* are the strongest evidence that a value
        was read — the agent quoting a reservation id back into the next
        tool call — so they count as much as anything it said. Best effort
        by design: a blob that cannot be read makes the salience heuristic
        slightly worse, never the pipeline wrong.
        """
        parts = [json.dumps(dict(step.tool_args))] if step.tool_args else []
        ref = step.tool_result_ref or step.response_ref
        if ref is not None:
            with contextlib.suppress(OSError, ValueError):
                parts.append(_plain_text(self.store.get_json(ref)))
        return "\n".join(part for part in parts if part)

    # -- forking -----------------------------------------------------------

    def resample(self, base_run_id: str, *, run_id: str, seed: int) -> RerunResult:
        """The whole run again, sampled fresh: the stability check."""
        return self._fork(base_run_id, run_id=run_id, fork_step=0,
                          intervention=Resample(step=0), seed=seed)

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
    ) -> RerunResult:
        """Fork at k with the fault standing in the world; the DB is untouched.

        The intervention still replaces the result *at* k, because a
        snapshot prefix serves the recorded result there and never
        executes the tool. The injector covers everything the
        intervention cannot: later repeats of the same call, and any fork
        of this item taken before k
        (`docs/decisions/0016-persistent-planted-fault.md`).
        """
        return self._fork(
            base_run_id,
            run_id=run_id,
            fork_step=step_idx,
            intervention=ReplaceToolResult(step=step_idx, new_result=dict(faulted_result)),
            seed=seed,
            fault=FaultSpec.from_mutation(
                tool_name=tool_name, tool_args=tool_args, mutated=faulted_result,
                step_idx=step_idx, fault_type=fault_type,
            ),
        )

    def _fork(
        self,
        base_run_id: str,
        *,
        run_id: str,
        fork_step: int,
        intervention: Any,
        seed: int,
        fault: FaultSpec | None = None,
    ) -> RerunResult:
        # The fork keeps its parent's run seed, and `seed` does not reach
        # the model. tau2 puts the run seed into every model request, so:
        # re-pinning it would change the hash-checked *prefix* and the
        # re-run would die of a divergence that says nothing about the
        # intervention; injecting it into the live suffix only would make
        # the forked recording unreplayable, because its prefix rows and
        # its suffix rows would then want two different orchestrator
        # seeds. Both were tried. Re-run variation therefore comes from
        # the provider, which is not deterministic even at temperature 0,
        # and `seed` is kept on the record so each re-run is identifiable.
        # Carrying a per-fork suffix seed needs the replay engine to
        # record it on the fork manifest and re-apply it from the fork
        # step onward -- an additive change in core/runner.fork_manifest
        # and adapters/tau2_replay, owned elsewhere.
        spec = ForkSpec(
            parent_run_id=base_run_id,
            run_id=run_id,
            fork_step=fork_step,
            prefix_tools=self.prefix_tools,
            seed=None,
        )
        reference = self.store.put_json(intervention.to_ref())
        if self.flaky is not None:
            return self._flaky_fork(spec, intervention, reference, run_id, fault)
        driver = FaultedForkDriver(
            spec,
            store=self.store,
            reader=self.reader,
            tape=self.tape,
            live_completion=shaped_completion(intervention, self._live()),
            fault=fault,
        )
        outcome = run_fork(driver, spec, intervention)
        return RerunResult(run_id=run_id, passed=outcome.passed, intervention_ref=reference)

    def _flaky_fork(
        self,
        spec: ForkSpec,
        intervention: Any,
        reference: str,
        run_id: str,
        fault: FaultSpec | None,
    ) -> RerunResult:
        """A fork whose world is flaky as well as faulted.

        Both layers go on through the one `environment_hook`, in order:
        the world first, the faulty tool on top of it, then the recorder
        and the replayer outside both.
        """
        config = self._flaky_for(run_id)

        @contextmanager
        def hook(environment: Any) -> Iterator[None]:
            with ExitStack() as stack:
                stack.enter_context(flaky_world(environment, config))
                if fault is not None:
                    stack.enter_context(fault_injected(environment, fault))
                yield

        driver = Tau2ForkDriver(
            spec,
            store=self.store,
            reader=self.reader,
            tape=self.tape,
            live_completion=shaped_completion(intervention, self._live()),
            environment_hook=hook,
        )
        outcome = run_fork(driver, spec, intervention)
        return RerunResult(run_id=run_id, passed=outcome.passed, intervention_ref=reference)

    def _live(self) -> Callable[..., Any]:
        if self.live_completion is not None:
            return self.live_completion
        import tau2.utils.llm_utils as llm_utils

        return llm_utils.completion


def _plain_text(payload: Any) -> str:
    """The human-readable text inside a recorded payload."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        if "content" in payload and isinstance(payload["content"], str):
            return payload["content"]
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                return str(message.get("content") or "")
    return ""
