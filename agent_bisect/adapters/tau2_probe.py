"""Per-task probe accounting and the three selection rules of `docs/decisions/0004`.

`ProbeCollector` is fed by the `on_call` hook of
`agent_bisect.adapters.tau2_llm.route_tau2_llm`: one instance per τ² task,
tallying that task's agent/user calls, tool calls and their validity
(0004 §2). `summarise_probe` pools those per-task rows into one model's
figures, and `choose_agent` / `choose_judge` / `user_sim_is_usable` apply
the pre-registered rules mechanically — they are pure functions over
already-measured numbers, so the decision can be re-derived from the
checkpoints alone and never depends on the order results arrived in.

`choose_agent` returning `(None, reason)` is a real outcome, not an error
path: if no candidate satisfies both pre-registered conditions the gate
stays FAILED with the numbers, and nothing is relaxed to manufacture a
pass.

Note on the import of `attribution.estimate.wilson_interval`: the
architectural wall in the brief is "`core/` never imports
`attribution/`"; `adapters/` is outside it, and re-deriving a Wilson
interval here would only be duplication.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from agent_bisect.adapters.tau2_llm import CallMeta, ToolValidator, classify_tool_calls
from agent_bisect.attribution.estimate import wilson_interval

MIN_VALID_TOOL_CALL_RATE = 0.95
AGENT_PASS_WINDOW = (0.35, 0.75)
AGENT_TARGET_PASS_RATE = 0.55
JUDGE_LATENCY_BUDGET_S = 30.0
#: Pass rates are k/20, so equidistance from the target is exact in principle but
#: not in binary floating point (|0.50-0.55| != |0.60-0.55| by ~1e-17). Without a
#: tolerance the pre-registered tie-break would be unreachable dead code.
DISTANCE_TOLERANCE = 1e-9
MAX_STEPS_TERMINATION = "max_steps"
UNPARSEABLE = "unparseable_response"


@dataclass(frozen=True)
class TaskProbeResult:
    """One (model, task) checkpoint row. Immutable; build a new one to change a field."""

    model: str
    task_id: str
    reward: float | None
    passed: bool
    #: τ² messages in the finished conversation (`len(simulation.messages)`),
    #: which is what "steps" means for a half-duplex τ² run: one message per
    #: turn taken by the agent, the user or a tool.
    n_steps: int
    n_agent_calls: int
    n_user_calls: int
    n_agent_tool_calls: int
    n_invalid_tool_calls: int
    invalid_reasons: tuple[str, ...]
    termination_reason: str
    calls_used: int
    wall_time_s: float
    seed: int
    mean_agent_latency_ms: float = 0.0
    n_empty_user_messages: int = 0
    error: str | None = None


def _choices_of(response: Any) -> Any:
    if isinstance(response, dict):
        return response.get("choices")
    return getattr(response, "choices", None)


def _message_of(response: Any) -> Any:
    choices = _choices_of(response)
    if not choices:
        return None
    first = choices[0]
    return first.get("message") if isinstance(first, dict) else getattr(first, "message", None)


def _content_and_tool_calls(message: Any) -> tuple[str, Any]:
    if isinstance(message, dict):
        return message.get("content") or "", message.get("tool_calls")
    return getattr(message, "content", "") or "", getattr(message, "tool_calls", None)


class ProbeCollector:
    """Accumulates one τ² task's call statistics. One instance per task, per thread."""

    def __init__(self, known_tool_names: set[str], validate: ToolValidator) -> None:
        self._known = known_tool_names
        self._validate = validate
        self.n_agent_calls = 0
        self.n_user_calls = 0
        self.n_tool_calls = 0
        self.n_invalid_tool_calls = 0
        self.n_empty_user_messages = 0
        self.calls_used = 0
        self._reasons: list[str] = []
        self._agent_latencies: list[float] = []

    @property
    def invalid_reasons(self) -> tuple[str, ...]:
        return tuple(self._reasons)

    @property
    def mean_agent_latency_ms(self) -> float:
        return mean(self._agent_latencies) if self._agent_latencies else 0.0

    def record(self, request: dict, response: Any, meta: CallMeta) -> None:
        """The `on_call` hook: every network attempt this call made is already counted."""
        self.calls_used += meta.attempts
        message = _message_of(response)
        if meta.purpose == "user":
            self._record_user(message)
            return
        if meta.purpose != "agent":
            return
        self.n_agent_calls += 1
        self._agent_latencies.append(meta.latency_ms)
        if message is None:
            self.n_tool_calls += 1
            self.n_invalid_tool_calls += 1
            self._reasons.append(UNPARSEABLE)
            return
        content, tool_calls = _content_and_tool_calls(message)
        stats = classify_tool_calls(tool_calls, content, self._known, self._validate)
        self.n_tool_calls += stats.total
        self.n_invalid_tool_calls += stats.total - stats.valid
        self._reasons.extend(stats.reasons)

    def _record_user(self, message: Any) -> None:
        self.n_user_calls += 1
        if message is None:
            self.n_empty_user_messages += 1
            return
        content, _ = _content_and_tool_calls(message)
        if not content.strip():
            self.n_empty_user_messages += 1


