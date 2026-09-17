"""Tests for agent_bisect.core.snapshot: the Snapshotter protocol and InMemorySnapshotter fake."""

from __future__ import annotations

from agent_bisect.core.snapshot import InMemorySnapshotter, Snapshotter


def test_in_memory_snapshotter_satisfies_the_protocol():
    assert isinstance(InMemorySnapshotter(), Snapshotter)


def test_capture_returns_the_initial_state():
    snapshotter = InMemorySnapshotter({"count": 1})

    assert snapshotter.capture() == {"count": 1}


def test_capture_defaults_to_empty_dict():
    assert InMemorySnapshotter().capture() == {}


def test_restore_replaces_the_current_state():
    snapshotter = InMemorySnapshotter({"count": 1})

    snapshotter.restore({"count": 99})

    assert snapshotter.capture() == {"count": 99}


def test_capture_is_a_deep_copy_not_a_reference():
    snapshotter = InMemorySnapshotter({"nested": {"count": 1}})

    captured = snapshotter.capture()
    captured["nested"]["count"] = 999

    assert snapshotter.capture() == {"nested": {"count": 1}}


def test_restore_is_a_deep_copy_not_a_reference():
    snapshotter = InMemorySnapshotter()
    state = {"nested": {"count": 1}}

    snapshotter.restore(state)
    state["nested"]["count"] = 999

    assert snapshotter.capture() == {"nested": {"count": 1}}


def test_state_hash_is_deterministic_for_equal_state():
    snapshotter_a = InMemorySnapshotter({"a": 1, "b": 2})
    snapshotter_b = InMemorySnapshotter({"b": 2, "a": 1})

    assert snapshotter_a.state_hash() == snapshotter_b.state_hash()


def test_state_hash_changes_after_restore_to_different_state():
    snapshotter = InMemorySnapshotter({"count": 1})
    hash_before = snapshotter.state_hash()

    snapshotter.restore({"count": 2})

    assert snapshotter.state_hash() != hash_before


def test_state_hash_matches_after_capture_restore_round_trip():
    snapshotter = InMemorySnapshotter({"count": 1, "items": [1, 2, 3]})
    hash_before = snapshotter.state_hash()
    captured = snapshotter.capture()

    snapshotter.restore({"count": 2, "items": []})
    snapshotter.restore(captured)

    assert snapshotter.state_hash() == hash_before
