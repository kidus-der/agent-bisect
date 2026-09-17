"""The two Who&When failure-attribution protocols, run over a tau2 trajectory.

Provenance, and which parts are faithful to the published protocol versus
adapted to tau2, is documented in `attribution/judge_prompts.py`. This
module is the control flow: ask, validate, repair once, record a failure.

What the judge sees is a `JudgeInput` and nothing else — the failed run's
trajectory plus the task description and policy the agent itself was
given. Never the planted step, the fault type, the base run, the oracle
fix or the reward breakdown. The type carries no field for any of them.

Failure is a result, not an exception
-------------------------------------
An answer that will not parse gets exactly one repair retry, quoting the
offending output and the validator's complaint back to the judge. A second
failure produces a `JudgeVerdict` with `parse_failed=True`,
`decisive_step=None` and an empty ranking — which `bench/evaluate.py`
scores as a **wrong answer**, with its calls still counted. Nothing is
dropped: an item the judge could not answer is an item the judge got
wrong, and pretending otherwise would flatter every judge baseline.

Deriving a ranking from the step-by-step protocol
-------------------------------------------------
The published step-by-step protocol yields one step (the first "yes"), but
P5 reports recall@m for m = 1..10, which needs an order over suspects. The
derivation, fixed here: a step's **suspicion** is the judge's confidence if
it said "yes" and `1 - confidence` if it said "no" (a hesitant "no" is a
weak suspicion; a firm one is none), the "yes" step is forced to rank 1,
and ties break on the earlier step index so the ranking is deterministic.
Steps the walk never reached are unranked — which caps the protocol's
recall@m by construction, and is a property of the protocol, not of this
implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol as TypingProtocol

from agent_bisect.attribution.judge_parse import (
    JudgeParseError,
    parse_all_at_once,
    parse_step_by_step,
)
from agent_bisect.attribution.judge_prompts import (
    RANKING_LIMIT,
    TruncationPolicy,
    build_all_at_once_prompt,
    build_step_by_step_prompt,
)
from agent_bisect.attribution.judge_store import JudgeCall
from agent_bisect.attribution.judge_view import (
    JudgeInput,
    JudgeVerdict,
    Protocol,
    RankedStep,
)

#: A run longer than this stops the step-by-step walk. tau2 airline and
#: retail runs are far shorter, so it never binds in P5; it exists so a
#: pathological trajectory cannot silently spend an unbounded budget. When
#: it does bind it is recorded in `failure_reason`, never hidden.
DEFAULT_MAX_STEPS_EXAMINED = 80

REPAIR_INSTRUCTION = """\

---

Your previous answer could not be used.

What you sent:
{answer}

Why it was rejected: {problem}

