"""Replaying and forking a recorded tau2 run.

The mechanism is `docs/decisions/0010-replay-mechanism.md`: re-drive tau2's
**real** orchestrator from step 0 with the tape in charge of the prefix.
Nothing about the run is reconstructed or simulated — the same
`Orchestrator`, the same `Environment`, the same evaluator, the same step
and error budgets — only `llm_utils.completion` and
`Environment.get_response` answer from the recording instead of from the
network and the world.

Three tool modes, because the prefix can be obtained three ways:

- `verify` — execute the tool for real and assert it reproduced the
  recorded result *and* the recorded state hash. Full-run replay uses
  this: it is what proves a recording is faithful.
- `snapshot` — serve the recorded result and restore the world from the
  recorded snapshot, executing nothing. Bisect's fork prefix.
- `rerun_live` — execute the tool for real and restore nothing, letting
  the world drift. The CAR-style baseline of `docs/brief/summary.md` §8.
  The tool *call* is still checked against the recording (it comes from
  the tape, so it must match); only its result is allowed to differ.

There is no fallback: a mismatch raises `DivergenceError` and the run
stops. A live call before the fork step is impossible by construction, and
`replay_run` has no live path at all.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from agent_bisect.adapters.tau2 import (
    INFRA_TERMINATIONS,
    RunSpec,
    Tau2Recorder,
    active_recorder,
    build_orchestrator,
    wrap_tool_execution,
)
from agent_bisect.adapters.tau2_llm import SECRET_KWARGS
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
from agent_bisect.core.replay import (
    LIVE,
    DivergenceError,
    Intervention,
    NoOpIntervention,
    TapeCursor,
    TapeLLM,
    TapeTools,
)
from agent_bisect.core.runner import (
    ForkSpec,
    check_replay_complete,
    check_same_outcome,
    fork_manifest,
)
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step, TapeReader, TapeWriter

#: How the tool executions the tape still governs are obtained.
ToolMode = Literal["verify", "snapshot", "rerun_live"]

#: `replay_run`'s fork step: the tape governs every step, for ever.
REPLAY_EVERYTHING = None


class ForkSeedError(ValueError):
    """A fork asked for a seed its own prefix could not survive.

    tau2 threads the run seed into every model request (`llm_args`), so it
    is part of `canonical_request_hash`: a fork that re-pins the seed
    diverges on its own first prefix step, and one that injects the new
    seed only from the fork step on produces a recording whose prefix and
    suffix want two different orchestrator seeds -- unreplayable either
    way. Resampling at the fork step is what the `Resample` intervention
    is for; it makes a live call instead of changing the seed.
    """


class NoLiveCallError(DivergenceError):
    """A replay tried to make a live call it has no source for.

    A `DivergenceError` subclass so the one thing a caller has to catch
    still covers it — and so it can never be mistaken for a transport
    failure worth retrying.
    """


#: Tape actor -> the ledger purpose the recorder maps back to it. Anything
#: the router could not attribute carries `route_tau2_llm`'s default, so an
#: evaluator call's purpose is "tau2", not "evaluator".
_ACTOR_TO_PURPOSE = {"agent": "agent", "user": "user"}
_DEFAULT_PURPOSE = "tau2"


@dataclass(frozen=True)
class _CallMeta:
    """The shape `Tau2Recorder.on_llm_call` reads off a call's metadata.

    Taken from the recorded step rather than from the replay, so a forked
    run's prefix row comes out byte-identical to its parent's — which is
    what makes the prefix shared rather than duplicated, the blob store
    being content-addressed.
    """

    purpose: str
    model: str | None
    latency_ms: float

    @classmethod
    def of(cls, step: Step) -> _CallMeta:
        params = step.params or {}
        purpose = params.get("purpose") or _ACTOR_TO_PURPOSE.get(step.actor, _DEFAULT_PURPOSE)
        return cls(purpose=purpose, model=step.model, latency_ms=float(step.latency_ms or 0))


def rehydrate_response(payload: Mapping[str, Any]) -> Any:
    """A recorded response payload back into the object tau2 unpacks.

    `tau2.utils.llm_utils.generate` reads `choices[0].finish_reason`,
    `.message.role/.content/.tool_calls`, `response.to_dict()` and
    `response.get("usage")` — all of which a `ModelResponse` rebuilt from
    its own `to_dict()` reproduces exactly (including the provider's `id`
    and `created`, so nothing about the replayed request can differ).
    """
    import litellm

    return litellm.ModelResponse(**dict(payload))


#: Fields tau2 stamps on every message afresh: `timestamp` from the wall
#: clock (`data_model/message.py`) and `turn_idx`, assigned by
#: `Orchestrator.get_trajectory` at the end of the run. They are recorded
#: verbatim but must never be compared -- and must never be *restored*,
#: because the trajectory is sorted by timestamp: a replayed prefix wearing
#: its parent's clock would sort ahead of this run's own opening message
#: and hand the evaluator a reordered conversation.
VOLATILE_MESSAGE_FIELDS = frozenset({"timestamp", "turn_idx"})


def rehydrate_tool_message(payload: Mapping[str, Any]) -> Any:
    """A recorded tool result back into a tau2 `ToolMessage`, stamped now."""
    from tau2.data_model.message import ToolMessage

    return ToolMessage.model_validate(
        {key: value for key, value in payload.items() if key not in VOLATILE_MESSAGE_FIELDS}
    )


def _request_of(model: str, messages: Any, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """The request dict as the recorder saw it, minus what it never stored."""
    return {
        "model": model,
        "messages": messages,
        **{key: value for key, value in kwargs.items() if key not in SECRET_KWARGS},
    }


@dataclass(frozen=True)
class ReplayResult:
    """What one replay or fork produced."""

    run_id: str
    steps: int
    outcome: Outcome | None
    termination_reason: str
    tape_llm_calls: int
    live_llm_calls: int
    #: Prefix responses served to a request the recording does not match.
    #: Always 0 unless the run was driven `unsafe_positional`, and the
    #: measure of how far the re-run-live baseline drifted from its own
    #: recording -- which is the point of that baseline.
    unguarded_llm_calls: int = 0

    @property
    def aborted_infra(self) -> bool:
        return self.outcome is None


class _CountingSink:
    """Stands in for a recorder when a replay writes nothing.

    `replay_run` verifies a recording; writing a second copy of it would
    double the store and put a run on the dashboard that nobody asked for.
    """

    def __init__(self) -> None:
        self.next_step_idx = 0

    def begin_step(self) -> None:
        return None

    def on_llm_call(self, request: dict, response: Any, meta: Any, *, from_tape: bool) -> None:
        self.next_step_idx += 1

    def on_tool_call(self, tool_call: Any, tool_message: Any, *, from_tape: bool) -> None:
        self.next_step_idx += 1


class Tau2Replayer:
    """Drives one replayed or forked run.

    `fork_step` is the first step the tape stops governing *after*: steps
    below it are served from the recording, the step itself is served and
    then passed through the intervention, and everything above it is live.
    `REPLAY_EVERYTHING` means the tape governs to the end.
    """

    def __init__(
        self,
        *,
        environment: Any,
        steps: list[Step],
        store: BlobStore,
        sink: Any,
        fork_step: int | None = REPLAY_EVERYTHING,
        tool_mode: ToolMode = "verify",
        intervention: Intervention | None = None,
        live_completion: Callable[..., Any] | None = None,
        unsafe_positional: bool = False,
    ) -> None:
        self._environment = environment
        self._snapshotter = Tau2Snapshotter(environment)
        self._cursor = TapeCursor(steps)
        # `unsafe_positional` drops ONLY the request-hash guard, and only
        # for the CAR-style re-run-live baseline of P5, whose prefix drifts
        # by construction once a tool answers differently. It is never a
        # fallback: see `core.replay.TapeLLM`.
        self._llm = TapeLLM(
            self._cursor, store.get_json, unsafe_positional=unsafe_positional
        )
        self._tools = TapeTools(
            self._cursor, store.get_json, volatile_fields=VOLATILE_MESSAGE_FIELDS
        )
        self._sink = sink
        self._fork_step = fork_step
        self._tool_mode: ToolMode = tool_mode
        self._intervention = intervention or NoOpIntervention()
        self._live_completion = live_completion
        self._live_llm_calls = 0

    @property
    def cursor(self) -> TapeCursor:
        return self._cursor

    @property
    def tape_llm_calls(self) -> int:
        return self._llm.calls_served

    @property
    def unguarded_llm_calls(self) -> int:
        """Prefix responses served to a request the recording does not match.

        Always 0 unless the replayer was built `unsafe_positional`; the
        measure of how far the re-run-live baseline drifted from its own
        recording.
        """
        return self._llm.unguarded_calls

    @property
    def live_llm_calls(self) -> int:
        return self._live_llm_calls

    @property
    def _step_idx(self) -> int:
        return self._sink.next_step_idx

    def _governed_by_tape(self) -> bool:
        return self._fork_step is None or self._step_idx <= self._fork_step

    def _at_fork(self) -> bool:
        return self._fork_step is not None and self._step_idx == self._fork_step

    # -- the LLM seam ------------------------------------------------------

    def completion(self, *, model: str, messages: Any, **kwargs: Any) -> Any:
        """The stand-in for `litellm.completion` inside `llm_utils`."""
        if not self._governed_by_tape():
            return self._live(model=model, messages=messages, **kwargs)
        request = _request_of(model, messages, kwargs)
        step = self._cursor.peek()
        payload = self._llm.serve(request)
        # `serve` advanced the cursor past `step`, and would have raised
        # `TapeExhaustedError` rather than let `peek` be None.
        assert step is not None
        if self._at_fork():
            payload = self._intervention.apply(step, payload)
            if payload is LIVE:
                return self._live(model=model, messages=messages, **kwargs)
        response = rehydrate_response(payload)
        meta = _CallMeta.of(step)
        # The recorder stores the request verbatim, and the router's copy
        # carried the purpose; putting it back keeps a forked prefix row
        # identical to its parent's. It is not part of the request hash.
        self._sink.on_llm_call({**request, "purpose": meta.purpose}, response, meta, from_tape=True)
        return response

    def _live(self, **payload: Any) -> Any:
        if self._live_completion is None:
            raise NoLiveCallError(
                step_idx=self._step_idx,
                actor="llm",
                expected="a recorded response",
                got="a live call",
                diff="this replay has no live source; a tape that ran out is a divergence",
            )
        self._live_llm_calls += 1
        return self._live_completion(**payload)

    # -- the tool seam -----------------------------------------------------

    def get_response(self, original: Callable[[Any], Any], tool_call: Any) -> Any:
        """The stand-in for `Environment.get_response`."""
        self._sink.begin_step()
        if not self._governed_by_tape():
            tool_message = original(tool_call)
            self._sink.on_tool_call(tool_call, tool_message, from_tape=False)
            return tool_message

        step = self._tools.take(tool_call.name, dict(tool_call.arguments or {}))
        tool_message = self._obtain(step, original, tool_call)
        if self._at_fork():
            payload = self._intervention.apply(step, tool_message.model_dump(mode="json"))
            if payload is LIVE:
                tool_message = original(tool_call)
            elif payload != tool_message.model_dump(mode="json"):
                tool_message = rehydrate_tool_message(payload)
        self._sink.on_tool_call(tool_call, tool_message, from_tape=True)
        return tool_message

    def _obtain(self, step: Step, original: Callable[[Any], Any], tool_call: Any) -> Any:
        if self._tool_mode == "snapshot":
            tool_message = rehydrate_tool_message(self._tools.recorded_result(step))
            self._restore(step)
            return tool_message
        tool_message = original(tool_call)
        if self._tool_mode == "verify":
            self._tools.check_reexecution(
                step, tool_message.model_dump(mode="json"), self._snapshotter.state_hash()
            )
        return tool_message

    def _restore(self, step: Step) -> None:
        """Put the world exactly where the recording left it after `step`."""
        self._snapshotter.restore(self._tools.recorded_state_after(step))
        restored = self._snapshotter.state_hash()
        if restored != step.state_hash:
            raise DivergenceError(
                step_idx=step.step_idx,
                actor="tool",
                expected=step.state_hash,
                got=restored,
                diff=f"state_hash: restoring the recorded snapshot gave {restored}",
            )


#: The replay serving this thread's tau2 calls, if any.
_active_completion: ContextVar[Callable[..., Any] | None] = ContextVar(
    "bisect_replay_completion", default=None
)


class _CompletionDispatcher:
    """One process-wide stand-in for `llm_utils.completion`, shared by threads.

    `llm_utils.completion` is a module attribute, so a replay that serves
    its tape by rebinding it is process-global: two forks in two threads
    overwrite each other, and the one that leaves first restores the
    other's replayer as the global — from then on one fork's tape answers
    the other's requests. `Tau2Recorder` already avoids exactly this with
    a `ContextVar`; this is the same answer for the replay half, which
    matters because P3 runs sixteen forks per dataset item and P5 samples
    N arms per step.

    So the attribute is replaced **once**, by an object that asks a
    `ContextVar` who is serving *this* thread and falls through to
    whatever was installed underneath when nobody is — in production the
    router, so a fork's live suffix keeps the limiter, the ledger and the
    retry policy exactly as before. `ThreadPoolExecutor` gives each worker
    a fresh context, and a tau2 simulation is strictly sequential within
    itself (`docs/decisions/0010-replay-mechanism.md`), so one variable per
    thread is the whole story.

    Installation is refcounted under a lock: the first holder installs and
    the **last** one restores, so a thread finishing early cannot pull the
    dispatcher out from under threads still running.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._depth = 0
        self._fallback: Callable[..., Any] | None = None

    def __call__(self, **kwargs: Any) -> Any:
        completion = _active_completion.get()
        if completion is not None:
            return completion(**kwargs)
        fallback = self._fallback
        if fallback is None:  # pragma: no cover - only if called uninstalled
            raise RuntimeError("the replay dispatcher was called with nothing underneath it")
        return fallback(**kwargs)

    @contextmanager
    def installed(self) -> Iterator[None]:
        import tau2.utils.llm_utils as llm_utils

        with self._lock:
            if self._depth == 0:
                self._fallback = llm_utils.completion
                llm_utils.completion = self
            self._depth += 1
        try:
            yield
        finally:
            with self._lock:
                self._depth -= 1
                if self._depth == 0:
                    llm_utils.completion = self._fallback
                    self._fallback = None


