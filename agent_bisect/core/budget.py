"""Call ledger: records every LLM API call to SQLite (WAL) and enforces a hard budget cap.

The ledger is the single source of truth for "how many calls has this
process (or a previous run, via the same file) made".

**The cap is enforced by `reserve()`, not by `check_budget()`.** Anything
about to spend a call reserves a slot first: the count and the insert are
one statement, so concurrent callers cannot all see "under the cap" and
then all insert. The reservation row is written *before* the request goes
out — a call in flight has already been paid for, so it must hold its slot
— and `finish()` fills in the outcome. τ² runs its tasks in a thread pool
and our own code runs coroutines, so this is the normal case rather than
an edge one.

`check_budget()` remains for read-only reporting and is explicitly
advisory; `record()` is for after-the-fact accounting of calls that have
already been made.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_LEDGER_PATH = Path("runs/ledger.sqlite")
#: Concurrent writers queue on SQLite's write lock rather than failing fast.
BUSY_TIMEOUT_S = 30.0
#: A row written before its call is made, updated by finish() afterwards.
RESERVED_STATUS = "reserved"

_COLUMNS = "ts, phase, model, purpose, status, tokens_in, tokens_out, latency_ms"
_INSERT_SQL = f"INSERT INTO calls ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
#: The count and the insert in ONE statement: that is what makes the cap hold
#: under concurrency. rowcount == 0 means the cap was already reached.
_INSERT_GUARDED_SQL = (
    f"INSERT INTO calls ({_COLUMNS}) "
    "SELECT ?, ?, ?, ?, ?, ?, ?, ? "
    "WHERE (SELECT COUNT(*) FROM calls) < ?"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    phase TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    latency_ms REAL NOT NULL
);
"""


def _row_values(record: CallRecord) -> tuple:
    return (
        record.ts,
        record.phase,
        record.model,
        record.purpose,
        record.status,
        record.tokens_in,
        record.tokens_out,
        record.latency_ms,
    )


class BudgetExceededError(RuntimeError):
    """Raised before a call is attempted when it would exceed the configured hard cap."""


class CallRecord(BaseModel):
    """One immutable ledger row. Construct a new instance per call; never mutate one in place."""

    model_config = ConfigDict(frozen=True)

    ts: float
    phase: str
    model: str
    purpose: str
    status: str
    tokens_in: int
    tokens_out: int
    latency_ms: float


def current_phase(explicit: str | None = None) -> str:
    """Resolve the phase: an explicit argument wins, else `$BISECT_PHASE`, else "unknown"."""
    if explicit is not None:
        return explicit
    return os.environ.get("BISECT_PHASE", "unknown")


class BudgetLedger:
    """SQLite-backed (WAL mode) ledger of LLM calls, with a hard-cap guard.

    Short-lived connections are opened per operation; WAL mode makes this
    safe for concurrent readers (e.g. `bisect doctor` inspecting a ledger
    written by another process) without holding a connection open.
    """

    def __init__(self, db_path: Path = DEFAULT_LEDGER_PATH, max_calls: int | None = None) -> None:
        self._db_path = db_path
        self._max_calls = max_calls
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_S)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT_S * 1000)}")
        return conn

    def check_budget(self) -> None:
        """Advisory, non-atomic peek at the cap.

        Only for read-only reporting (`bisect doctor`). It does **not**
        enforce the cap: between this SELECT and a later INSERT any number
        of other threads can do the same, and every one of them passes.
        Anything about to spend a call must use `reserve()`.
        """
        if self._max_calls is None:
            return
        total = self.total_calls()
        if total >= self._max_calls:
            raise BudgetExceededError(
                f"budget exceeded: {total} calls already recorded, cap is {self._max_calls}"
            )

    def reserve(self, *, phase: str, model: str, purpose: str) -> int:
        """Atomically claim one slot under the cap; return the row id.

        The count and the insert are a single statement, so concurrent
        callers cannot all observe "under the cap" and then all insert.
        The row is written before the call is made — a request in flight
        has already been paid for and must hold its slot — and `finish()`
        fills in the outcome afterwards.
        """
        row = CallRecord(
            ts=time.time(), phase=phase, model=model, purpose=purpose,
            status=RESERVED_STATUS, tokens_in=0, tokens_out=0, latency_ms=0.0,
        )
        with self._connect() as conn:
            if self._max_calls is None:
                cursor = conn.execute(_INSERT_SQL, _row_values(row))
            else:
                cursor = conn.execute(_INSERT_GUARDED_SQL, (*_row_values(row), self._max_calls))
            if cursor.rowcount == 0:
                raise BudgetExceededError(
                    f"budget exceeded: cap is {self._max_calls} calls, all of them reserved"
                )
            call_id = cursor.lastrowid
        if call_id is None:  # pragma: no cover - sqlite always sets it on INSERT
            raise RuntimeError("sqlite did not return a row id for the reservation")
        return call_id

    def finish(
        self,
        call_id: int,
        *,
        status: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        """Fill in a reserved row's outcome. Never adds a row, so the cap still holds."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE calls SET status = ?, tokens_in = ?, tokens_out = ?, latency_ms = ? "
                "WHERE id = ?",
                (status, tokens_in, tokens_out, latency_ms, call_id),
            )

    def record(self, record: CallRecord) -> None:
        """Record a call that has ALREADY been made. Does not enforce the cap.

        For after-the-fact accounting (the rate-limit ramp records outcomes
        once a window has been fired). Anything that is about to spend a
        call must go through `reserve()` / `finish()` instead, or the cap is
        only advisory.
        """
        with self._connect() as conn:
            conn.execute(_INSERT_SQL, _row_values(record))

    def total_calls(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM calls").fetchone()
            return int(row[0])

    def totals_per_model(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT model, COUNT(*) FROM calls GROUP BY model").fetchall()
            return dict(rows)

    def totals_per_phase(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT phase, COUNT(*) FROM calls GROUP BY phase").fetchall()
            return dict(rows)
