"""Two throwaway git worktrees, one per side of a `bisect gate` comparison.

`bisect gate --base <ref> --head <ref>` runs the demo suite once per ref,
and each run needs its *own* checkout of `demo/` and `agent_bisect/` --
that is the whole point of comparing a PR's policy edit against what it
changed from. A worktree gives that without touching the caller's working
tree: `git worktree add` checks a ref out into a fresh temporary directory,
and `git worktree remove` (with `git worktree prune` as a fallback for a
directory a crashed process left behind) cleans it up.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class WorktreeError(RuntimeError):
    """A git worktree operation failed. Carries the command's stderr."""


def _run(args: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, shell=False, check=False
    )
    if result.returncode != 0:
        raise WorktreeError(f"{' '.join(args)} (in {cwd}) failed: {result.stderr.strip()}")
    return result.stdout


def verify_ref(repo: Path, ref: str) -> str:
    """The commit `ref` resolves to, or a `WorktreeError` if it does not exist.

    Called before anything touches the filesystem: a ref that does not
    resolve must never reach `git worktree add`, whose own error is far
    less clear about which of `--base`/`--head` was the problem.
    """
    try:
        return _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo).strip()
    except WorktreeError as exc:
        raise WorktreeError(f"ref {ref!r} does not resolve to a commit in {repo}: {exc}") from exc


@contextmanager
def worktree_at(repo: Path, ref: str, *, label: str) -> Iterator[Path]:
    """A worktree checking out `ref`, removed on exit even if the body raises.

    `ref` is resolved to a commit hash first and that hash — never the
    ref string itself — is what `git worktree add` checks out, so a
    caller-controlled branch name can never be interpreted as a flag
    (`git worktree add <path> -- <commit>` would still be safer against a
    hostile *path*, which is ours, not the ref's, so this is the guard that
    matters here).
    """
    commit = verify_ref(repo, ref)
    with tempfile.TemporaryDirectory(prefix=f"bisect-gate-{label}-") as tmp:
        path = Path(tmp) / "worktree"
        _run(
            ["git", "worktree", "add", "--detach", str(path), commit],
            cwd=repo,
        )
        try:
            yield path
        finally:
            _cleanup(repo, path)


def _cleanup(repo: Path, path: Path) -> None:
    try:
        _run(["git", "worktree", "remove", "--force", str(path)], cwd=repo)
    except WorktreeError:
        # The directory may already be gone (the TemporaryDirectory context
        # is about to remove it regardless) or git's own bookkeeping may be
        # stale from a previous crash; `prune` reconciles either case
        # without needing the path to still exist.
        _run(["git", "worktree", "prune"], cwd=repo)
