"""The flaky world: a τ² domain that does not answer the same way twice.

τ²'s airline and retail tools are deterministic functions of the database
— `_get_new_reservation_id` picks from a fixed list, `_get_datetime`
returns a constant, and neither domain uses `random`, the clock, the
network or the filesystem. On such a world, serving a recorded tool
result from a snapshot and re-executing the tool live agree, so snapshots
buy speed and nothing else.

This module is where they stop agreeing. Three sources of
non-determinism, all driven by one RNG **seeded per run** and recorded in
the manifest, so a recording is self-consistent on tape while
re-executing the same calls later gives different answers:

1. **random identifiers** — the toolkit's id generator mints a fresh
   random id per execution instead of the next entry of a fixed list. It
   is generated inside the tool, so the database and the returned record
   agree with each other within a run;
2. **a drifting clock** — a simulated clock advances one tick per tool
   execution; stamped creation times move with it, and availability and
   price fields in *returned* read results drift with it (seats sell,
   fares move) without the database being edited;
3. **injected errors** — with probability `p_error`, decided **before**
   the tool runs, so the tool is not executed at all and the database is
   untouched. That is what a transient backend failure does, and what
   τ²'s own error path does.

Install it on the environment **before** the recorder or the replayer
wraps `get_response`: then the recorder records the flaky answers and a
`rerun_live` prefix reaches them, while a `snapshot` prefix never calls
the tool at all. That asymmetry is the ablation.

The reward under this world is **not** τ²'s stock reward — its evaluator
re-executes write actions on an environment of its own and would mint
different identifiers — so it is the DB-state check on a canonicalised
database. `canonicalise` and `flaky_db_hash` here implement exactly the
renaming defined in `docs/decisions/0011-flaky-world.md`.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from agent_bisect.adapters.tau2 import wrap_tool_execution

#: What the deterministic airline domain would have produced, in order
#: (`AirlineTools._get_new_reservation_id` at the pinned tau2 commit).
#: Canonicalisation maps the i-th random id back onto the i-th of these.
DETERMINISTIC_RESERVATION_IDS: tuple[str, ...] = ("HATHAT", "HATHAU", "HATHAV")

#: Identifier shape: six upper-case alphanumerics, like the domain's own.
ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
ID_LENGTH = 6

#: Result fields that move with the clock. They are returned to the agent
#: and never written to the database, so they stay out of the DB check.
DRIFTING_KEYS = frozenset({"available_seats", "prices"})

#: The clock the deterministic airline domain reports.
BASE_DATETIME = "2024-05-15T15:00:00"

#: How far availability and prices may drift, per tick.
_SEAT_CYCLE = 4
_PRICE_STEP = 0.01
_PRICE_CYCLE = 5

#: A transient failure, in the shape `Environment.get_response` produces.
TRANSIENT_ERROR = "Error: The reservation system is temporarily unavailable. Please try again."


@dataclass(frozen=True)
class FlakyConfig:
    """Everything the flaky world does, and how much of it."""

    seed: int
    p_error: float = 0.05
    clock_seconds: int = 3600
    random_ids: bool = True
    drifting_reads: bool = True
    base_datetime: str = BASE_DATETIME

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "p_error": self.p_error,
            "clock_seconds": self.clock_seconds,
            "random_ids": self.random_ids,
            "drifting_reads": self.drifting_reads,
            "base_datetime": self.base_datetime,
        }


class FlakyWorld:
    """One run's worth of non-determinism: the RNG, the clock, the trail.

    An accumulator by nature — it exists to remember what it did, so the
    reward can undo the renaming afterwards.
    """

    def __init__(self, config: FlakyConfig) -> None:
        self._config = config
        self._rng = random.Random(config.seed)
        self.id_trail: list[tuple[str, str]] = []
        self.ticks = 0
        self.injected_errors = 0
        self.executions = 0

    @property
    def config(self) -> FlakyConfig:
        return self._config

    def tick(self) -> None:
        self.ticks += 1

    def new_id(self) -> str:
        """A random identifier, paired with the one the domain would have used."""
        flaky = "".join(self._rng.choice(ID_ALPHABET) for _ in range(ID_LENGTH))
        index = len(self.id_trail)
        deterministic = (
            DETERMINISTIC_RESERVATION_IDS[index]
            if index < len(DETERMINISTIC_RESERVATION_IDS)
            else f"OVERFLOW{index}"
        )
        self.id_trail.append((flaky, deterministic))
        return flaky

    def now(self) -> str:
        """The simulated clock, `clock_seconds` per tool execution so far."""
        base = datetime.fromisoformat(self._config.base_datetime)
        return (base + timedelta(seconds=self._config.clock_seconds * self.ticks)).isoformat()

    def should_fail(self) -> bool:
        if self._rng.random() >= self._config.p_error:
            return False
        self.injected_errors += 1
        return True

    def canonical_ids(self) -> dict[str, str]:
        """The renaming that undoes this run's random identifiers and clock."""
        mapping = {flaky: deterministic for flaky, deterministic in self.id_trail}
        for tick in range(self.ticks + 1):
            base = datetime.fromisoformat(self._config.base_datetime)
            stamped = (base + timedelta(seconds=self._config.clock_seconds * tick)).isoformat()
            mapping[stamped] = self._config.base_datetime
        return mapping

    def manifest(self) -> dict[str, Any]:
        """What the run manifest records, so a recording can be explained."""
        return {
            **self._config.as_dict(),
            "generated_ids": [flaky for flaky, _ in self.id_trail],
            "canonical_ids": self.canonical_ids(),
            "ticks": self.ticks,
            "executions": self.executions,
            "injected_errors": self.injected_errors,
        }