_dispatcher = _CompletionDispatcher()


def _dispatcher_installed() -> AbstractContextManager[None]:
    """Put the shared dispatcher in place for as long as this block runs."""
    return _dispatcher.installed()


@contextmanager
def _completion_patched(completion: Callable[..., Any]) -> Iterator[None]:
    """Serve this thread's tau2 calls from `completion` for the duration.

    Per thread, not per process: see `_CompletionDispatcher`. Nested
    *inside* `route_tau2_llm` when a fork has a live suffix, so the router
    stays underneath and this takes precedence for the prefix.
    """
    token = _active_completion.set(completion)
    try:
        yield
    finally:
        _active_completion.reset(token)


@contextmanager
def _driving(
    replayer: Tau2Replayer, environment: Any, recorder: Tau2Recorder | None
) -> Iterator[None]:
    """Install both seams, plus the recorder this thread's live calls belong to."""
    with ExitStack() as stack:
        if recorder is not None:
            stack.enter_context(active_recorder(recorder))
        stack.enter_context(_dispatcher_installed())
        stack.enter_context(_completion_patched(replayer.completion))
        stack.enter_context(wrap_tool_execution(environment, replayer.get_response))
        yield


def _spec_from(manifest: RunManifest) -> RunSpec:
    params = manifest.params or {}
    return RunSpec(
        domain=manifest.domain,
        task_id=manifest.task_id,
        agent_model=manifest.agent_model,
        user_model=manifest.user_model,
        seed=manifest.seed,
        temperature=params.get("temperature", 0.0),
        max_steps=params.get("max_steps", 200),
        max_errors=params.get("max_errors", 10),
    )