Send the JSON object again, correctly this time. One JSON object, nothing else.
"""


@dataclass(frozen=True, slots=True)
class JudgeConfig:
    """Everything the protocols may vary. Immutable; build a new one to change it."""

    truncation: TruncationPolicy = field(default_factory=TruncationPolicy)
    ranking_limit: int = RANKING_LIMIT
    max_steps_examined: int = DEFAULT_MAX_STEPS_EXAMINED

    def __post_init__(self) -> None:
        if self.ranking_limit <= 0:
            raise ValueError(f"ranking_limit must be positive, got {self.ranking_limit}")
        if self.max_steps_examined <= 0:
            raise ValueError(
                f"max_steps_examined must be positive, got {self.max_steps_examined}"
            )


DEFAULT_CONFIG = JudgeConfig()


class JudgeBackend(TypingProtocol):
    """Whatever actually asks the model. `LedgeredJudgeBackend` in production."""

    model: str

    def ask(
        self, *, system: str, user: str, item_id: str, protocol: Protocol
    ) -> JudgeCall: ...


@dataclass(frozen=True, slots=True)
class _Attempt[Parsed]:
    """One ask-and-validate round: what came back, and what went wrong with it."""

    parsed: Parsed | None
    calls: int
    problem: str | None
    raw: str


def _ask_once[Parsed](
    backend: JudgeBackend,
    *,
    system: str,
    user: str,
    item_id: str,
    protocol: Protocol,
    validate: Callable[[str], Parsed],
) -> _Attempt[Parsed]:
    answer = backend.ask(system=system, user=user, item_id=item_id, protocol=protocol)
    try:
        return _Attempt(validate(answer.content), 1, None, answer.content)
    except JudgeParseError as exc:
        return _Attempt(None, 1, str(exc), answer.content)


def _ask_validated[Parsed](
    backend: JudgeBackend,
    *,
    system: str,
    user: str,
    item_id: str,
    protocol: Protocol,
    validate: Callable[[str], Parsed],
) -> _Attempt[Parsed]:
    """Ask; on a schema failure ask once more with the complaint quoted back."""
    first = _ask_once(
        backend, system=system, user=user, item_id=item_id, protocol=protocol, validate=validate
    )
    if first.problem is None:
        return first
    repaired_user = user + REPAIR_INSTRUCTION.format(answer=first.raw, problem=first.problem)
    second = _ask_once(
        backend,
        system=system,
        user=repaired_user,
        item_id=item_id,
        protocol=protocol,
        validate=validate,
    )
    return _Attempt(
        second.parsed,
        first.calls + second.calls,
        second.problem,
        second.raw,
    )


def _failed(
    judge_input: JudgeInput, protocol: Protocol, *, calls: int, reason: str, examined: int = 0
) -> JudgeVerdict:
    return JudgeVerdict(
        item_id=judge_input.item_id,
        protocol=protocol,
        decisive_step=None,
        ranking=(),
        rationale="",
        calls=calls,
        steps_examined=examined,
        parse_failed=True,
        failure_reason=reason,
    )


def judge_all_at_once(
    judge_input: JudgeInput,
    backend: JudgeBackend,
    config: JudgeConfig = DEFAULT_CONFIG,
) -> JudgeVerdict:
    """The whole trajectory in one prompt: decisive step, ranked suspects, reason."""
    candidates = judge_input.candidate_steps
    if not candidates:
        raise ValueError(f"run {judge_input.run_id!r} has no candidate step to judge")
    system, user = build_all_at_once_prompt(judge_input, config.truncation)
    valid = frozenset(candidates)

    attempt = _ask_validated(
        backend,
        system=system,
        user=user,
        item_id=judge_input.item_id,
        protocol="all_at_once",
        validate=lambda text: parse_all_at_once(
            text, valid_steps=valid, limit=config.ranking_limit
        ),
    )
    if attempt.parsed is None:
        assert attempt.problem is not None
        return _failed(
            judge_input, "all_at_once", calls=attempt.calls, reason=attempt.problem
        )

    answer = attempt.parsed
    return JudgeVerdict(
        item_id=judge_input.item_id,
        protocol="all_at_once",
        decisive_step=answer.decisive_step,
        ranking=answer.ranking,
        rationale=answer.reason,
        calls=attempt.calls,
        steps_examined=len(candidates),
    )


@dataclass(frozen=True, slots=True)
class _Suspicion:
    step: int
    score: float
    rationale: str
    said_yes: bool


def _rank(suspicions: tuple[_Suspicion, ...], limit: int) -> tuple[RankedStep, ...]:
    """Yes first, then descending suspicion, ties on the earlier step."""
    ordered = sorted(
        suspicions, key=lambda item: (not item.said_yes, -item.score, item.step)
    )
    return tuple(
        RankedStep(
            step=item.step, rank=position + 1, score=item.score, rationale=item.rationale
        )
        for position, item in enumerate(ordered[:limit])
    )


def judge_step_by_step(
    judge_input: JudgeInput,
    backend: JudgeBackend,
    config: JudgeConfig = DEFAULT_CONFIG,
) -> JudgeVerdict:
    """Walk the trajectory forward, asking at each step, stopping at the first yes."""
    candidates = judge_input.candidate_steps
    if not candidates:
        raise ValueError(f"run {judge_input.run_id!r} has no candidate step to judge")

    suspicions: list[_Suspicion] = []
    calls = 0
    budget_hit = False
    decisive: int | None = None

    for examined, step_idx in enumerate(candidates, start=1):
        if examined > config.max_steps_examined:
            budget_hit = True
            break
        system, user = build_step_by_step_prompt(
            judge_input, step_idx=step_idx, policy=config.truncation
        )
        attempt = _ask_validated(
            backend,
            system=system,
            user=user,
            item_id=judge_input.item_id,
            protocol="step_by_step",
            validate=parse_step_by_step,
        )
        calls += attempt.calls
        if attempt.parsed is None:
            assert attempt.problem is not None
            return _failed(
                judge_input,
                "step_by_step",
                calls=calls,
                reason=f"step {step_idx}: {attempt.problem}",
                examined=len(suspicions) + 1,
            )
        verdict = attempt.parsed
        said_yes = verdict.error_here
        confidence = verdict.confidence
        suspicions.append(
            _Suspicion(
                step=step_idx,
                score=confidence if said_yes else 1.0 - confidence,
                rationale=verdict.reason,
                said_yes=said_yes,
            )
        )
        if said_yes:
            decisive = step_idx
            break

    reason = None
    if budget_hit:
        reason = (
            f"step budget exhausted after {config.max_steps_examined} steps of "
            f"{len(candidates)}"
        )
    ranking = _rank(tuple(suspicions), config.ranking_limit)
    return JudgeVerdict(
        item_id=judge_input.item_id,
        protocol="step_by_step",
        decisive_step=decisive,
        ranking=ranking,
        rationale=next(
            (item.rationale for item in suspicions if item.said_yes),
            "no step was identified as the decisive error",
        ),
        calls=calls,
        steps_examined=len(suspicions),
        failure_reason=reason,
    )