@contextmanager
def flaky_world(environment: Any, config: FlakyConfig) -> Iterator[FlakyWorld]:
    """Make `environment` non-deterministic for the duration.

    Enter this *before* the recorder or the replayer wraps
    `get_response`, so their wrapper sits outside this one and sees the
    flaky answers.
    """
    world = FlakyWorld(config)
    with ExitStack() as stack:
        stack.enter_context(_patched_generators(environment, world, config))
        stack.enter_context(wrap_tool_execution(environment, _responder(world, config)))
        yield world


@contextmanager
def _patched_generators(environment: Any, world: FlakyWorld, config: FlakyConfig) -> Iterator[None]:
    """Swap the toolkit's id generator and clock, on the instance only."""
    toolkit = getattr(environment, "tools", None)
    originals: list[tuple[Any, str, Any]] = []
    if toolkit is not None and config.random_ids:
        originals.extend(_swap(toolkit, "_get_new_reservation_id", world.new_id))
    if toolkit is not None:
        originals.extend(_swap(toolkit, "_get_datetime", world.now))
    try:
        yield
    finally:
        for owner, name, original in originals:
            setattr(owner, name, original)


def _swap(owner: Any, name: str, replacement: Any) -> list[tuple[Any, str, Any]]:
    """Replace `owner.name` if it exists. A domain without it is left alone."""
    if not hasattr(owner, name):
        return []
    original = getattr(owner, name)
    setattr(owner, name, replacement)
    return [(owner, name, original)]


def _responder(world: FlakyWorld, config: FlakyConfig) -> Any:
    """The `get_response` wrapper: fail, or execute and let the answer drift."""

    def respond(original: Any, tool_call: Any) -> Any:
        world.tick()
        if config.p_error > 0 and world.should_fail():
            return _error_message(tool_call)
        world.executions += 1
        message = original(tool_call)
        if config.drifting_reads and not message.error:
            return _drifted(message, world)
        return message

    return respond


def _error_message(tool_call: Any) -> Any:
    """A transient failure that executed nothing, so the world is untouched."""
    from tau2.data_model.message import ToolMessage

    return ToolMessage(
        id=tool_call.id,
        role="tool",
        content=TRANSIENT_ERROR,
        requestor=getattr(tool_call, "requestor", "assistant"),
        error=True,
    )


def _drifted(message: Any, world: FlakyWorld) -> Any:
    """Availability and prices as they are *now*, not as they were stored."""
    try:
        body = json.loads(message.content or "")
    except (TypeError, ValueError):
        return message
    moved = _drift(body, world.ticks)
    if moved == body:
        return message
    return message.model_copy(update={"content": json.dumps(moved, default=str)})