def _run(orchestrator: Any) -> Any:
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.runner.simulation import run_simulation

    return run_simulation(orchestrator, evaluation_type=EvaluationType.ALL)


def _termination_of(simulation: Any) -> str:
    raw = simulation.termination_reason
    return str(getattr(raw, "value", raw))


def replay_run(
    run_id: str,
    *,
    store: BlobStore,
    reader: TapeReader,
    expect_same_outcome: bool = True,
    tool_mode: ToolMode = "verify",
) -> ReplayResult:
    """Re-run a recording end to end from the tape. Zero network calls.

    Every LLM response comes from the recording with its request hash
    checked. `tool_mode` decides the tools: `verify` (the default, and
    what the P2 gate asserts) re-executes each one and requires its
    recorded result and state hash back; `snapshot` serves the recorded
    result and restores the world from the recorded snapshot instead,
    which is what a recording whose tool result was deliberately altered
    needs -- a P3 dataset item's recorded result *is* the planted
    mutation, so re-executing the tool would rightly disagree with it.
    Either way the whole tape must be consumed and the same reward
    reached, or it raises.
    """
    manifest = reader.get_manifest(run_id)
    steps = reader.get_steps(run_id)
    orchestrator = build_orchestrator(_spec_from(manifest), f"{run_id}-replay")
    sink = _CountingSink()
    replayer = Tau2Replayer(
        environment=orchestrator.environment,
        steps=steps,
        store=store,
        sink=sink,
        fork_step=REPLAY_EVERYTHING,
        tool_mode=tool_mode,
    )
    with _driving(replayer, orchestrator.environment, None):
        simulation = _run(orchestrator)

    check_replay_complete(replayer.cursor)
    termination = _termination_of(simulation)
    reward = simulation.reward_info.reward if simulation.reward_info is not None else None
    outcome = None if reward is None else Outcome(run_id=run_id, reward=reward)
    if expect_same_outcome and outcome is not None:
        check_same_outcome(reader.get_outcome(run_id), outcome)
    return ReplayResult(
        run_id=run_id,
        steps=sink.next_step_idx,
        outcome=outcome,
        termination_reason=termination,
        tape_llm_calls=replayer.tape_llm_calls,
        live_llm_calls=replayer.live_llm_calls,
        unguarded_llm_calls=replayer.unguarded_llm_calls,
    )


