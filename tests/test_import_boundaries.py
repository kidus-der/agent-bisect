"""Runs import-linter and asserts the `core` boundary contract holds.

`agent_bisect.core` must never import `attribution`, `bench`, or `gate`
(see `agent_bisect/core/__init__.py` and the `[[tool.importlinter.contracts]]`
entry in `pyproject.toml`). This test enforces it at the process level by
invoking the real `lint-imports` CLI, so a future edit that violates the
boundary fails CI even if no unit test happens to catch the specific
import.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_lint_imports_passes():
    # `importlinter` is a package (no __main__), so invoke its console-script
    # entry point in-process via -c rather than `-m importlinter`.
    entry_point = "from importlinter.cli import lint_imports_command; lint_imports_command()"
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, no untrusted input
        [sys.executable, "-c", entry_point],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"lint-imports failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