@dataclass(frozen=True)
class ModelProbeSummary:
    """One model's pooled 20-task figures. `n_tasks` is always the asked-for count."""

    model: str
    n_tasks: int
    n_completed: int
    n_passed: int
    pass_rate: float
    ci_low: float
    ci_high: float
    valid_tool_call_rate: float | None
    n_tool_calls: int
    n_invalid_tool_calls: int
    invalid_reasons: tuple[str, ...]
    mean_steps: float
    mean_calls_per_task: float
    mean_agent_latency_ms: float
    termination_counts: dict[str, int] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.n_completed == self.n_tasks

    @property
    def meets_tool_call_floor(self) -> bool:
        rate = self.valid_tool_call_rate
        return rate is not None and rate >= MIN_VALID_TOOL_CALL_RATE

    @property
    def in_pass_window(self) -> bool:
        low, high = AGENT_PASS_WINDOW
        return low <= self.pass_rate <= high


def summarise_probe(
    model: str, results: list[TaskProbeResult], *, n_tasks: int
) -> ModelProbeSummary:
    """Pool per-task rows into one model's figures. Missing tasks stay in the denominator."""
    if n_tasks <= 0:
        raise ValueError(f"n_tasks must be positive, got {n_tasks}")
    n_passed = sum(1 for r in results if r.passed)
    tool_calls = sum(r.n_agent_tool_calls for r in results)
    invalid = sum(r.n_invalid_tool_calls for r in results)
    interval = wilson_interval(n_passed, n_tasks)
    return ModelProbeSummary(
        model=model,
        n_tasks=n_tasks,
        n_completed=len(results),
        n_passed=n_passed,
        pass_rate=n_passed / n_tasks,
        ci_low=interval.low,
        ci_high=interval.high,
        valid_tool_call_rate=None if tool_calls == 0 else (tool_calls - invalid) / tool_calls,
        n_tool_calls=tool_calls,
        n_invalid_tool_calls=invalid,
        invalid_reasons=tuple(reason for r in results for reason in r.invalid_reasons),
        mean_steps=mean([r.n_steps for r in results]) if results else 0.0,
        mean_calls_per_task=mean([r.calls_used for r in results]) if results else 0.0,
        mean_agent_latency_ms=(
            mean([r.mean_agent_latency_ms for r in results]) if results else 0.0
        ),
        termination_counts=dict(Counter(r.termination_reason for r in results)),
    )


def _ineligibility(summary: ModelProbeSummary) -> str | None:
    if not summary.meets_tool_call_floor:
        rate = summary.valid_tool_call_rate
        shown = "no tool call emitted" if rate is None else f"{rate:.3f}"
        return f"{summary.model}: valid tool call rate {shown} < {MIN_VALID_TOOL_CALL_RATE}"
    if not summary.in_pass_window:
        low, high = AGENT_PASS_WINDOW
        return f"{summary.model}: pass rate {summary.pass_rate:.2f} outside [{low}, {high}]"
    return None


