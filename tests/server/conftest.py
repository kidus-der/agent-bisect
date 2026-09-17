"""Shared fixtures for `tests/server/`. All offline: `TestClient` drives the ASGI
app in-process, never a real socket, so it's unaffected by `--disable-socket`.
"""

from __future__ import annotations

import pytest
from agent_bisect.server.app import create_app
from agent_bisect.server.fixture_repository import FixtureRepository
from agent_bisect.server.settings import ServerSettings
from fastapi.testclient import TestClient

TEST_SEED = 20260917


@pytest.fixture(scope="session")
def fixture_repo() -> FixtureRepository:
    """Built once per test session: fixture generation is deterministic and pure,
    and rebuilding it (~264 synthetic runs, each running the real estimator three
    ways) for every single test would make the suite unusably slow."""
    return FixtureRepository(seed=TEST_SEED)


@pytest.fixture(scope="session")
def fixture_app():
    return create_app(ServerSettings(data_source="fixture", fixture_seed=TEST_SEED))


@pytest.fixture(scope="session")
def client(fixture_app) -> TestClient:
    return TestClient(fixture_app)
