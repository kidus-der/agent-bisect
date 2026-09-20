"""One evaluation per runs directory, enforced by a pid lock.

Killing a supervisor used to leave its `bisect eval` child running, so a
"relaunch" added a second evaluation against the same tape under the same
seed. Each then treated the other's in-flight forks as resumable work:
throughput readings swung by 4x, the status file was rewritten by an older
process, and the pace looked like provider flakiness for hours. Two
evaluations sharing a tape is never intended, so the code refuses it.

The lock holds a pid. A lock whose process is gone is **stale, not
fatal** — a crashed run must not require manual cleanup before the next
one can resume — so it is reclaimed with a note rather than an error.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

LOCK_NAME = "eval.lock"


class EvaluationLockedError(RuntimeError):
    """Another evaluation is already running against this runs directory."""


def lock_path(runs_dir: Path) -> Path:
    return runs_dir / LOCK_NAME


def _alive(pid: int) -> bool:
    """Whether `pid` is a live process this user could signal."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _holder(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check_unlocked(runs_dir: Path) -> None:
    """Raise if a live evaluation already holds this runs directory."""
    held = _holder(lock_path(runs_dir))
    if held is not None and _alive(int(held.get("pid", -1))):
        raise EvaluationLockedError(
            f"another evaluation (pid {held.get('pid')}, started "
            f"{held.get('started_at')}, {held.get('label') or 'no label'}) is already "
            f"running against {runs_dir}. Two evaluations on one tape corrupt each "
            f"other's pace and fork reuse. Stop it first, or remove "
            f"{lock_path(runs_dir)} if you are certain it is dead."
        )


@contextmanager
def evaluation_lock(runs_dir: Path, *, label: str = "") -> Iterator[Path]:
    """Hold the evaluation lock for `runs_dir`, or refuse to start."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    check_unlocked(runs_dir)
    path = lock_path(runs_dir)
    path.write_text(
        json.dumps(
            {"pid": os.getpid(), "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "label": label},
            indent=2, sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        yield path
    finally:
        # Only ever release our own lock: a crash elsewhere must not let
        # this process delete a newer run's claim.
        current = _holder(path)
        if current is not None and current.get("pid") == os.getpid():
            path.unlink(missing_ok=True)
