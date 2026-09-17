"""`ServerSettings`: everything `app.create_app` needs to build one `DashboardRepository`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_bisect.server.fixture_repository import DEFAULT_FIXTURE_SEED

DataSource = Literal["fixture", "real"]

DEV_ORIGINS: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")


@dataclass(frozen=True, slots=True)
class ServerSettings:
    data_source: DataSource = "fixture"
    fixture_seed: int = DEFAULT_FIXTURE_SEED
    runs_dir: Path = Path("runs")
    cors_origins: tuple[str, ...] = DEV_ORIGINS
