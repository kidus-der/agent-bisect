"""Tests for agent_bisect.core.budget: the SQLite call ledger and hard-cap guard."""

from __future__ import annotations

import pytest
from agent_bisect.core.budget import BudgetExceededError, BudgetLedger, CallRecord, current_phase
from pydantic import ValidationError


def _record(
    *,
    ts: float = 1.0,
    phase: str = "P0",
    model: str = "some/model",
    purpose: str = "test",
    status: str = "ok",
    tokens_in: int = 10,
    tokens_out: int = 5,
    latency_ms: float = 123.4,
) -> CallRecord:
    return CallRecord(
        ts=ts,
        phase=phase,
        model=model,
        purpose=purpose,
        status=status,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )


def test_call_record_is_frozen():
    record = _record()

    with pytest.raises(ValidationError):
        record.tokens_in = 99  # type: ignore[misc]


def test_ledger_creates_db_file(tmp_path):
    db_path = tmp_path / "sub" / "ledger.sqlite"

    BudgetLedger(db_path)

    assert db_path.exists()


def test_ledger_records_and_counts(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")

    ledger.record(_record())
    ledger.record(_record(model="other/model"))

    assert ledger.total_calls() == 2


def test_ledger_totals_per_model(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")

    ledger.record(_record(model="a"))
    ledger.record(_record(model="a"))
    ledger.record(_record(model="b"))

    assert ledger.totals_per_model() == {"a": 2, "b": 1}


def test_ledger_totals_per_phase(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")

    ledger.record(_record(phase="P0"))
    ledger.record(_record(phase="P0"))
    ledger.record(_record(phase="P1"))

    assert ledger.totals_per_phase() == {"P0": 2, "P1": 1}


def test_check_budget_allows_calls_under_cap(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite", max_calls=2)

    ledger.check_budget()
    ledger.record(_record())
    ledger.check_budget()


def test_check_budget_raises_before_call_at_cap(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite", max_calls=1)
    ledger.record(_record())

    with pytest.raises(BudgetExceededError):
        ledger.check_budget()


def test_check_budget_never_writes_a_row(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite", max_calls=0)

    with pytest.raises(BudgetExceededError):
        ledger.check_budget()

    assert ledger.total_calls() == 0


def test_check_budget_unbounded_when_no_max(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite", max_calls=None)

    for _ in range(5):
        ledger.check_budget()
        ledger.record(_record())

    assert ledger.total_calls() == 5


def test_ledger_survives_reopen(tmp_path):
    db_path = tmp_path / "ledger.sqlite"
    BudgetLedger(db_path).record(_record())

    reopened = BudgetLedger(db_path)

    assert reopened.total_calls() == 1


def test_current_phase_explicit_wins(monkeypatch):
    monkeypatch.setenv("BISECT_PHASE", "P3")

    assert current_phase("P5") == "P5"


def test_current_phase_reads_env(monkeypatch):
    monkeypatch.setenv("BISECT_PHASE", "P3")

    assert current_phase(None) == "P3"


def test_current_phase_defaults_to_unknown(monkeypatch):
    monkeypatch.delenv("BISECT_PHASE", raising=False)

    assert current_phase(None) == "unknown"


def test_ledger_uses_wal_journal_mode(tmp_path):
    db_path = tmp_path / "ledger.sqlite"
    BudgetLedger(db_path)

    import sqlite3

    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    assert mode.lower() == "wal"
