"""P8 gate: report reproducibility, in a clean clone, network blocked."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.gates import p8


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """A minimal git repo, just enough for `check_byte_identical` to have something to check."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    tracked = repo / "docs" / "report.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("committed content\n", encoding="utf-8")
    _git(repo, "add", "docs/report.md")
    _git(repo, "commit", "--quiet", "-m", "initial")
    return repo


def test_check_byte_identical_passes_on_a_clean_tree(tiny_repo: Path) -> None:
    criterion = p8.check_byte_identical(tiny_repo)
    assert criterion.passed, criterion.detail


def test_check_byte_identical_fails_when_a_regenerated_path_changed(tiny_repo: Path) -> None:
    (tiny_repo / "docs" / "report.md").write_text("regenerated differently\n", encoding="utf-8")
    criterion = p8.check_byte_identical(tiny_repo)
    assert not criterion.passed
    assert "docs/report.md" in criterion.detail or "differ" in criterion.detail


def test_clone_repo_copies_a_local_path_with_no_network(tmp_path: Path) -> None:
    """The gate's own `clone_repo` against a throwaway local repo, not the real one."""
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "--quiet")
    _git(source, "config", "user.email", "test@example.com")
    _git(source, "config", "user.name", "Test")
    (source / "x.txt").write_text("hi\n", encoding="utf-8")
    _git(source, "add", "x.txt")
    _git(source, "commit", "--quiet", "-m", "c")

    dest = tmp_path / "clone"
    original_repo_root = p8.REPO_ROOT
    p8.REPO_ROOT = source
    try:
        criterion = p8.clone_repo(dest)
    finally:
        p8.REPO_ROOT = original_repo_root
    assert criterion.passed, criterion.detail
    assert (dest / "x.txt").exists()


def test_write_report_shape(tmp_path: Path) -> None:
    criteria = [p8.Criterion("a", True, "ok"), p8.Criterion("b", False, "nope")]
    path = p8.write_report(criteria, tmp_path)
    import json

    data = json.loads(path.read_text())
    assert data["gate"] == "P8"
    assert data["passed"] is False
    assert [c["name"] for c in data["criteria"]] == ["a", "b"]


def test_full_gate_passes_against_the_real_repository() -> None:
    """The real, end-to-end check: clone this repository, render offline, byte-diff.

    Slower than the rest of the suite (a real `git clone` and `uv run`
    subprocess), but this integration is exactly what the P8 gate exists to
    prove, and `scripts/report/render.py` makes no network call to slow it
    down further.
    """
    criteria, _ = p8.run_gate()
    for criterion in criteria:
        assert criterion.passed, f"{criterion.name}: {criterion.detail}"
