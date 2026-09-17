"""The four planted faults: `wrong_value`, `missing_field`, `stale_record`,
`tool_error`.

Pre-registered in `docs/decisions/0001-preregistration.md`: a dataset item
is a stable success broken on purpose at one tool-result step. This module
is the breaking, and it is deliberately dull — seeded, deterministic, and
free of any model call. A dataset whose faults were invented by an LLM
could not be reproduced and could not be audited; these can.

What a mutator is allowed to do:

- change **one** thing, name it by path, and report the old and the new
  value, so the dataset card can print the funnel and the oracle fix is
  exactly "put the old value back";
- keep the shape it claims to keep — structured results stay valid JSON
  of the same shape, a date still looks like a date, an identifier still
  looks like an identifier;
- never be a no-op: a mutation equal to the truth would be labelled a
  planted fault and then pass, wasting four re-runs to discover nothing.

What it never does: touch anything outside the path it names, or touch
the fields that say *which* call the result answers (`id`, `requestor`).
Which leaf is worth breaking is `bench.salience`'s job.

`ReplaceToolResult` then shows the agent the mutated result. The world is
**not** mutated: the database is whatever the real tool call left behind,
so the fault is a fault of perception and the oracle fix is well defined.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, get_args

from agent_bisect.bench.salience import (
    Candidate,
    Path,
    best,
    droppable_candidates,
    dropped_at,
    is_scalar,
    looks_like_date,
    render_path,
    replaced_at,
    scalar_candidates,
)

FaultType = Literal["wrong_value", "missing_field", "stale_record", "tool_error"]

#: The four, in the order the dataset strata are reported.
FAULT_TYPES: tuple[FaultType, ...] = get_args(FaultType)

#: How a status rolls *back*: one step earlier in the entity's lifecycle.
#: This is what makes `stale_record` different in kind from `wrong_value` —
#: the result is not wrong, it is old.
STATUS_ROLLBACK: Mapping[str, str] = {
    "cancelled": "pending",
    "canceled": "pending",
    "confirmed": "pending",
    "completed": "processing",
    "delivered": "shipped",
    "shipped": "processed",
    "processed": "pending",
    "paid": "pending",
    "returned": "delivered",
    "exchanged": "delivered",
    "exchange requested": "delivered",
    "return requested": "delivered",
}

#: Real tau2 tool errors: every domain error is raised as a `ValueError`
#: and surfaces as `f"Error: {e}"` (`Environment.get_response`).
GENERIC_ERRORS: tuple[str, ...] = (
    "Error: Payment method not found",
    "Error: Gift card balance is not enough",
    "Error: Too many reservations",
    "Error: Invalid characters in expression",
    "Error: Cannot find the requested record",
)

#: Templates used when the call's own arguments are known, so the error
#: names the thing the agent actually asked about.
ARGUMENT_ERRORS: tuple[str, ...] = (
    "Error: {entity} {value} not found",
    "Error: {entity} {value} is not available",
    "Error: Cannot complete {tool}: {entity} {value} not found",
)

#: Days a stale date is rolled back by, and a wrong date moved by.
_DATE_SHIFTS = (1, 2, 3, 7, 14, 30)
_DATE_FORMAT = "%Y-%m-%d"
#: How far a wrong integer may be off. Never 0.
_INT_DELTAS = (-3, -2, -1, 1, 2, 3)
_PRICE_FACTORS = (0.5, 0.75, 1.25, 1.5, 2.0)


class NoFaultPossibleError(Exception):
    """This result cannot carry this fault.

    Not a failure: the pipeline logs the candidate as rejected with this
    reason and moves on. Silently returning the result unchanged would
    put an unfaulted run into the dataset with a planted-step label.
    """


@dataclass(frozen=True)
class FaultContext:
    """What the recording knows that makes a fault better chosen.

    `downstream` is the text of the conversation *after* this step: a
    value that re-appears there was demonstrably read. `earlier` is the
    same call's result from an earlier point in the run, which is what
    makes `stale_record` literally stale. `tool_name`/`tool_args` let a
    `tool_error` name the thing the agent asked about.
    """

    tool_name: str = ""
    tool_args: Mapping[str, Any] = field(default_factory=dict)
    downstream: str = ""
    #: Just the arguments of later calls that change the world. A value
    #: that reaches one of those is a value the run acted on, which is
    #: what a planted fault has to break to matter at all.
    downstream_writes: str = ""
    earlier: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Mutation:
    """Exactly what changed, in a form the dataset card can print."""

    fault_type: FaultType
    path: Path
    old: Any
    new: Any
    detail: str

    @property
    def path_str(self) -> str:
        return render_path(self.path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault_type": self.fault_type,
            "path": list(self.path),
            "path_str": self.path_str,
            "old": self.old,
            "new": self.new,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class FaultedResult:
    """The mutated tool-result payload and the account of the mutation."""

    payload: dict[str, Any]
    mutation: Mutation


def plant(
    payload: Mapping[str, Any],
    *,
    fault_type: FaultType,
    seed: int,
    context: FaultContext | None = None,
) -> FaultedResult:
    """Break `payload` in exactly one way. Raises `NoFaultPossibleError`."""
    if fault_type not in FAULT_TYPES:
        raise ValueError(f"unknown fault type {fault_type!r}; known: {list(FAULT_TYPES)}")
    context = context or FaultContext()
    rng = random.Random(f"{fault_type}:{seed}")
    if fault_type == "tool_error":
        return _plant_tool_error(payload, rng, context)
    body, is_json = _parse(str(payload.get("content") or ""))
    planter = {
        "wrong_value": _plant_wrong_value,
        "missing_field": _plant_missing_field,
        "stale_record": _plant_stale_record,
    }[fault_type]
    mutated, mutation = planter(body, rng, context)
    return FaultedResult(
        payload={**dict(payload), "content": _render(mutated, is_json)},
        mutation=mutation,
    )


# ---- wrong_value ------------------------------------------------------------


def _plant_wrong_value(
    body: Any, rng: random.Random, context: FaultContext
) -> tuple[Any, Mutation]:
    chosen = _pick(_ranked(body, context), "wrong_value", rng)
    new = _wrong_scalar(chosen.value, rng)
    return (
        replaced_at(body, chosen.path, new),
        Mutation(
            fault_type="wrong_value",
            path=chosen.path,
            old=chosen.value,
            new=new,
            detail=f"{render_path(chosen.path)}: {chosen.value!r} -> {new!r}",
        ),
    )


def _wrong_scalar(value: Any, rng: random.Random) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + rng.choice(_INT_DELTAS)
    if isinstance(value, float):
        changed = round(value * rng.choice(_PRICE_FACTORS), 2)
        return changed if changed != value else value + 1.0
    return _wrong_text(str(value), rng)


def _wrong_text(value: str, rng: random.Random) -> str:
    shifted = _shift_date(value, rng.choice(_DATE_SHIFTS) * rng.choice((-1, 1)))
    if shifted is not None:
        return shifted
    return _perturb(value, rng)


def _perturb(value: str, rng: random.Random) -> str:
    """Change one alphanumeric character, keeping its case class."""
    positions = [index for index, char in enumerate(value) if char.isalnum()]
    if not positions:
        raise NoFaultPossibleError(
            f"wrong_value: {value!r} has no alphanumeric character to change"
        )
    index = rng.choice(positions)
    char = value[index]
    if char.isdigit():
        alphabet = "0123456789"
    elif char.isupper():
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    else:
        alphabet = "abcdefghijklmnopqrstuvwxyz"
    replacement = rng.choice([letter for letter in alphabet if letter != char])
    return value[:index] + replacement + value[index + 1 :]


def _shift_date(value: str, days: int) -> str | None:
    """`value` moved by `days`, or `None` if it is not a date."""
    if not looks_like_date(value):
        return None
    try:
        moved = datetime.strptime(value[:10], _DATE_FORMAT).date() + timedelta(days=days)
    except ValueError:
        return None
    return moved.strftime(_DATE_FORMAT) + value[10:]


# ---- missing_field ----------------------------------------------------------


def _plant_missing_field(
    body: Any, rng: random.Random, context: FaultContext
) -> tuple[Any, Mutation]:
    chosen = _pick(
        droppable_candidates(body, context.downstream, context.downstream_writes),
        "missing_field", rng,
    )
    return (
        dropped_at(body, chosen.path),
        Mutation(
            fault_type="missing_field",
            path=chosen.path,
            old=chosen.value,
            new=None,
            detail=f"{render_path(chosen.path)}: dropped",
        ),
    )


# ---- stale_record -----------------------------------------------------------


def _plant_stale_record(
    body: Any, rng: random.Random, context: FaultContext
) -> tuple[Any, Mutation]:
    older = _earlier_body(context)
    if older is not None and older != body:
        return (
            older,
            Mutation(
                fault_type="stale_record",
                path=(),
                old=body,
                new=older,
                detail="the same call's result from earlier in the run",
            ),
        )
    candidates = [candidate for candidate in _ranked(body, context) if _has_a_past(candidate.value)]
    chosen = _pick(candidates, "stale_record", rng)
    new = _rolled_back(chosen.value, rng)
    return (
        replaced_at(body, chosen.path, new),
        Mutation(
            fault_type="stale_record",
            path=chosen.path,
            old=chosen.value,
            new=new,
            detail=f"{render_path(chosen.path)}: rolled back {chosen.value!r} -> {new!r}",
        ),
    )


def _earlier_body(context: FaultContext) -> Any:
    if context.earlier is None:
        return None
    body, _is_json = _parse(str(context.earlier.get("content") or ""))
    return body


def _has_a_past(value: Any) -> bool:
    """True when `value` has an earlier version this module can name."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() in STATUS_ROLLBACK or looks_like_date(value)
    return False


