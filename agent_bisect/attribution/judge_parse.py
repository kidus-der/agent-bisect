"""Strict schema validation of the judge's answers.

Who&When parses a free-text answer. We require one JSON object and check
it, because the alternative is a lenient parser that quietly turns a
confused answer into a plausible-looking step index — and a benchmark
whose headline number depends on how forgiving its parser is measures the
parser.

Every rejection raises `JudgeParseError` naming the offending field. The
caller (`attribution/judge.py`) turns the first one into a single repair
retry and the second into a recorded parse failure, which counts as a
wrong answer and is never dropped.

Two deliberate leniencies, both stated rather than hidden:

- **Fences and surrounding prose are tolerated.** Models wrap JSON in
  ```json fences and add "Here is my answer:". Refusing those would
  measure formatting compliance, not attribution skill, so the first
  balanced `{...}` object in the text is taken.
- **A ranking longer than the limit is truncated, not rejected.** P5 never
  reports beyond recall@10, so entries past the limit cannot change a
  number; rejecting them would spend a repair retry on nothing.

The ranking's *order* is taken as given — rank is list position — even if
the judge's confidences do not decrease monotonically. Re-sorting would be
us overruling the judge's own stated order on the metric it is being
compared on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent_bisect.attribution.judge_view import RankedStep


class JudgeParseError(ValueError):
    """The judge's answer did not satisfy the requested schema."""


@dataclass(frozen=True, slots=True)
class AllAtOnceAnswer:
    """A validated all-at-once answer."""

    decisive_step: int
    actor: str
    reason: str
    ranking: tuple[RankedStep, ...]


@dataclass(frozen=True, slots=True)
class StepVerdict:
    """A validated step-by-step answer about one step."""

    error_here: bool
    confidence: float
    reason: str


def _find_objects(text: str) -> list[str]:
    """Every balanced top-level `{...}` run in `text`, ignoring braces in strings."""
    found: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                found.append(text[start : index + 1])
                start = -1
    return found


def extract_json_object(text: str) -> dict[str, Any]:
    """The judge's JSON object, whatever it wrapped it in.

    The **last** parseable object wins, not the first. The P0-chosen judge
    is a reasoning model: it narrates first -- often quoting the very
    schema it was asked for, braces and all -- and answers at the end.
    Taking the first object would hand back a fragment of its thinking.
    Earlier objects are still tried, so a model that answers up front and
    then keeps talking into a truncation is read correctly too.
    """
    candidates = _find_objects(text)
    if not candidates:
        raise JudgeParseError("no JSON object in the judge's answer")
    problem: str | None = None
    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            problem = str(exc)
            continue
        if isinstance(parsed, dict):
            return parsed
        problem = "got a non-object"
    raise JudgeParseError(f"the judge's JSON object did not parse: {problem}")


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise JudgeParseError(f"the judge's answer has no {key!r}")
    return payload[key]


def _as_step(value: Any, *, field: str, valid_steps: frozenset[int]) -> int:
    # `bool` is an `int` in Python and `True` would silently become step 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise JudgeParseError(f"{field} must be an integer step index, got {value!r}")
    if value not in valid_steps:
        raise JudgeParseError(f"{field} names step {value}, which is not in the trajectory")
    return value


def _as_confidence(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise JudgeParseError(f"{field} confidence must be a number, got {value!r}")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise JudgeParseError(f"{field} confidence must be between 0 and 1, got {confidence}")
    return confidence


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _parse_ranking(
    raw: Any, *, decisive_step: int, valid_steps: frozenset[int], limit: int
) -> tuple[RankedStep, ...]:
    if not isinstance(raw, list) or not raw:
        raise JudgeParseError("the judge's answer has an empty or non-list 'ranking'")
    entries: list[RankedStep] = []
    seen: set[int] = set()
    for position, item in enumerate(raw[:limit]):
        if not isinstance(item, dict):
            raise JudgeParseError(f"ranking[{position}] is not an object")
        field = f"ranking[{position}]"
        step = _as_step(_require(item, "step"), field=field, valid_steps=valid_steps)
        if step in seen:
            raise JudgeParseError(f"{field} names step {step} twice")
        seen.add(step)
        entries.append(
            RankedStep(
                step=step,
                rank=position + 1,
                score=_as_confidence(item.get("confidence", 0.0), field=field),
                rationale=_as_text(item.get("reason", "")),
            )
        )
    if entries[0].step != decisive_step:
        raise JudgeParseError(
            f"ranking[0] names step {entries[0].step} but decisive_step is {decisive_step}"
        )
    return tuple(entries)


def parse_all_at_once(
    text: str, *, valid_steps: frozenset[int], limit: int
) -> AllAtOnceAnswer:
    """Validate an all-at-once answer, or say exactly what is wrong with it."""
    payload = extract_json_object(text)
    decisive_step = _as_step(
        _require(payload, "decisive_step"), field="decisive_step", valid_steps=valid_steps
    )
    return AllAtOnceAnswer(
        decisive_step=decisive_step,
        actor=_as_text(payload.get("actor", "")),
        reason=_as_text(payload.get("reason", "")),
        ranking=_parse_ranking(
            _require(payload, "ranking"),
            decisive_step=decisive_step,
            valid_steps=valid_steps,
            limit=limit,
        ),
    )


def parse_step_by_step(text: str) -> StepVerdict:
    """Validate one step-by-step verdict, or say exactly what is wrong with it."""
    payload = extract_json_object(text)
    error_here = _require(payload, "error_here")
    if not isinstance(error_here, bool):
        raise JudgeParseError(f"'error_here' must be true or false, got {error_here!r}")
    return StepVerdict(
        error_here=error_here,
        confidence=_as_confidence(payload.get("confidence", 0.5), field="the verdict's"),
        reason=_as_text(payload.get("reason", "")),
    )
