"""Tests for agent_bisect.adapters.tau2_env: TAU2_DATA_DIR resolution."""

from __future__ import annotations

from pathlib import Path

from agent_bisect.adapters.tau2_env import DEFAULT_TAU2_DATA_DIR, ensure_tau2_data_dir


def test_ensure_tau2_data_dir_sets_env_var_when_unset(monkeypatch):
    monkeypatch.delenv("TAU2_DATA_DIR", raising=False)

    resolved = ensure_tau2_data_dir()

    assert resolved == DEFAULT_TAU2_DATA_DIR
    import os

    assert os.environ["TAU2_DATA_DIR"] == str(DEFAULT_TAU2_DATA_DIR)


def test_ensure_tau2_data_dir_never_overrides_existing(monkeypatch):
    monkeypatch.setenv("TAU2_DATA_DIR", "/some/other/path")

    resolved = ensure_tau2_data_dir()

    assert resolved == Path("/some/other/path")


def test_ensure_tau2_data_dir_accepts_explicit_override(monkeypatch, tmp_path):
    monkeypatch.delenv("TAU2_DATA_DIR", raising=False)

    resolved = ensure_tau2_data_dir(tmp_path)

    assert resolved == tmp_path


def test_default_tau2_data_dir_points_at_vendored_checkout():
    assert DEFAULT_TAU2_DATA_DIR.parts[-3:] == ("vendor", "tau2-bench", "data")
