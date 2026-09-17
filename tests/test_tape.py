"""Tests for agent_bisect.core.tape: Step/RunManifest/Outcome models,
canonical_request_hash, and the TapeWriter/TapeReader SQLite index.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

import pytest
from agent_bisect.core.tape import (
    DuplicateOutcomeError,
    DuplicateRunError,
    DuplicateStepError,
    Outcome,
    RunManifest,
    Step,
    TapeReader,
    TapeWriter,
    UnknownRunError,
    UnknownStepError,
    canonical_request_hash,
)
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError


def _manifest(**overrides: Any) -> RunManifest:
    defaults: dict[str, Any] = dict(
        run_id="run-1",
        domain="airline",
        task_id="task-0",
        agent_model="moonshotai/kimi-k2.6",
        user_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        params={"temperature": 0.0},
        seed=42,
        tau2_commit="2174a603f6d014ef94473ffa95957f6ce27100db",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    defaults.update(overrides)
    return RunManifest(**defaults)


def _step(**overrides: Any) -> Step:
    defaults: dict[str, Any] = dict(
        run_id="run-1",
        step_idx=0,
        actor="tool",
        state_before="a" * 64,
        state_after="b" * 64,
        state_hash="c" * 64,
    )
    defaults.update(overrides)
    return Step(**defaults)


# ---- Step ----


def test_step_is_frozen():
    step = _step()

    with pytest.raises(ValidationError):
        step.tool_name = "book_reservation"  # type: ignore[misc]


def test_step_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _step(unknown_field="nope")


def test_step_rejects_negative_step_idx():
    with pytest.raises(ValidationError):
        _step(step_idx=-1)


def test_step_optional_fields_default_to_none():
    step = _step()

    assert step.parent_run_id is None
    assert step.tool_name is None
    assert step.tool_args is None
    assert step.model is None


# ---- Outcome ----


def test_outcome_derives_passed_from_reward_when_omitted():
    passing = Outcome(run_id="run-1", reward=1.0)
    failing = Outcome(run_id="run-1", reward=0.5)

    assert passing.passed is True
    assert failing.passed is False


def test_outcome_accepts_explicit_consistent_passed():
    outcome = Outcome(run_id="run-1", reward=1.0, passed=True)

    assert outcome.passed is True


def test_outcome_rejects_inconsistent_passed():
    with pytest.raises(ValidationError):
        Outcome(run_id="run-1", reward=0.5, passed=True)


# ---- canonical_request_hash ----


def test_canonical_request_hash_stable_under_key_reordering():
    request_a = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0.0}
    request_b = {"temperature": 0.0, "messages": [{"role": "user", "content": "hi"}], "model": "m"}

    assert canonical_request_hash(request_a) == canonical_request_hash(request_b)


def test_canonical_request_hash_excludes_volatile_fields():
    base = {"model": "m", "messages": [], "temperature": 0.0}
    with_volatile = {
        **base,
        "api_key": "nvapi-should-not-matter",
        "api_base": "https://example.invalid",
        "timeout": 30,
        "metadata": {"trace_id": "abc"},
    }

    assert canonical_request_hash(base) == canonical_request_hash(with_volatile)


def test_canonical_request_hash_changes_with_messages():
    request_a = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    request_b = {"model": "m", "messages": [{"role": "user", "content": "bye"}]}

    assert canonical_request_hash(request_a) != canonical_request_hash(request_b)


def test_canonical_request_hash_changes_with_sampling_params():
    base = {"model": "m", "messages": []}

    assert canonical_request_hash({**base, "temperature": 0.0}) != canonical_request_hash(
        {**base, "temperature": 1.0}
    )


_request_dicts = st.fixed_dictionaries(
    {
        "model": st.text(min_size=1, max_size=10),
        "messages": st.lists(
            st.fixed_dictionaries(
                {
                    "role": st.sampled_from(["user", "assistant"]),
                    "content": st.text(max_size=20),
                }
            ),
            max_size=3,
        ),
        "temperature": st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
        "api_key": st.text(max_size=10),
        "metadata": st.dictionaries(st.text(max_size=5), st.text(max_size=5), max_size=3),
    }
)


@given(_request_dicts)
def test_canonical_request_hash_stable_under_full_dict_reordering(request):
    reordered = dict(reversed(list(request.items())))

    assert canonical_request_hash(request) == canonical_request_hash(reordered)


# ---- TapeWriter / TapeReader ----


def test_writer_creates_index_file(tmp_path):
    TapeWriter(tmp_path)

    assert (tmp_path / "index.sqlite").exists()


def test_start_run_then_get_manifest_round_trips(tmp_path):
    writer = TapeWriter(tmp_path)
    manifest = _manifest()

    writer.start_run(manifest)

    reader = TapeReader(tmp_path)
    assert reader.get_manifest("run-1") == manifest


def test_start_run_duplicate_raises(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())

    with pytest.raises(DuplicateRunError):
        writer.start_run(_manifest())


def test_get_manifest_unknown_run_raises(tmp_path):
    TapeWriter(tmp_path)
    reader = TapeReader(tmp_path)

    with pytest.raises(UnknownRunError):
        reader.get_manifest("no-such-run")


def test_append_step_then_get_steps_round_trips(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.append_step(_step(step_idx=0))
    writer.append_step(_step(step_idx=1))

    reader = TapeReader(tmp_path)
    steps = reader.get_steps("run-1")

    assert [s.step_idx for s in steps] == [0, 1]
    assert steps[0] == _step(step_idx=0)


def test_get_steps_are_ordered_by_step_idx_regardless_of_insert_order(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.append_step(_step(step_idx=2))
    writer.append_step(_step(step_idx=0))
    writer.append_step(_step(step_idx=1))

    reader = TapeReader(tmp_path)
    assert [s.step_idx for s in reader.get_steps("run-1")] == [0, 1, 2]


def test_get_steps_empty_for_run_with_no_steps(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())

    reader = TapeReader(tmp_path)
    assert reader.get_steps("run-1") == []


def test_get_step_single(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.append_step(_step(step_idx=5, tool_name="book_reservation"))

    reader = TapeReader(tmp_path)
    assert reader.get_step("run-1", 5).tool_name == "book_reservation"


def test_get_step_unknown_raises(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())

    reader = TapeReader(tmp_path)
    with pytest.raises(UnknownStepError):
        reader.get_step("run-1", 99)


def test_append_step_duplicate_step_idx_raises(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.append_step(_step(step_idx=0))

    with pytest.raises(DuplicateStepError):
        writer.append_step(_step(step_idx=0))


def test_append_step_duplicate_does_not_overwrite_existing_row(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.append_step(_step(step_idx=0, tool_name="original"))

    with pytest.raises(DuplicateStepError):
        writer.append_step(_step(step_idx=0, tool_name="replacement"))

    reader = TapeReader(tmp_path)
    assert reader.get_step("run-1", 0).tool_name == "original"


def test_record_outcome_then_get_outcome_round_trips(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.record_outcome(Outcome(run_id="run-1", reward=1.0))

    reader = TapeReader(tmp_path)
    outcome = reader.get_outcome("run-1")

    assert outcome is not None
    assert outcome.reward == 1.0
    assert outcome.passed is True


def test_get_outcome_none_when_not_recorded(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())

    reader = TapeReader(tmp_path)
    assert reader.get_outcome("run-1") is None


def test_record_outcome_duplicate_raises(tmp_path):
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.record_outcome(Outcome(run_id="run-1", reward=1.0))

    with pytest.raises(DuplicateOutcomeError):
        writer.record_outcome(Outcome(run_id="run-1", reward=0.0))


def test_index_uses_wal_journal_mode(tmp_path):
    TapeWriter(tmp_path)

    conn = sqlite3.connect(tmp_path / "index.sqlite")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    assert mode.lower() == "wal"


def test_writer_survives_reopen(tmp_path):
    TapeWriter(tmp_path).start_run(_manifest())

    reopened_writer = TapeWriter(tmp_path)
    reopened_writer.append_step(_step(step_idx=0))

    reader = TapeReader(tmp_path)
    assert reader.get_manifest("run-1").run_id == "run-1"
    assert len(reader.get_steps("run-1")) == 1


def test_append_step_redacts_key_material_in_tool_args(tmp_path):
    fake_key = "nvapi-" + "a" * 40
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    writer.append_step(_step(step_idx=0, tool_args={"note": f"leaked: {fake_key}"}))

    # Scan the main db file and its WAL sidecar (a WAL-mode write may not be
    # checkpointed into the main file yet) -- the key must be in neither.
    for db_file in tmp_path.glob("index.sqlite*"):
        assert fake_key.encode() not in db_file.read_bytes()

    reader = TapeReader(tmp_path)
    assert fake_key not in (reader.get_step("run-1", 0).tool_args or {}).get("note", "")


def test_append_step_from_concurrent_threads_records_every_step(tmp_path):
    """Simulates tau2's own worker threads calling append_step concurrently."""
    writer = TapeWriter(tmp_path)
    writer.start_run(_manifest())
    num_steps = 20
    errors: list[BaseException] = []

    def _append(idx: int) -> None:
        try:
            writer.append_step(_step(step_idx=idx))
        except BaseException as exc:  # noqa: BLE001 - collected and re-raised on the main thread
            errors.append(exc)

    threads = [threading.Thread(target=_append, args=(i,)) for i in range(num_steps)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    reader = TapeReader(tmp_path)
    assert sorted(s.step_idx for s in reader.get_steps("run-1")) == list(range(num_steps))
