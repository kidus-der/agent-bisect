"""The hard cap must hold under concurrency, not just in a single thread.

`check_budget()` (SELECT COUNT) followed by `record()` (INSERT) is a
read-then-write race: every thread can pass the check before any of them
inserts, and the cap is then overshot by however many were in flight. τ²
runs its tasks in a thread pool, so this is the normal case, not an edge
one. `reserve()` has to do both halves in one atomic statement.
"""

from __future__ import annotations

import threading

import pytest
from agent_bisect.core.budget import BudgetExceededError, BudgetLedger

CAP = 10
RACERS = 32


def _ledger(tmp_path, cap: int | None = CAP) -> BudgetLedger:
    return BudgetLedger(tmp_path / "ledger.sqlite", max_calls=cap)


def test_exactly_the_cap_is_granted_when_many_threads_race(tmp_path):
    ledger = _ledger(tmp_path)
    granted: list[int] = []
    refused: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(RACERS)

    def racer():
        barrier.wait()
        try:
            call_id = ledger.reserve(phase="P0", model="m", purpose="test")
        except BudgetExceededError as exc:
            with lock:
                refused.append(exc)
            return
        with lock:
            granted.append(call_id)

    threads = [threading.Thread(target=racer) for _ in range(RACERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(granted) == CAP
    assert len(refused) == RACERS - CAP
    assert ledger.total_calls() == CAP


def test_every_granted_reservation_has_a_distinct_row(tmp_path):
    ledger = _ledger(tmp_path)

    ids = [ledger.reserve(phase="P0", model="m", purpose="test") for _ in range(CAP)]

    assert len(set(ids)) == CAP


def test_reserving_past_the_cap_raises_rather_than_recording(tmp_path):
    ledger = _ledger(tmp_path, cap=1)
    ledger.reserve(phase="P0", model="m", purpose="test")

    with pytest.raises(BudgetExceededError, match="cap"):
        ledger.reserve(phase="P0", model="m", purpose="test")

    assert ledger.total_calls() == 1


def test_an_unlimited_ledger_never_refuses(tmp_path):
    ledger = _ledger(tmp_path, cap=None)

    for _ in range(RACERS):
        ledger.reserve(phase="P0", model="m", purpose="test")

    assert ledger.total_calls() == RACERS


def test_finish_updates_the_reserved_row_instead_of_adding_one(tmp_path):
    ledger = _ledger(tmp_path)
    call_id = ledger.reserve(phase="P0", model="m", purpose="test")

    ledger.finish(call_id, status="ok", tokens_in=7, tokens_out=3, latency_ms=12.5)

    assert ledger.total_calls() == 1
    assert ledger.totals_per_model() == {"m": 1}


def test_a_reservation_counts_against_the_cap_before_it_finishes(tmp_path):
    """A call in flight has already been paid for; it must hold its slot."""
    ledger = _ledger(tmp_path, cap=1)
    ledger.reserve(phase="P0", model="m", purpose="test")

    with pytest.raises(BudgetExceededError):
        ledger.reserve(phase="P0", model="m", purpose="test")


def test_concurrent_writers_do_not_trip_over_a_locked_database(tmp_path):
    """Short-lived per-operation connections plus WAL and a busy timeout."""
    ledger = _ledger(tmp_path, cap=None)
    errors: list[BaseException] = []
    barrier = threading.Barrier(RACERS)

    def racer():
        barrier.wait()
        try:
            call_id = ledger.reserve(phase="P0", model="m", purpose="test")
            ledger.finish(call_id, status="ok", tokens_in=1, tokens_out=1, latency_ms=1.0)
        except BaseException as exc:  # noqa: BLE001 - any failure is the finding
            errors.append(exc)

    threads = [threading.Thread(target=racer) for _ in range(RACERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert ledger.total_calls() == RACERS
