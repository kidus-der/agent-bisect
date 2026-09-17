"""The secret-scanning pre-commit hook must block a staged key, and must fail closed.

The hook is the last thing between a leaked credential and the history, so
it is worth testing as a program rather than trusting by inspection. Every
test runs the real hook script in a throwaway git repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".githooks" / "pre-commit"
# Built at runtime: a literal nvapi-<20+ chars> in source would be blocked by
# this very hook.
SYNTHETIC_KEY = "nvapi" + "-" + "E" * 40


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    return tmp_path


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)], cwd=repo, capture_output=True, text=True, check=False
    )


def test_a_staged_key_is_blocked(repo):
    (repo / "leak.py").write_text(f'KEY = "{SYNTHETIC_KEY}"\n')
    _git(repo, "add", "leak.py")

    result = _run_hook(repo)

    assert result.returncode != 0
    assert "nvapi" in result.stderr


def test_clean_content_is_allowed(repo):
    (repo / "fine.py").write_text("VALUE = 42\n")
    _git(repo, "add", "fine.py")

    assert _run_hook(repo).returncode == 0


def test_an_unstaged_key_does_not_block_the_commit(repo):
    (repo / "fine.py").write_text("VALUE = 42\n")
    _git(repo, "add", "fine.py")
    (repo / "leak.py").write_text(f'KEY = "{SYNTHETIC_KEY}"\n')  # never staged

    assert _run_hook(repo).returncode == 0


def test_a_key_added_to_an_existing_file_is_blocked(repo):
    (repo / "config.py").write_text("VALUE = 42\n")
    _git(repo, "add", "config.py")
    _git(repo, "commit", "-q", "-m", "first")
    (repo / "config.py").write_text(f'VALUE = 42\nKEY = "{SYNTHETIC_KEY}"\n')
    _git(repo, "add", "config.py")

    assert _run_hook(repo).returncode != 0


def test_a_short_nvapi_lookalike_is_not_a_false_positive(repo):
    (repo / "doc.py").write_text('PREFIX = "nvapi-"  # keys start with this\n')
    _git(repo, "add", "doc.py")

    assert _run_hook(repo).returncode == 0


def test_the_hook_fails_closed_when_git_cannot_produce_a_diff(tmp_path):
    """Outside a repository `git diff` errors; the hook must refuse, not wave it through."""
    result = subprocess.run(
        ["bash", str(HOOK)],
        cwd=tmp_path,  # deliberately NOT a git repository
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path)},
    )

    assert result.returncode != 0, "a hook that cannot read the diff must block the commit"


def test_the_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "git will not run a non-executable hook"