class Tau2ForkDriver:
    """`core.runner.ForkDriver` over a recorded tau2 run.

    `restore` and `apply` arm the engine — where the tape stops being
    authoritative, and what changes there — and `run_rest` re-drives the
    orchestrator, which is what actually puts the world back
    (`docs/decisions/0010-replay-mechanism.md`).
    """

    def __init__(
        self,
        spec: ForkSpec,
        *,
        store: BlobStore,
        reader: TapeReader,
        tape: TapeWriter,
        live_completion: Callable[..., Any],
        unsafe_positional: bool = False,
        environment_hook: Callable[[Any], AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._spec = spec
        self._store = store
        self._reader = reader
        self._tape = tape
        self._live_completion = live_completion
        self._unsafe_positional = unsafe_positional
        # Entered around the whole run and *before* the recorder and the
        # replayer wrap `get_response`, so a standing component installed
        # on the environment -- a planted fault (decision 0016) -- is what
        # the agent sees AND what the tape records. Installed after those
        # wrappers, the tape would record the true answer while the agent
        # saw the corrupted one.
        self._environment_hook = environment_hook
        self._fork_step = spec.fork_step
        self._intervention: Intervention = NoOpIntervention()
        self.result: ReplayResult | None = None

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
        spec = _spec_from(parent)
        if seed is not None and seed != parent.seed:
            raise ForkSeedError(
                f"fork {self._spec.run_id!r} asked for seed {seed}, but its parent "
                f"{parent.run_id!r} was recorded with seed {parent.seed}; tau2 puts the "
                "seed in every model request, so it is part of the canonical request hash "
                "and the fork would diverge on its own first prefix step"
            )
        orchestrator = build_orchestrator(spec, self._spec.run_id)
        recorder = Tau2Recorder(
            self._spec.run_id,
            self._store,
            self._tape,
            orchestrator.environment,
            parent_run_id=parent.run_id,
            fork_step=self._fork_step,
        )
        recorder.start(
            fork_manifest(
                parent,
                run_id=self._spec.run_id,
                fork_step=self._fork_step,
                created_at=datetime.now(UTC),
                seed=seed,
            )
        )
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
        with ExitStack() as stack:
            if self._environment_hook is not None:
                stack.enter_context(self._environment_hook(orchestrator.environment))
            stack.enter_context(_driving(replayer, orchestrator.environment, recorder))
            simulation = _run(orchestrator)

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
                f"fork {self._spec.run_id!r} of {parent.run_id!r} ended on "
                f"{termination!r}; it has no outcome and must be re-run"
            )
        return outcome


class InfraAbortError(RuntimeError):
    """A run ended on infrastructure, so it has no outcome to report.

    Never a zero reward: an infra failure scored as an agent failure is
    exactly what `docs/decisions/0004-p0-probe-protocol.md` §3 forbids.
    """
