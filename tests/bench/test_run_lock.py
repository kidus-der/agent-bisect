"""One evaluation per runs directory."""

from __future__ import annotations

import json
import os

import pytest
from agent_bisect.bench.run_lock import (
    EvaluationLockedError,
    check_unlocked,
    evaluation_lock,
    lock_path,
)


def test_an_empty_directory_is_unlocked(tmp_path):
    check_unlocked(tmp_path)  # does not raise


def test_holding_the_lock_writes_this_process_pid(tmp_path):
    with evaluation_lock(tmp_path, label="eval --split dev"):
        held = json.loads(lock_path(tmp_path).read_text())

    assert held["pid"] == os.getpid()
    assert held["label"] == "eval --split dev"


def test_a_live_holder_blocks_a_second_evaluation(tmp_path):
    with evaluation_lock(tmp_path), pytest.raises(EvaluationLockedError, match="already"):
        check_unlocked(tmp_path)


def test_the_refusal_names_the_holder_and_what_to_do(tmp_path):
    with evaluation_lock(tmp_path, label="eval --split test"), pytest.raises(
        EvaluationLockedError, match="eval --split test"
    ):
        check_unlocked(tmp_path)


def test_the_lock_is_released_on_the_way_out(tmp_path):
    with evaluation_lock(tmp_path):
        pass

    check_unlocked(tmp_path)
    assert not lock_path(tmp_path).exists()


def test_a_dead_holder_is_stale_not_fatal(tmp_path):
    """A crashed run must not need manual cleanup before the next one resumes."""
    lock_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    lock_path(tmp_path).write_text(
        json.dumps({"pid": 2**30, "started_at": "2026-01-01T00:00:00", "label": "dead"})
    )

    check_unlocked(tmp_path)  # does not raise
    with evaluation_lock(tmp_path):
        assert json.loads(lock_path(tmp_path).read_text())["pid"] == os.getpid()


def test_an_unreadable_lock_is_treated_as_absent(tmp_path):
    lock_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    lock_path(tmp_path).write_text("{not json")

    check_unlocked(tmp_path)  # does not raise


def test_releasing_never_removes_a_newer_run_s_claim(tmp_path):
    """If another run took the lock while we held it, we must not delete theirs."""
    with evaluation_lock(tmp_path):
        lock_path(tmp_path).write_text(
            json.dumps({"pid": 2**30, "started_at": "x", "label": "newer"})
        )

    assert lock_path(tmp_path).exists()
