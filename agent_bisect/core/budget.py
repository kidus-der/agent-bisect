"""Call ledger: records every LLM API call to SQLite (WAL) and enforces a hard budget cap.

The ledger is the single source of truth for "how many calls has this
process (or a previous run, via the same file) made". `LLMClient` in
`core.llm` calls `check_budget()` before every attempt — so a call that
would exceed the cap never reaches the network — and `record()` after
every attempt, success or failure.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_LEDGER_PATH = Path("runs/ledger.sqlite")

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
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def check_budget(self) -> None:
        """Raise `BudgetExceededError` if the next call would exceed the hard cap."""
        if self._max_calls is None:
            return
        total = self.total_calls()
        if total >= self._max_calls:
            raise BudgetExceededError(
                f"budget exceeded: {total} calls already recorded, cap is {self._max_calls}"
            )

    def record(self, record: CallRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO calls "
                "(ts, phase, model, purpose, status, tokens_in, tokens_out, latency_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.ts,
                    record.phase,
                    record.model,
                    record.purpose,
                    record.status,
                    record.tokens_in,
                    record.tokens_out,
                    record.latency_ms,
                ),
            )

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
