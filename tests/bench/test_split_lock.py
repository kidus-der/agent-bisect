"""The test split opens once, and only after tuning is declared finished."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from agent_bisect.bench.split_lock import (
    MARKER_NAME,
    SplitLockedError,
    guard,
    marker_path,
    open_test_split,
)

WHEN = datetime(2026, 9, 17, 14, 30, tzinfo=UTC)


@pytest.fixture
def decision(tmp_path):
    path = tmp_path / "0014-p5-freeze.md"
    path.write_text("tuning finished on dev")
    return path


def test_the_dev_split_is_never_locked(tmp_path):
    # Arrange / Act / Assert
    assert guard("dev", tmp_path, decision=tmp_path / "absent.md") is None


def test_the_test_split_is_refused_without_the_freeze_decision(tmp_path):
    # Arrange / Act / Assert
    with pytest.raises(SplitLockedError, match="does not exist"):
        guard("test", tmp_path, decision=tmp_path / "absent.md")


def test_the_refusal_says_what_to_do_about_it(tmp_path):
    # Arrange / Act / Assert
    with pytest.raises(SplitLockedError, match="tuning is finished"):
        guard("test", tmp_path, decision=tmp_path / "absent.md")


def test_the_first_opening_succeeds_and_is_not_a_resume(tmp_path, decision):
    # Arrange / Act
    opening = open_test_split(tmp_path, now=WHEN, decision=decision)

    # Assert
    assert opening.resumed is False
    assert opening.opened_at == WHEN.isoformat()


def test_the_first_opening_writes_a_marker_recording_when(tmp_path, decision):
    # Arrange / Act
    open_test_split(tmp_path, now=WHEN, decision=decision)

    # Assert
    recorded = json.loads(marker_path(tmp_path).read_text())
    assert recorded["opened_at"] == WHEN.isoformat()
    assert recorded["split"] == "test"


def test_a_second_full_run_is_refused(tmp_path, decision):
    # Arrange
    open_test_split(tmp_path, now=WHEN, decision=decision)

    # Act / Assert
    with pytest.raises(SplitLockedError, match="already opened"):
        open_test_split(tmp_path, now=WHEN, decision=decision)


def test_the_refusal_names_when_it_was_opened(tmp_path, decision):
    # Arrange
    open_test_split(tmp_path, now=WHEN, decision=decision)

    # Act / Assert
    with pytest.raises(SplitLockedError, match="2026-09-17"):
        open_test_split(tmp_path, now=WHEN, decision=decision)


def test_a_resume_is_allowed_and_keeps_the_original_opening_time(tmp_path, decision):
    # Arrange
    open_test_split(tmp_path, now=WHEN, decision=decision)
    later = datetime(2026, 9, 18, tzinfo=UTC)

    # Act
    resumed = open_test_split(tmp_path, resume=True, now=later, decision=decision)

    # Assert
    assert resumed.resumed is True
    assert resumed.opened_at == WHEN.isoformat()


def test_a_resume_does_not_rewrite_the_marker(tmp_path, decision):
    # Arrange
    open_test_split(tmp_path, now=WHEN, decision=decision)
    before = marker_path(tmp_path).read_bytes()

    # Act
    open_test_split(tmp_path, resume=True, now=datetime(2026, 9, 18, tzinfo=UTC),
                    decision=decision)

    # Assert
    assert marker_path(tmp_path).read_bytes() == before


def test_a_resume_still_needs_the_freeze_decision(tmp_path, decision):
    # Arrange
    open_test_split(tmp_path, now=WHEN, decision=decision)
    decision.unlink()

    # Act / Assert
    with pytest.raises(SplitLockedError):
        open_test_split(tmp_path, resume=True, decision=decision)


def test_the_marker_lives_beside_the_results(tmp_path, decision):
    # Arrange / Act
    open_test_split(tmp_path, now=WHEN, decision=decision)

    # Assert
    assert (tmp_path / MARKER_NAME).exists()


def test_the_output_directory_is_created_if_it_is_missing(tmp_path, decision):
    # Arrange
    out_dir = tmp_path / "runs" / "p5"

    # Act
    open_test_split(out_dir, now=WHEN, decision=decision)

    # Assert
    assert marker_path(out_dir).exists()