def choose_agent(
    summaries: list[ModelProbeSummary],
    measured_rpm: dict[str, float],
    order: list[str],
) -> tuple[str | None, str]:
    """0004 §4.3, applied mechanically. `(None, reason)` when nothing qualifies."""
    rejected = [note for note in (_ineligibility(s) for s in summaries) if note]
    eligible = [s for s in summaries if _ineligibility(s) is None]
    if not eligible:
        return None, "no candidate satisfies both conditions — " + "; ".join(rejected)

    def distance(summary: ModelProbeSummary) -> float:
        return abs(summary.pass_rate - AGENT_TARGET_PASS_RATE)

    best_distance = min(distance(s) for s in eligible)
    closest = [
        s for s in eligible
        if math.isclose(distance(s), best_distance, abs_tol=DISTANCE_TOLERANCE)
    ]
    if len(closest) == 1:
        chosen = closest[0]
        return chosen.model, (
            f"pass rate {chosen.pass_rate:.2f} is closest to {AGENT_TARGET_PASS_RATE} "
            f"among candidates meeting the {MIN_VALID_TOOL_CALL_RATE} tool-call floor"
        )
    return _break_tie(closest, measured_rpm, order, best_distance)


def _break_tie(
    closest: list[ModelProbeSummary],
    measured_rpm: dict[str, float],
    order: list[str],
    best_distance: float,
) -> tuple[str, str]:
    """Ties on distance go to the higher measured rpm, then to candidate list order."""
    rates = {s.model: measured_rpm.get(s.model, 0.0) for s in closest}
    best_rpm = max(rates.values())
    fastest = [model for model, rpm in rates.items() if rpm == best_rpm]
    tie = (
        f"tied at distance {best_distance:.2f} from {AGENT_TARGET_PASS_RATE} "
        f"({', '.join(sorted(rates))})"
    )
    if len(fastest) == 1:
        return fastest[0], f"{tie}; broken by the higher measured rpm ({best_rpm:g})"
    by_order = min(fastest, key=order.index)
    return by_order, f"{tie}; rpm tied at {best_rpm:g} too, broken by candidate list order"


def user_sim_is_usable(results: list[TaskProbeResult]) -> tuple[bool, str]:
    """0004 §4.1: keep the first user simulator unless the sanity check trips a rule."""
    if not results:
        return False, "the user-simulator sanity check produced no results"
    if all(r.error for r in results):
        return False, f"errored on every sanity task ({results[0].error})"
    empty = sum(r.n_empty_user_messages for r in results)
    if empty:
        return False, f"returned {empty} empty user message(s)"
    if all(r.termination_reason == MAX_STEPS_TERMINATION for r in results):
        return False, f"never ended a conversation ({MAX_STEPS_TERMINATION} on every task)"
    return True, (
        "clean: no errors, no empty messages, and at least one conversation ended "
        f"({', '.join(r.termination_reason for r in results)})"
    )


def choose_judge(
    median_latency_s: dict[str, float], order: list[str]
) -> tuple[str, str]:
    """0004 §4.2: first in list order within the latency budget, else the faster one."""
    if not order:
        raise ValueError("no judge candidates to choose from")
    for model in order:
        median = median_latency_s.get(model)
        if median is not None and median <= JUDGE_LATENCY_BUDGET_S:
            return model, (
                f"first candidate in list order with median latency {median:.1f}s "
                f"<= {JUDGE_LATENCY_BUDGET_S:g}s"
            )
    fastest = min(order, key=lambda m: median_latency_s.get(m, float("inf")))
    return fastest, (
        f"neither judge met the {JUDGE_LATENCY_BUDGET_S:g}s budget; taking the faster one "
        f"({median_latency_s.get(fastest, float('inf')):.1f}s)"
    )
