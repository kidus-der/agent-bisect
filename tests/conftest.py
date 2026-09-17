"""Shared pytest fixtures.

Nothing here opens a real socket — `--disable-socket` (set in
`pyproject.toml`) enforces that for the whole suite except tests marked
`live`, which are deselected by default.
"""

from __future__ import annotations

import pytest
from agent_bisect.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Every test starts with a fresh `get_settings()` cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Clears bisect/NVIDIA env vars and points `.env` loading at an empty dir."""
    env_vars = (
        "NVIDIA_API_KEY",
        "NVIDIA_BASE_URL",
        "BISECT_RUNS_DIR",
        "BISECT_DATA_DIR",
        "BISECT_PHASE",
    )
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path
