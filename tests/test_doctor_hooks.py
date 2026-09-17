"""`bisect doctor` must notice when the secret-scanning hook is not wired up.

`.githooks/pre-commit` exists in the repository but git ignores it until
`core.hooksPath` points there, which a fresh clone does not do. Silently
having no secret scanning is worse than having none, so the doctor says so
and names the fix.
"""

from __future__ import annotations

import pytest
from agent_bisect.core.doctor import (
    EXPECTED_HOOKS_PATH,
    HOOKS_FIX_COMMAND,
    evaluate_git_hooks,
)


def test_passes_when_the_hooks_path_points_at_the_repo_hooks():
    result = evaluate_git_hooks(EXPECTED_HOOKS_PATH)

    assert result.passed is True
    assert EXPECTED_HOOKS_PATH in result.detail


def test_fails_on_a_fresh_clone_where_the_hooks_path_is_unset():
    result = evaluate_git_hooks(None)

    assert result.passed is False
    assert "unset" in result.detail


def test_the_failure_explains_the_consequence_and_the_fix():
    result = evaluate_git_hooks(None)

    assert "API key" in result.detail
    assert HOOKS_FIX_COMMAND in result.detail


@pytest.mark.parametrize("path", [".git/hooks", "/somewhere/else", ""])
def test_fails_when_the_hooks_path_points_somewhere_else(path):
    assert evaluate_git_hooks(path).passed is False


def test_make_setup_wires_the_hooks_path():
    """The fix the doctor names has to exist in the Makefile."""
    from pathlib import Path

    makefile = Path("Makefile").read_text()

    assert "setup:" in makefile
    assert "core.hooksPath .githooks" in makefile