def _rolled_back(value: Any, rng: random.Random) -> Any:
    """`value` as it plausibly was earlier. Only for values with a past."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value - 1
    if isinstance(value, float):
        return round(value * 0.8, 2)
    rolled = STATUS_ROLLBACK.get(str(value).strip().lower())
    if rolled is not None:
        return rolled
    shifted = _shift_date(str(value), -rng.choice(_DATE_SHIFTS))
    if shifted is None:  # pragma: no cover - guarded by `_has_a_past`
        raise NoFaultPossibleError(f"stale_record: {value!r} has no earlier version")
    return shifted


# ---- tool_error -------------------------------------------------------------


def _plant_tool_error(
    payload: Mapping[str, Any], rng: random.Random, context: FaultContext
) -> FaultedResult:
    if payload.get("error"):
        raise NoFaultPossibleError(
            "tool_error: this call already failed, so failing it again changes nothing"
        )
    old = payload.get("content")
    message = _error_message(rng, context)
    return FaultedResult(
        payload={**dict(payload), "content": message, "error": True},
        mutation=Mutation(
            fault_type="tool_error",
            path=(),
            old=old,
            new=message,
            detail=f"the call now fails: {message}",
        ),
    )


def _error_message(rng: random.Random, context: FaultContext) -> str:
    named = _named_argument(context.tool_args)
    if named is None:
        return rng.choice(GENERIC_ERRORS)
    key, value = named
    return rng.choice(ARGUMENT_ERRORS).format(
        entity=_entity_of(key), value=value, tool=context.tool_name or "the request"
    )


def _named_argument(tool_args: Mapping[str, Any]) -> tuple[str, Any] | None:
    """The argument an error would most plausibly be about: an id, else the first."""
    scalars = [(key, value) for key, value in tool_args.items() if is_scalar(value)]
    if not scalars:
        return None
    for key, value in scalars:
        if key.lower().endswith("_id") or key.lower() == "id":
            return key, value
    return scalars[0]


def _entity_of(key: str) -> str:
    stem = key[:-3] if key.lower().endswith("_id") else key
    return stem.replace("_", " ").strip().capitalize() or "Record"


# ---- shared -----------------------------------------------------------------


def _ranked(body: Any, context: FaultContext) -> list[Candidate]:
    """Scalar leaves, scored with the downstream-write flow weighted in."""
    return scalar_candidates(body, context.downstream, context.downstream_writes)


def parse_content(content: str) -> tuple[Any, bool]:
    """`(body, is_json)` for a tau2 tool result's content."""
    return _parse(content)


def _pick(candidates: list[Candidate], fault_type: str, rng: random.Random) -> Candidate:
    if not candidates:
        raise NoFaultPossibleError(
            f"{fault_type}: this result has nothing that could plausibly be broken"
        )
    return best(candidates, rng)


def _parse(content: str) -> tuple[Any, bool]:
    """`(body, is_json)`. tau2 dumps structured results and passes text through."""
    try:
        return json.loads(content), True
    except (ValueError, TypeError):
        return content, False


def _render(body: Any, is_json: bool) -> str:
    if not is_json:
        return str(body)
    return json.dumps(body, default=str)
