"""The five P5 methods, run over one item from one judge output.

Fixed in `docs/decisions/0001-preregistration.md` before any measurement:

- `bisect` — all-at-once top m, confirmed by forking on snapshots against a
  shared control, blaming the earliest step whose boundary clears delta.
- `judge_all_at_once` — no confirmation: the judge's own answer.
- `judge_step_by_step` — no confirmation: the first step it says "yes" at.
- `rerun_live` — the same search, but the forks re-execute the prefix's
  tools instead of restoring a snapshot and serve the recorded model
  replies **positionally** (CAR-style, no snapshots).
- `no_control` — the same search, but effect := treated pass rate, with no
  control arm at all.

**One judge output per item, shared by every method that uses one.** The
comparison is between *confirmation procedures*; letting each method draw
its own shortlist would make the difference partly judge noise. That is
why `evaluate_item` takes an `ItemJudgement` rather than a backend, and
why the two judge-only baselines report the very verdicts the replay
methods were handed.

The judge cost is attributed to **every** method that used that verdict,
not divided among them. A user running only Bisect pays the whole
all-at-once call; that is what "cost per diagnosis" means here.

`rerun_live` is the baseline whose weakness the flaky-world ablation
exists to expose, and the weakness is switched on explicitly: its forks
carry `prefix_tools="rerun_live"` and `unsafe_positional=True`. See
`core/replay.TapeLLM` — nothing selects that mode as a fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from agent_bisect.attribution.estimate import ControlMode, SequentialConfig
from agent_bisect.attribution.judge import (
    DEFAULT_CONFIG as DEFAULT_JUDGE_CONFIG,
)
from agent_bisect.attribution.judge import (
    JudgeBackend,
    JudgeConfig,
    judge_all_at_once,
    judge_step_by_step,
)
from agent_bisect.attribution.judge_view import JudgeInput, JudgeVerdict
from agent_bisect.attribution.search import (
    BlameConfig,
    BlameResult,
    ForkExecutor,
    TruthFor,
    run_blame,
)
from agent_bisect.core.tape import Step

#: Every method P5 reports. Mirrors `server.schemas_benchmark.Method`.
EvalMethod = Literal[
    "bisect", "judge_all_at_once", "judge_step_by_step", "rerun_live", "no_control"
]
EVAL_METHODS: tuple[EvalMethod, ...] = (
    "bisect",
    "judge_all_at_once",
    "judge_step_by_step",
    "rerun_live",
    "no_control",
)
#: The methods that buy re-runs, and the `search.Method` each maps to.
REPLAY_METHODS: tuple[EvalMethod, ...] = ("bisect", "rerun_live", "no_control")


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    """What every method shares, and the two knobs that differ between them."""

    top_m: int = 3
    sequential: SequentialConfig = field(default_factory=SequentialConfig)
    judge: JudgeConfig = DEFAULT_JUDGE_CONFIG
    methods: tuple[EvalMethod, ...] = EVAL_METHODS
    #: How the control arm is drawn for the two methods that have one.
    #: `shared` is the pre-registered default; `per_step` is the ablation
    #: decision 0005 exists to check, and on a planted-fault dataset it is
    #: not merely cheaper-or-dearer but a different quantity -- see
    #: `docs/findings/p5-control-fork.md`.
    control_mode: ControlMode = "shared"

    def blame_config(self, method: EvalMethod) -> BlameConfig:
        """The one config difference that defines each replay method."""
        if method == "bisect":
            return BlameConfig(
                top_m=self.top_m, sequential=self.sequential,
                control_mode=self.control_mode, prefix_tools="snapshot", method="bisect",
            )
        if method == "rerun_live":
            return BlameConfig(
                top_m=self.top_m, sequential=self.sequential,
                control_mode=self.control_mode,
                prefix_tools="rerun_live", unsafe_positional=True, method="rerun_live",
            )
        if method == "no_control":
            return BlameConfig(
                top_m=self.top_m, sequential=self.sequential,
                control_mode="none", prefix_tools="snapshot", method="no_control",
            )
        raise ValueError(f"{method!r} buys no re-runs; it has no blame config")


@dataclass(frozen=True, slots=True)
class ItemJudgement:
    """One item's judge output, shared by every method that uses one.

    `step_by_step` is `None` when that protocol was not run (it costs one
    call per step). The step-by-step baseline then reports a non-answer,
    which scores as wrong — never as a skipped item.
    """

    all_at_once: JudgeVerdict
    step_by_step: JudgeVerdict | None = None


@dataclass(frozen=True, slots=True)
class MethodOutcome:
    """What one method answered for one item, and what it cost."""

    item_id: str
    run_id: str
    method: EvalMethod
    predicted_step: int | None
    #: The judge's ranked suspects, for recall@m. Empty for a method that
    #: produces no ranking of its own.
    ranking: tuple[int, ...]
    shortlist: tuple[int, ...]
    judge_calls: int
    replay_calls: int
    reruns: int
    control_reruns: int
    parse_failed: bool
    note: str = ""
    blame: BlameResult | None = None

    @property
    def total_calls(self) -> int:
        return self.judge_calls + self.replay_calls


def judge_item(
    judge_input: JudgeInput,
    backend: JudgeBackend,
    config: JudgeConfig = DEFAULT_JUDGE_CONFIG,
    *,
    step_by_step: bool = True,
) -> ItemJudgement:
    """Ask both protocols once. Calls the backend, which caches per prompt."""
    return ItemJudgement(
        all_at_once=judge_all_at_once(judge_input, backend, config),
        step_by_step=(
            judge_step_by_step(judge_input, backend, config) if step_by_step else None
        ),
    )


def _judge_only(
    item_id: str, run_id: str, method: EvalMethod, verdict: JudgeVerdict | None
) -> MethodOutcome:
    if verdict is None:
        return MethodOutcome(
            item_id=item_id, run_id=run_id, method=method, predicted_step=None,
            ranking=(), shortlist=(), judge_calls=0, replay_calls=0, reruns=0,
            control_reruns=0, parse_failed=False,
            note="this protocol was not run for this item",
        )
    return MethodOutcome(
        item_id=item_id,
        run_id=run_id,
        method=method,
        predicted_step=verdict.decisive_step,
        ranking=tuple(entry.step for entry in verdict.ranking),
        shortlist=(),
        judge_calls=verdict.calls,
        replay_calls=0,
        reruns=0,
        control_reruns=0,
        parse_failed=verdict.parse_failed,
        note=verdict.failure_reason or "",
    )


def _from_blame(result: BlameResult, method: EvalMethod) -> MethodOutcome:
    control_reruns = 0 if result.estimate is None else result.estimate.control_reruns
    return MethodOutcome(
        item_id=result.item_id,
        run_id=result.run_id,
        method=method,
        predicted_step=result.blamed_step,
        ranking=tuple(entry.step for entry in result.judge.ranking),
        shortlist=result.shortlist,
        judge_calls=result.judge_calls,
        replay_calls=result.replay_calls,
        reruns=len(result.reruns),
        control_reruns=control_reruns,
        parse_failed=result.judge.parse_failed,
        note="; ".join(result.untestable),
        blame=result,
    )


def evaluate_item(
    *,
    item_id: str,
    run_id: str,
    steps: Sequence[Step],
    judgement: ItemJudgement,
    executor: ForkExecutor,
    config: BaselineConfig,
    seed: int,
    truth_for: TruthFor | None = None,
) -> tuple[MethodOutcome, ...]:
    """Run every configured method over one item, from one judge output."""
    outcomes: list[MethodOutcome] = []
    for method in config.methods:
        if method == "judge_all_at_once":
            outcomes.append(_judge_only(item_id, run_id, method, judgement.all_at_once))
        elif method == "judge_step_by_step":
            outcomes.append(_judge_only(item_id, run_id, method, judgement.step_by_step))
        else:
            result = run_blame(
                item_id=item_id,
                run_id=run_id,
                steps=steps,
                verdict=judgement.all_at_once,
                executor=executor,
                config=config.blame_config(method),
                seed=seed,
                truth_for=truth_for,
            )
            outcomes.append(_from_blame(result, method))
    return tuple(outcomes)
