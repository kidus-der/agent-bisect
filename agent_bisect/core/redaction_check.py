"""A reusable redaction check: record one run with a key threaded through
every payload shape a real leak could take, then scan everything the
recording wrote for it.

Shared by `tests/test_p1_redaction.py` (assertion-per-artifact) and
`scripts/gates/p1_offline.py` (single PASS/FAIL for the P1 gate), so the
two never drift on what "recorded with the key everywhere" means.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Outcome, RunManifest, Step, TapeWriter

_RUN_ID = "run-redaction-check"


def record_run_with_key_everywhere(root: Path, key: str) -> None:
    """Writes one run whose request/response/tool-result blobs and whose
    Step's direct (non-blob) fields all contain `key` -- the shape a real
    leak (an API error echoing the key back, or a bug threading it into
    tool_args) would take.
    """
    blobs = BlobStore(root)
    tape = TapeWriter(root)

    request_ref = blobs.put_json(
        {"model": "m", "messages": [{"role": "system", "content": f"Authorization: Bearer {key}"}]}
    )
    response_ref = blobs.put_json({"content": f"upstream error, key was {key}, please retry"})
    tool_result_ref = blobs.put_json({"result": f"echoed header: {key}"})

    tape.start_run(
        RunManifest(
            run_id=_RUN_ID,
            domain="airline",
            task_id="task-0",
            agent_model="m",
            user_model="m",
            params={"note": f"seen key {key}"},
            tau2_commit="2174a603f6d014ef94473ffa95957f6ce27100db",
            created_at=datetime(2026, 9, 17, tzinfo=UTC),
        )
    )
    tape.append_step(
        Step(
            run_id=_RUN_ID,
            step_idx=0,
            actor="agent",
            request_hash="a" * 64,
            request_ref=request_ref,
            response_ref=response_ref,
            tool_name="book_reservation",
            tool_args={"note": f"leaked in args: {key}"},
            tool_result_ref=tool_result_ref,
            state_before="b" * 64,
            state_after="c" * 64,
            state_hash="d" * 64,
            model="m",
            params={"also_leaked": key},
        )
    )
    tape.record_outcome(Outcome(run_id=_RUN_ID, reward=1.0))


def every_blob_decompressed(root: Path) -> list[bytes]:
    blobs = BlobStore(root)
    return [
        blobs.get_bytes(path.stem) for path in sorted((root / "blobs").glob("**/*.zst"))
    ]


def every_sqlite_file_bytes(root: Path) -> list[bytes]:
    return [path.read_bytes() for path in sorted(root.glob("index.sqlite*"))]


def key_absent_everywhere(root: Path, key: str) -> tuple[bool, str]:
    """Scans every blob and every SQLite index file under `root` for `key`.

    Returns `(True, "")` if the key was found nowhere, else
    `(False, detail)` naming the first artifact where it was found.
    """
    key_bytes = key.encode("utf-8")
    for path in sorted((root / "blobs").glob("**/*.zst")):
        blobs = BlobStore(root)
        if key_bytes in blobs.get_bytes(path.stem):
            return False, f"key found in blob {path.name}"
    for path in sorted(root.glob("index.sqlite*")):
        if key_bytes in path.read_bytes():
            return False, f"key found in {path.name}"
    return True, ""
