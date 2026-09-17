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


def test_core_never_imports_tau2_or_an_adapter():
    """The other half of "a core that knows nothing".

    import-linter's graph only covers `agent_bisect`, so the tau2 half of
    the boundary is checked here: `core/` must be importable, and must
    stay importable, without tau2 on the path at all -- that is what lets
    Branchpoint reuse it, and what keeps a domain's data model out of the
    replay engine.
    """
    probe = (
        "import sys; sys.modules['tau2'] = None\n"
        "import importlib, pkgutil\n"
        "import agent_bisect.core as core\n"
        "for module in pkgutil.iter_modules(core.__path__):\n"
        "    importlib.import_module(f'agent_bisect.core.{module.name}')\n"
        "leaked = sorted(\n"
        "    name for name in sys.modules\n"
        "    if name.startswith(('tau2.', 'agent_bisect.adapters'))\n"
        ")\n"
        "assert not leaked, leaked\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, no untrusted input
        [sys.executable, "-c", probe],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"core reached outside itself:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
