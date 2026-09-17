"""Shared pytest fixtures.

Nothing here opens a real socket — `--disable-socket` (set in
`pyproject.toml`) enforces that for the whole suite except tests marked
`live`, which are deselected by default.
"""

from __future__ import annotations

import pytest
from agent_bisect.core.config import get_settings


@pytest.fixture(autouse=True)
def _no_real_key(request, monkeypatch, tmp_path_factory):
    """Structurally prevent any test from loading the developer's real key.

    Pytest runs from the repo root, so anything calling `get_settings()`
    without chdir'ing would otherwise discover the repo's own `.env` and
    load the live key — which is exactly how it ended up printed in an
    assertion diff. Pointing `BISECT_ENV_FILE` at a path that does not
    exist makes discovery impossible rather than merely unlikely.

    Tests marked `live` opt out: they are deselected by default and are the
    only ones allowed to talk to the real API.
    """
    get_settings.cache_clear()
    if request.node.get_closest_marker("live") is None:
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        absent = tmp_path_factory.mktemp("noenv") / "absent.env"
        monkeypatch.setenv("BISECT_ENV_FILE", str(absent))
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
