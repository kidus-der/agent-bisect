"""What the judge is allowed to see, and what it is asked to return.

The containment rule of P5 lives here rather than in a comment: a
`JudgeInput` carries only what a real user of the tool would have in front
of them — the failed run's trajectory and the task description and policy
the agent itself was given. There is deliberately no field for the planted
step, the fault type, the base run, the oracle fix, or the reward
breakdown, so a prompt cannot accidentally leak a label that the type does
not carry.

Step indices are the tape's own `Step.step_idx`, unchanged, so a judge's
answer is directly comparable with a planted label and with the step the
estimator blames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agent_bisect.core.tape import Actor

#: The two Who&When protocols implemented in `attribution/judge.py`.
Protocol = Literal["all_at_once", "step_by_step"]

#: Actors that can be a causal step of the trajectory. tau2's NL-assertion
#: evaluator runs *after* the loop and scores it, so it can neither be
#: blamed nor intervened on (`docs/decisions/0013-suspect-interventions.md`).
CANDIDATE_ACTORS: frozenset[str] = frozenset({"agent", "user", "tool"})


@dataclass(frozen=True, slots=True)
class JudgeStepView:
    """One step as the judge sees it: who acted, what they did, what came back."""

    step_idx: int
    actor: Actor
    tool_name: str | None
    tool_args: dict[str, Any] | None
    content: str

    @property
    def is_candidate(self) -> bool:
        return self.actor in CANDIDATE_ACTORS


@dataclass(frozen=True, slots=True)
class JudgeInput:
    """One failed run, as the judge sees it. No label, ever."""

    item_id: str
    run_id: str
    domain: str
    task_description: str
    policy: str
    steps: tuple[JudgeStepView, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError(f"item {self.item_id!r} has no steps to judge")
        indices = [step.step_idx for step in self.steps]
        if indices != sorted(indices):
            raise ValueError(f"item {self.item_id!r}: steps must be in tape order")
        if len(set(indices)) != len(indices):
            raise ValueError(f"item {self.item_id!r}: duplicate step_idx in the trajectory")

    @property
    def candidate_steps(self) -> tuple[int, ...]:
        """Every step the judge may name, in tape order."""
        return tuple(step.step_idx for step in self.steps if step.is_candidate)


@dataclass(frozen=True, slots=True)
class RankedStep:
    """One entry of the judge's ranking. `rank` is 1-based; `score` is its confidence."""

    step: int
    rank: int
    score: float
    rationale: str


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """One protocol's answer for one item, including the ways it can fail.

    A `parse_failed` verdict is a *recorded wrong answer*, not a dropped
    item: `decisive_step` is `None`, the ranking is empty, and the calls it
    cost are still counted. Nothing in the evaluation may skip it.
    """

    item_id: str
    protocol: Protocol
    decisive_step: int | None
    ranking: tuple[RankedStep, ...]
    rationale: str
    calls: int
    steps_examined: int = 0
    parse_failed: bool = False
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.parse_failed and self.decisive_step is not None:
            raise ValueError("a parse failure cannot also name a decisive step")
        ranks = [entry.rank for entry in self.ranking]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(f"ranking must be 1..n in order, got {ranks}")

    def shortlist(self, top_m: int) -> tuple[int, ...]:
        """The first `top_m` distinct steps of the ranking, best first."""
        if top_m <= 0:
            raise ValueError(f"top_m must be positive, got {top_m}")
        return tuple(entry.step for entry in self.ranking[:top_m])

    def rank_of(self, step: int) -> int | None:
        """Where `step` sits in the ranking, or `None` if it is absent."""
        for entry in self.ranking:
            if entry.step == step:
                return entry.rank
        return None
