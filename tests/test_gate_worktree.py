"""`gate.worktree`: isolated checkouts for `bisect gate`'s two sides.

Runs against this repository's own git history -- `worktree_at` never
touches the caller's working tree (it is a *separate* `git worktree add`
directory), so exercising it here is as safe as `git log`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from agent_bisect.gate.worktree import WorktreeError, verify_ref, worktree_at

REPO = Path(__file__).resolve().parents[1]


def test_verify_ref_resolves_head_to_a_commit_hash():
    commit = verify_ref(REPO, "HEAD")

    assert len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit)


def test_verify_ref_rejects_an_unknown_ref():
    with pytest.raises(WorktreeError, match="does not resolve"):
        verify_ref(REPO, "not-a-real-ref-xyz")


def test_worktree_at_checks_out_a_readable_copy_of_the_repo():
    with worktree_at(REPO, "HEAD", label="test") as path:
        assert path.is_dir()
        assert (path / "pyproject.toml").is_file()
        assert (path / "demo" / "agent_policy.yaml").is_file()


def test_worktree_at_removes_the_directory_on_exit():
    with worktree_at(REPO, "HEAD", label="test") as path:
        recorded_path = path

    assert not recorded_path.exists()


def test_worktree_at_removes_the_directory_even_if_the_body_raises():
    class _Boom(Exception):
        pass

    recorded_path = None
    with pytest.raises(_Boom), worktree_at(REPO, "HEAD", label="test") as path:
        recorded_path = path
        raise _Boom

    assert recorded_path is not None
    assert not recorded_path.exists()


def test_worktree_at_does_not_touch_the_caller_working_tree():
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout

    with worktree_at(REPO, "HEAD", label="test"):
        pass

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    assert before == after


def test_two_worktrees_can_coexist_for_base_and_head():
    with worktree_at(REPO, "HEAD", label="base") as base_path, \
            worktree_at(REPO, "HEAD", label="head") as head_path:
        assert base_path != head_path
        assert base_path.is_dir()
        assert head_path.is_dir()
