"""Blocks every new INET/INET6 socket for the lifetime of the interpreter.

Python auto-imports `sitecustomize` at startup if its directory is on
`PYTHONPATH` (or `sys.path`), so putting this directory first on
`PYTHONPATH` enforces "no network" on any `python` (or `uv run python`)
process launched with it, the same way `pytest-socket`'s `--disable-socket`
enforces it for the test suite -- without needing to patch every call site.

Unix-domain sockets are left alone (`--allow-unix-socket`'s counterpart):
local IPC that never leaves the machine is not what "offline" means here,
and blocking it would risk breaking tooling that has nothing to do with the
report's own network claim.

Used by `make reproduce-check` (working tree) and `scripts/gates/p8.py`
(clean clone) to enforce, not just document, that `scripts/report/render.py`
and `bisect eval --report-only` make zero network calls.
"""

from __future__ import annotations

import socket

_BLOCKED_FAMILIES = {socket.AF_INET, socket.AF_INET6}
_original_socket = socket.socket


class NetworkBlockedError(RuntimeError):
    """Raised in place of opening a real network socket."""


class _GuardedSocket(_original_socket):  # type: ignore[misc, valid-type]
    def __init__(self, family: int = -1, *args: object, **kwargs: object) -> None:
        resolved = socket.AF_INET if family == -1 else family
        if resolved in _BLOCKED_FAMILIES:
            raise NetworkBlockedError(
                "a network socket was opened during an offline report run "
                "(scripts/report/_offline/sitecustomize.py) -- the report generator "
                "must make zero network calls"
            )
        super().__init__(family, *args, **kwargs)  # type: ignore[arg-type]


socket.socket = _GuardedSocket  # type: ignore[misc]
