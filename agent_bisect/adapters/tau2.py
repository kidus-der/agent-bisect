"""`Tau2Recorder`: run one real tau2 task and write every step to the tape.

Rule 1 of `docs/brief/summary.md` §3 is *record everything, always, before
use*. Two hooks make that literal:

1. **LLM calls** — `adapters.tau2_llm.route_tau2_llm`'s `on_call` hook,
   which the router invokes *before* it returns the response
   (`Tau2Router.completion`). A response this module fails to record is
   therefore never used: the failure comes back as `RecordingError` and
   the call site never sees the reply.
2. **Tool executions** — a wrapper installed on the live
   `Environment.get_response`, the single call site tau2's orchestrator
   uses (`orchestrator.Orchestrator._execute_tool_calls`). It records the
   result, and the world before and after it, before handing the
   `ToolMessage` back.

One tape row per LLM call and per *individual* tool execution, so a
two-tool agent turn writes two rows — a step has to be an interventionable
unit, and `ReplaceToolResult` targets exactly one tool result. See
`docs/decisions/0010-replay-mechanism.md`.

The recorder is bound to the calling thread through a `ContextVar`, so a
batch may enter `route_tau2_llm` **once** (it is only safe entered once,
single-threaded, around the whole run) and still record several concurrent
runs into their own tapes.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_bisect.adapters.tau2_env import DEFAULT_TAU2_DATA_DIR, ensure_tau2_data_dir
from agent_bisect.adapters.tau2_llm import route_tau2_llm
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.config import redact
from agent_bisect.core.llm import RecordingError
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import (
    Actor,
    Outcome,
    RunManifest,
    Step,
    TapeWriter,
    canonical_request_hash,
)

#: Ledger purpose -> tape actor. Anything the router could not attribute to
#: the agent or the user simulator is an evaluator call: on the reward path
#: the only other caller of `llm_utils.completion` is tau2's NL-assertion
#: judge (`evaluator/evaluator_nl_assertions.py`).
_PURPOSE_TO_ACTOR: dict[str, Actor] = {"agent": "agent", "user": "user"}

#: tau2 termination reasons that mean "infrastructure", not "the agent
#: failed". Protocol `docs/decisions/0004-p0-probe-protocol.md` §3: these
#: are re-run, never scored. max_steps, too_many_errors, agent_error and
#: user_error are the agent's doing and count.
INFRA_TERMINATIONS = frozenset({"infrastructure_error"})

#: What the manifest records when the vendored tau2 checkout cannot be
#: interrogated. A gate should refuse a run pinned to this.
UNKNOWN_COMMIT = "unknown"

_active: ContextVar[Tau2Recorder | None] = ContextVar("bisect_active_recorder", default=None)


@lru_cache(maxsize=1)
def tau2_commit(vendor_dir: Path = DEFAULT_TAU2_DATA_DIR.parent) -> str:
    """The commit of the vendored tau2 checkout actually being imported.

    Read from the checkout rather than from a constant, because rule 4
    ("pin what moves") is about recording what ran, not what was meant to.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(vendor_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_COMMIT
    return completed.stdout.strip() or UNKNOWN_COMMIT


@dataclass(frozen=True)
class RunSpec:
    """Everything pinned for one recorded run."""

    domain: str
    task_id: str
    agent_model: str
    user_model: str
    seed: int | None = None
    temperature: float = 0.0
    max_steps: int = 200
    max_errors: int = 10

    @property
    def manifest_params(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "max_steps": self.max_steps,
            "max_errors": self.max_errors,
        }


@dataclass(frozen=True)
class RecordedRun:
    """What one recording produced. `outcome` is `None` for an infra abort."""

    run_id: str
    steps: int
    outcome: Outcome | None
    termination_reason: str
    llm_calls_by_actor: dict[str, int] = field(default_factory=dict)

    @property
    def aborted_infra(self) -> bool:
        return self.outcome is None


def recording_hook(request: dict, response: Any, meta: Any) -> None:
    """`route_tau2_llm`'s `on_call`, routed to the calling thread's recorder.

    Raises rather than dropping the call: a response nobody recorded must
    never be returned to the caller.
    """
    recorder = _active.get()
    if recorder is None:
        raise RecordingError(
            f"an LLM call was made outside any recording session (purpose "
            f"{getattr(meta, 'purpose', '?')!r}); it cannot be recorded, so it is not used"
        )
    recorder.on_llm_call(request, response, meta)


class Tau2Recorder:
    """Writes one run's steps to the tape, each before its result is used."""

    def __init__(
        self,
        run_id: str,
        store: BlobStore,
        tape: TapeWriter,
        environment: Any,
        *,
        parent_run_id: str | None = None,
        fork_step: int | None = None,
        first_step_idx: int = 0,
    ) -> None:
        self._run_id = run_id
        self._store = store
        self._tape = tape
        self._snapshotter = Tau2Snapshotter(environment)
        self._parent_run_id = parent_run_id
        self._fork_step = fork_step
        self._next_idx = first_step_idx
        self._state_ref: str | None = None
        self._state_hash: str | None = None
        self._llm_calls_by_actor: dict[str, int] = {}

    @property
    def next_step_idx(self) -> int:
        """The index the next recorded step will get."""
        return self._next_idx

    @property
    def llm_calls_by_actor(self) -> dict[str, int]:
        return dict(self._llm_calls_by_actor)

    # -- state -------------------------------------------------------------

    def _current_state(self) -> tuple[str, str]:
        """The live world as `(blob ref, domain hash)`, re-captured only on change.

        The hash is cheap next to a full capture, and most steps (every
        LLM call, every read-only tool) leave the world untouched, so this
        turns two full DB dumps per step into one hash.
        """
        live_hash = self._snapshotter.state_hash()
        if live_hash != self._state_hash or self._state_ref is None:
            self._state_ref = self._store.put_json(self._snapshotter.capture())
            self._state_hash = live_hash
        return self._state_ref, live_hash

    # -- steps -------------------------------------------------------------

    def _append(self, step: Step) -> Step:
        try:
            self._tape.append_step(step)
        except Exception as exc:  # noqa: BLE001 - re-raised as RecordingError
            raise RecordingError(
                redact(f"could not record step {step.step_idx} of run {step.run_id}: "
                       f"{type(exc).__name__}: {exc}")
            ) from None
        self._next_idx = step.step_idx + 1
        return step

    def _build(self, actor: Actor, **fields: Any) -> Step:
        before_ref, before_hash = self._state_ref, self._state_hash
        if before_ref is None or before_hash is None:
            before_ref, before_hash = self._current_state()
        after_ref, after_hash = self._current_state()
        return Step(
            run_id=self._run_id,
            step_idx=self._next_idx,
            parent_run_id=self._parent_run_id,
            fork_step=self._fork_step,
            actor=actor,
            state_before=before_ref,
            state_after=after_ref,
            state_hash=after_hash,
            state_hash_before=before_hash,
            **fields,
        )

    def begin_step(self) -> None:
        """Pin the world *entering* the next step.

        Called before the thing being recorded happens, so that a tool
        call's `state_before` is the world it acted on rather than the one
        it left behind.
        """
        self._current_state()

    def on_llm_call(
        self, request: dict, response: Any, meta: Any, *, from_tape: bool = False
    ) -> Step:
        """Record one LLM call. Raises `RecordingError` rather than losing it.

        `from_tape` marks a forked run's prefix step: the payload was read
        from the parent's recording rather than sampled, so no call was
        spent on it. The blobs are content-addressed, so re-storing the
        parent's payload writes nothing new -- the prefix is shared, not
        duplicated.
        """
        actor = _PURPOSE_TO_ACTOR.get(getattr(meta, "purpose", ""), "evaluator")
        try:
            request_ref = self._store.put_json(request)
            response_ref = self._store.put_json(response.to_dict())
            request_hash = canonical_request_hash(request)
        except Exception as exc:  # noqa: BLE001 - re-raised as RecordingError
            raise RecordingError(
                redact(f"could not store the {actor} call of run {self._run_id}: "
                       f"{type(exc).__name__}: {exc}")
            ) from None
        step = self._build(
            actor,
            request_hash=request_hash,
            request_ref=request_ref,
            response_ref=response_ref,
            from_tape=from_tape,
            model=getattr(meta, "model", None),
            params={"purpose": getattr(meta, "purpose", None)},
            latency_ms=int(getattr(meta, "latency_ms", 0) or 0),
            **_token_counts(response),
        )
        self._llm_calls_by_actor[actor] = self._llm_calls_by_actor.get(actor, 0) + 1
        return self._append(step)

    def on_tool_call(
        self, tool_call: Any, tool_message: Any, *, from_tape: bool = False
    ) -> Step:
        """Record one tool execution and the world either side of it."""
        try:
            result_ref = self._store.put_json(tool_message.model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001 - re-raised as RecordingError
            raise RecordingError(
                redact(f"could not store the result of {tool_call.name} in run "
                       f"{self._run_id}: {type(exc).__name__}: {exc}")
            ) from None
        return self._append(
            self._build(
                "tool",
                tool_name=tool_call.name,
                tool_args=dict(tool_call.arguments or {}),
                tool_result_ref=result_ref,
                from_tape=from_tape,
            )
        )

    # -- run lifecycle -----------------------------------------------------

    def start(self, manifest: RunManifest) -> None:
        self._tape.start_run(manifest)

    def record_outcome(self, reward: float, termination_reason: str, breakdown: Any) -> Outcome:
        breakdown_ref = self._store.put_json(breakdown) if breakdown is not None else None
        outcome = Outcome(
            run_id=self._run_id,
            reward=reward,
            breakdown_ref=breakdown_ref,
            termination_reason=termination_reason,
        )
        self._tape.record_outcome(outcome)
        return outcome

    @contextmanager
    def bind(self, environment: Any) -> Iterator[None]:
        """Install the tool hook and make this the calling thread's recorder."""

        def recording_get_response(original: Callable[[Any], Any], tool_call: Any) -> Any:
            self.begin_step()
            tool_message = original(tool_call)
            self.on_tool_call(tool_call, tool_message)
            return tool_message

        with active_recorder(self), wrap_tool_execution(environment, recording_get_response):
            yield


@contextmanager
def active_recorder(recorder: Tau2Recorder) -> Iterator[None]:
    """Make `recorder` the one `recording_hook` routes this thread's calls to.

    Separate from `Tau2Recorder.bind` because the replay engine needs the
    same routing with a *different* tool hook: during a replayed prefix the
    tools are not executed at all.
    """
    token = _active.set(recorder)
    try:
        yield
    finally:
        _active.reset(token)


@contextmanager
def wrap_tool_execution(
    environment: Any, wrapper: Callable[[Callable[[Any], Any], Any], Any]
) -> Iterator[None]:
    """Route `Environment.get_response` through `wrapper(original, tool_call)`.

    That method is the orchestrator's single tool-execution call site
    (`Orchestrator._execute_tool_calls`), so wrapping it on the live
    instance intercepts every tool call without touching tau2's source.
    """
    original = environment.get_response
    environment.get_response = lambda tool_call: wrapper(original, tool_call)
    try:
        yield
    finally:
        environment.get_response = original


def _token_counts(response: Any) -> dict[str, int | None]:
    usage = response.get("usage") if hasattr(response, "get") else None
    if usage is None:
        return {"tokens_in": None, "tokens_out": None}
    return {
        "tokens_in": getattr(usage, "prompt_tokens", None),
        "tokens_out": getattr(usage, "completion_tokens", None),
    }


@contextmanager
def recording_session(
    *,
    ledger: BudgetLedger,
    phase: str,
    completion_fn: Callable[..., Any] | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    limiter_for: Callable[[str], Any] | None = None,
) -> Iterator[Any]:
    """Route every tau2 LLM call through the limiter, ledger and recorder.

    Entered **once**, single-threaded, around a whole batch:
    `route_tau2_llm` installs and removes module-level patches, so nesting
    it or entering it from several threads would race. Which run each call
    belongs to is decided per thread by `Tau2Recorder.bind`.
    """
    ensure_tau2_data_dir()
    with route_tau2_llm(
        ledger=ledger,
        phase=phase,
        on_call=recording_hook,
        completion_fn=completion_fn,
        api_key=api_key,
        api_base=api_base,
        limiter_for=limiter_for,
    ) as router:
        yield router


def build_orchestrator(spec: RunSpec, run_id: str) -> Any:
    """A tau2 orchestrator for `spec`, with every replay hazard pinned.

    `simulation_id` is our run id (tau2 would otherwise mint a uuid4) and
    the wall-clock `timeout` is left at `None`, so only the deterministic
    step budget can end the run
    (`docs/decisions/0010-replay-mechanism.md`).
    """
    ensure_tau2_data_dir()
    from tau2.runner.build import build_text_orchestrator

    task = _find_task(spec.domain, spec.task_id)
    config = _run_config(spec)
    return build_text_orchestrator(config, task, seed=spec.seed, simulation_id=run_id)


def _find_task(domain: str, task_id: str) -> Any:
    from tau2.run import get_tasks

    tasks = get_tasks(task_set_name=domain)
    for task in tasks:
        if task.id == task_id:
            return task
    raise LookupError(f"no task {task_id!r} in domain {domain!r} ({len(tasks)} tasks)")


def _run_config(spec: RunSpec) -> Any:
    from tau2.data_model.simulation import TextRunConfig

    # pyright cannot see tau2's `Annotated[..., Field(default=...)]`
    # defaults and believes every other field is required; they all exist
    # at runtime.
    return TextRunConfig(  # pyright: ignore[reportCallIssue]
        domain=spec.domain,
        agent="llm_agent",
        user="user_simulator",
        llm_agent=spec.agent_model,
        llm_args_agent={"temperature": spec.temperature},
        llm_user=spec.user_model,
        llm_args_user={"temperature": spec.temperature},
        num_trials=1,
        max_steps=spec.max_steps,
        max_errors=spec.max_errors,
        seed=spec.seed if spec.seed is not None else 300,
        log_level="ERROR",
        timeout=None,
    )


def record_run(spec: RunSpec, *, run_id: str, store: BlobStore, tape: TapeWriter) -> RecordedRun:
    """Run one tau2 task end to end, recording every step. Zero calls of its own.

    Must be called inside `recording_session()`; the LLM hook is installed
    there, once, for the whole batch.
    """
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.runner.simulation import run_simulation

    orchestrator = build_orchestrator(spec, run_id)
    recorder = Tau2Recorder(run_id, store, tape, orchestrator.environment)
    recorder.start(
        RunManifest(
            run_id=run_id,
            domain=spec.domain,
            task_id=spec.task_id,
            agent_model=spec.agent_model,
            user_model=spec.user_model,
            params=spec.manifest_params,
            seed=spec.seed,
            tau2_commit=tau2_commit(),
            created_at=datetime.now(UTC),
        )
    )
    with recorder.bind(orchestrator.environment):
        simulation = run_simulation(orchestrator, evaluation_type=EvaluationType.ALL)

    raw_termination = simulation.termination_reason
    termination = str(getattr(raw_termination, "value", raw_termination))
    outcome = None
    if termination not in INFRA_TERMINATIONS and simulation.reward_info is not None:
        outcome = recorder.record_outcome(
            reward=simulation.reward_info.reward,
            termination_reason=termination,
            breakdown=simulation.reward_info.model_dump(mode="json"),
        )
    return RecordedRun(
        run_id=run_id,
        steps=recorder.next_step_idx,
        outcome=outcome,
        termination_reason=termination,
        llm_calls_by_actor=recorder.llm_calls_by_actor,
    )
