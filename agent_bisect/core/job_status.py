"""`runs/<phase>/status.json`: how a long job tells the dashboard where it is.

The Live page reads one status file per phase directory — the convention
in `docs/design/api-contract.md`, "Real mode's `runs/<phase>/status.json`"
— and `server.schemas_live.JobStatus` refuses a file whose state
disagrees with its progress or timestamps: a job cannot be `queued` at
77%, `done` without a finish time, or `failed` without a reason.

Rather than leave every long job to satisfy that by hand, this is the one
place a status is built, and the invariants are enforced here. `core/`
knows nothing of the server, so nothing is imported from it; the shape is
a plain JSON dict, and `tests/test_job_status.py` pins that what this
writes is what `JobStatus` accepts.

Writes are atomic (temp file + `os.replace`): the dashboard polls this
file while the job is writing it, and a half-written JSON document would
be reported as a job that vanished.

Shared by the P1 recorder, the P3 collection and the P5 evaluation.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATUS_NAME = "status.json"
#: `JobStatus` requires a running job to be strictly inside (0, 1), so a
#: job that has just started, or has finished its items but not its work,
#: still reports something the dashboard will accept.
RUNNING_MIN = 0.001
RUNNING_MAX = 0.999


class JobStatusError(ValueError):
    """This status could not be written: it contradicts itself."""


def status_path(runs_dir: Path, phase: str) -> Path:
    """`runs/<phase>/status.json`, with the phase lower-cased as on disk."""
    return Path(runs_dir) / phase.lower() / STATUS_NAME


def now() -> str:
    return datetime.now(UTC).isoformat()


def progress_for(items_done: int, items_total: int) -> float:
    """The share of items finished, clamped to 0..1. No items means 0."""
    if items_total <= 0:
        return 0.0
    return min(1.0, max(0.0, items_done / items_total))


def _base(kind: str, **fields: Any) -> dict[str, Any]:
    status: dict[str, Any] = {
        "kind": kind,
        "phase": None,
        "label": None,
        "items_done": None,
        "items_total": None,
        "model": None,
        "calls_spent": None,
        "started_at": None,
        "finished_at": None,
        "eta_seconds": None,
        "last_checkpoint_at": None,
        "error": None,
    }
    status.update({key: value for key, value in fields.items() if key != "kind"})
    return status


def queued(*, kind: str, **fields: Any) -> dict[str, Any]:
    """A job that exists but has not begun."""
    return validated(
        {**_base(kind, **fields), "state": "queued", "progress": 0.0, "started_at": None}
    )


def running(
    *, kind: str, items_done: int = 0, items_total: int = 0, **fields: Any
) -> dict[str, Any]:
    """A job in flight. Progress is pulled inside (0, 1) if it lands on an end."""
    share = progress_for(items_done, items_total)
    return validated(
        {
            **_base(kind, items_done=items_done, items_total=items_total, **fields),
            "state": "running",
            "progress": min(RUNNING_MAX, max(RUNNING_MIN, share)),
            "started_at": fields.get("started_at") or now(),
            "last_checkpoint_at": fields.get("last_checkpoint_at") or now(),
        }
    )


def done(*, kind: str, **fields: Any) -> dict[str, Any]:
    """A job that finished its work."""
    return validated(
        {
            **_base(kind, **fields),
            "state": "done",
            "progress": 1.0,
            "finished_at": fields.get("finished_at") or now(),
        }
    )


def failed(*, kind: str, error: str, **fields: Any) -> dict[str, Any]:
    """A job that stopped on something it could not continue through."""
    if not error:
        return _refuse("a failed job must carry the reason it failed")
    return validated(
        {
            **_base(kind, **fields),
            "state": "failed",
            "progress": fields.get("progress", 0.0),
            "error": error,
            "finished_at": fields.get("finished_at") or now(),
        }
    )


def validated(status: dict[str, Any]) -> dict[str, Any]:
    """The same invariants `JobStatus` enforces, checked before writing."""
    state = status.get("state")
    progress = float(status.get("progress", 0.0))
    if state not in {"queued", "running", "done", "failed"}:
        return _refuse(f"unknown job state {state!r}")
    if state == "queued" and (progress != 0.0 or status.get("started_at") is not None):
        return _refuse("a queued job has progress 0.0 and has not started")
    if state == "running" and not 0.0 < progress < 1.0:
        return _refuse(f"a running job has progress strictly inside (0, 1), got {progress}")
    if state == "done":
        if progress != 1.0:
            return _refuse(f"a done job has progress 1.0, got {progress}")
        if status.get("finished_at") is None:
            return _refuse("a done job has finished_at set")
    if state == "failed" and not status.get("error"):
        return _refuse("a failed job must carry the reason it failed")
    return status


def _refuse(message: str) -> Any:
    raise JobStatusError(message)


def write_status(runs_dir: Path, status: dict[str, Any], *, phase: str | None = None) -> Path:
    """Write `status` to `runs/<phase>/status.json`, atomically.

    The phase comes from the status itself unless given; a status with
    neither is written to `runs/unknown/`, which is visible rather than
    silently lost.
    """
    resolved = phase or status.get("phase") or "unknown"
    path = status_path(runs_dir, str(resolved))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(validated(status), indent=2, sort_keys=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return path
