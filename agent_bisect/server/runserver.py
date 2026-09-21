"""`run_server(host, port, data_source)`: the one call `bisect serve` (P6, not yet wired
into `cli.py`) needs. See this package's `__main__.py` for the CLI wrapper around it.
"""

from __future__ import annotations

from pathlib import Path

import uvicorn

from agent_bisect.server.app import create_app
from agent_bisect.server.fixture_repository import DEFAULT_FIXTURE_SEED
from agent_bisect.server.settings import DataSource, ServerSettings

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8484
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class UnsafeHostError(ValueError):
    """Raised when a non-loopback host is requested without explicit opt-in."""


def _validate_host(host: str, explicit: bool) -> None:
    if host in _LOOPBACK_HOSTS:
        return
    if not explicit:
        raise UnsafeHostError(
            f"refusing to bind non-loopback host {host!r} without an explicit --host"
        )
    print(  # noqa: T201 -- an operator-facing warning, not a logging call
        f"WARNING: binding to non-loopback host {host!r} -- the dashboard API will be "
        "reachable from other machines on this network."
    )


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    data_source: DataSource = "fixture",
    *,
    explicit_host: bool = False,
    fixture_seed: int = DEFAULT_FIXTURE_SEED,
    runs_dir: Path = Path("runs"),
    data_dir: Path = Path("data"),
    models_path: Path = Path("config/models.toml"),
) -> None:
    """Build the app and serve it with uvicorn. Blocks until interrupted."""
    _validate_host(host, explicit_host)
    settings = ServerSettings(
        data_source=data_source,
        fixture_seed=fixture_seed,
        runs_dir=runs_dir,
        data_dir=data_dir,
        models_path=models_path,
    )
    app = create_app(settings)
    uvicorn.run(app, host=host, port=port)
