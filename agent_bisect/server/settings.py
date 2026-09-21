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
    #: Real mode only: `data/manifest.json` + `data/results/*` (P3's frozen
    #: dataset, P5's committed evaluation output).
    data_dir: Path = Path("data")
    #: Real mode only: `config/models.toml` (P0's chosen models, for `/api/meta`).
    models_path: Path = Path("config/models.toml")
    cors_origins: tuple[str, ...] = DEV_ORIGINS