def _drift(node: Any, ticks: int) -> Any:
    if isinstance(node, dict):
        return {key: _drift_value(key, value, ticks) for key, value in node.items()}
    if isinstance(node, list):
        return [_drift(item, ticks) for item in node]
    return node


def _drift_value(key: str, value: Any, ticks: int) -> Any:
    if key not in DRIFTING_KEYS or not isinstance(value, dict):
        return _drift(value, ticks)
    return {inner: _moved(key, amount, ticks) for inner, amount in value.items()}


def _moved(key: str, amount: Any, ticks: int) -> Any:
    if key == "available_seats" and isinstance(amount, int):
        return max(0, amount - ticks % _SEAT_CYCLE)
    if key == "prices" and isinstance(amount, int | float):
        return round(float(amount) * (1 + _PRICE_STEP * (ticks % _PRICE_CYCLE)), 2)
    return amount


# ---- the canonicalised reward (decision 0011) -------------------------------


def canonicalise(node: Any, mapping: Mapping[str, str]) -> Any:
    """`node` with every flaky name replaced by its deterministic one.

    Applied to dictionary keys and to string values at any depth. A
    renaming, not a relaxation: anything that differs for a reason other
    than which random name an identifier got still differs afterwards.
    """
    if isinstance(node, dict):
        return {
            _renamed(str(key), mapping): canonicalise(value, mapping)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [canonicalise(item, mapping) for item in node]
    if isinstance(node, str):
        return _renamed(node, mapping)
    return node


def _renamed(text: str, mapping: Mapping[str, str]) -> str:
    replaced = mapping.get(text)
    if replaced is not None:
        return replaced
    for flaky, deterministic in mapping.items():
        if flaky in text:
            text = text.replace(flaky, deterministic)
    return text


def flaky_db_hash(environment: Any, world: FlakyWorld) -> str:
    """τ²'s own db hash, over the canonicalised database.

    Identical to `Environment.get_db_hash` except for the renaming, so two
    worlds that did the same thing under different random names agree and
    two that did different things still do not.
    """
    from tau2.utils.utils import get_dict_hash

    toolkit = getattr(environment, "tools", None)
    if toolkit is None or toolkit.db is None:
        raise ValueError("environment has no database to hash")
    return get_dict_hash(canonicalise(toolkit.db.model_dump(), world.canonical_ids()))


def canonical_actions(actions: Sequence[Mapping[str, Any]], world: FlakyWorld) -> list[dict]:
    """The golden actions with their arguments canonicalised the same way."""
    return [canonicalise(dict(action), world.canonical_ids()) for action in actions]


# ---- evaluating a flaky run (decision 0011) ---------------------------------


def canonical_simulation(simulation: Any, world: FlakyWorld) -> Any:
    """`simulation` with this run's random names replaced by the deterministic ones.

    A renaming applied to the whole trajectory — every message body and
    every tool-call argument — so that tau2's own evaluator, which
    replays the write actions on a fresh environment of its own, sees the
    identifiers *it* would have minted. Without it the replay does not
    merely score 0: `Environment.set_state` raises on the mismatch.
    """
    mapping = world.canonical_ids()
    return type(simulation).model_validate(
        canonicalise(simulation.model_dump(mode="json"), mapping)
    )


def flaky_evaluate(simulation: Any, task: Any, domain: str, world: FlakyWorld) -> Any:
    """tau2's own reward, computed on the canonicalised trajectory.

    This is the flaky-world reward defined in
    `docs/decisions/0011-flaky-world.md`: not a relaxed check, the same
    one — the DB hash, the action checks and the communicate checks — with
    generated identifiers and clock stamps renamed first. Two runs that
    booked the same flight under different random names agree; a run that
    booked a different flight still does not.
    """
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation

    return evaluate_simulation(
        simulation=canonical_simulation(simulation, world),
        task=task,
        evaluation_type=EvaluationType.ALL,
        solo_mode=False,
        domain=domain,
    )
