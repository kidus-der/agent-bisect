"""Which part of a tool result is worth breaking.

A fault planted on a field nobody reads is not a fault: the run passes,
the KEEP rule throws the candidate away, and four re-runs were spent
finding that out. So a mutator does not pick a leaf at random — it scores
every candidate and takes the best, breaking ties with the seeded RNG so
the choice is reproducible but not always the same one.

The score is deliberately crude and explainable (no model is involved
anywhere in dataset construction):

- **key name** — `reservation_id`, `price`, `status`, `total_baggages`
  and their kin are what an agent quotes back and acts on;
- **re-use downstream** — the strongest signal there is: if the value
  appears again later in the recorded conversation, the run demonstrably
  read it;
- **shape** — a value that looks like an identifier or a date is more
  load-bearing than free text;
- **depth** — a field near the top of the result is more likely to be the
  answer than one buried in a nested record.

Paths are tuples of dict keys and list indices, and every edit here
returns a **new** structure: nothing recorded is ever mutated in place.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

#: Key tokens an agent is likely to act on, matched against the key split
#: on `_` so `valid` does not count as `id`.
SALIENT_TOKENS = frozenset(
    {
        "id", "ids", "price", "prices", "amount", "cost", "total", "date", "dates",
        "time", "status", "state", "count", "seats", "quantity", "balance", "number",
        "fee", "available", "payment", "baggage", "baggages", "reservation", "order",
        "flight", "user", "address", "email", "insurance", "cabin", "origin",
        "destination",
    }
)

#: A path component: a dict key or a list index.
PathPart = str | int
Path = tuple[PathPart, ...]

SALIENT_KEY_BONUS = 3.0
DOWNSTREAM_BONUS = 4.0
#: A value that reaches a later call which CHANGES the world is the only
#: kind a perception fault reliably turns into a wrong outcome. It
#: outranks every other signal, because the others are guesses about what
#: the agent might use and this one is a record of what it did use.
WRITE_FLOW_BONUS = 8.0
SHAPE_BONUS = 1.0
DEPTH_PENALTY = 0.5
#: Dropping a whole sub-record is a gross change an agent notices at once.
CONTAINER_PENALTY = 2.0
#: A missing record in a list is the classic "the API forgot one" fault,
#: and the most consequential thing a result can lose, so it outranks any
#: single field inside that record.
LIST_ELEMENT_BONUS = 4.5
#: Shorter values match too much text to count as "re-used downstream".
MIN_DOWNSTREAM_CHARS = 3


@dataclass(frozen=True)
class Candidate:
    """One place a mutator could act, with the score that ranked it."""

    path: Path
    value: Any
    score: float

    @property
    def key(self) -> str:
        """The last dict key on the path, or `""` for a list index / the root."""
        last = self.path[-1] if self.path else ""
        return last if isinstance(last, str) else ""


def is_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


def looks_like_date(value: Any) -> bool:
    text = str(value)
    return len(text) >= 10 and text[4] == "-" and text[7] == "-" and text[:4].isdigit()


def looks_like_identifier(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 4 or looks_like_date(value):
        return False
    stripped = value.replace("_", "").replace("-", "").replace("#", "")
    return stripped.isalnum() and (any(c.isdigit() for c in value) or value.isupper())


def key_is_salient(key: str) -> bool:
    return bool(SALIENT_TOKENS & set(key.lower().split("_")))


def score_of(path: Path, value: Any, downstream: str, downstream_writes: str = "") -> float:
    """How much an agent is likely to care about `value` at `path`."""
    key = path[-1] if path and isinstance(path[-1], str) else ""
    score = 1.0 - DEPTH_PENALTY * len(path)
    if key_is_salient(key):
        score += SALIENT_KEY_BONUS
    if is_scalar(value) and not isinstance(value, bool):
        text = str(value)
        if len(text) >= MIN_DOWNSTREAM_CHARS and text in downstream:
            score += DOWNSTREAM_BONUS
        if len(text) >= MIN_DOWNSTREAM_CHARS and downstream_writes and text in downstream_writes:
            score += WRITE_FLOW_BONUS
    if looks_like_identifier(value) or looks_like_date(value):
        score += SHAPE_BONUS
    if isinstance(path[-1] if path else "", int):
        score += LIST_ELEMENT_BONUS
    return score


def scalar_candidates(
    body: Any, downstream: str = "", downstream_writes: str = ""
) -> list[Candidate]:
    """Every scalar leaf of `body`, scored. The root counts when it is one."""
    found: list[Candidate] = []
    _walk_scalars(body, (), downstream, downstream_writes, found)
    return found


def _walk_scalars(
    node: Any, path: Path, downstream: str, writes: str, found: list[Candidate]
) -> None:
    if is_scalar(node):
        found.append(Candidate(path, node, score_of(path, node, downstream, writes)))
        return
    for part, child in _children(node):
        _walk_scalars(child, (*path, part), downstream, writes, found)


def droppable_candidates(
    body: Any, downstream: str = "", downstream_writes: str = ""
) -> list[Candidate]:
    """Every dict key and list element that could be dropped, scored."""
    found: list[Candidate] = []
    _walk_droppable(body, (), downstream, downstream_writes, found)
    return found


def _walk_droppable(
    node: Any, path: Path, downstream: str, writes: str, found: list[Candidate]
) -> None:
    for part, child in _children(node):
        here = (*path, part)
        score = score_of(here, child, downstream, writes)
        if not is_scalar(child) and isinstance(part, str):
            score -= CONTAINER_PENALTY
        found.append(Candidate(here, child, score))
        _walk_droppable(child, here, downstream, writes, found)


def _children(node: Any) -> list[tuple[PathPart, Any]]:
    if isinstance(node, dict):
        return [(str(key), value) for key, value in node.items()]
    if isinstance(node, list):
        return list(enumerate(node))
    return []


def best(candidates: Sequence[Candidate], rng: random.Random) -> Candidate:
    """The highest-scoring candidate; ties broken by `rng`, never by dict order."""
    if not candidates:
        raise ValueError("no candidate to choose from")
    top = max(candidate.score for candidate in candidates)
    tied = sorted(
        (candidate for candidate in candidates if candidate.score == top),
        key=lambda candidate: render_path(candidate.path),
    )
    return tied[rng.randrange(len(tied))]


def render_path(path: Path) -> str:
    """`("flights", 0, "price")` -> `"flights[0].price"`, for a diff line."""
    parts: list[str] = []
    for component in path:
        if isinstance(component, int):
            parts.append(f"[{component}]")
        else:
            parts.append(f".{component}" if parts else component)
    return "".join(parts) or "<result>"


def replaced_at(body: Any, path: Path, value: Any) -> Any:
    """A copy of `body` with `path` set to `value`. `body` is not touched."""
    if not path:
        return value
    head, rest = path[0], path[1:]
    if isinstance(body, list):
        index = int(head)
        copy = list(body)
        copy[index] = replaced_at(body[index], rest, value)
        return copy
    copy = dict(body)
    copy[head] = replaced_at(body[head], rest, value)
    return copy


def dropped_at(body: Any, path: Path) -> Any:
    """A copy of `body` without the entry at `path`. `body` is not touched."""
    if not path:
        raise ValueError("the whole result cannot be dropped")
    head, rest = path[0], path[1:]
    if rest:
        return replaced_at(body, (head,), dropped_at(_child(body, head), rest))
    if isinstance(body, list):
        copy = list(body)
        del copy[int(head)]
        return copy
    return {key: value for key, value in body.items() if key != head}


def _child(body: Any, part: PathPart) -> Any:
    return body[int(part)] if isinstance(body, list) else body[part]
