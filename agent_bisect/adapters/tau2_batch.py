"""Recording many tau2 runs: resumable, checkpointed, one tape.

Rule 1 of `docs/brief/summary.md` §3 ends "a crash loses nothing, a resume
pays for nothing twice". That is what this module is: one JSON checkpoint
per `(domain, task, trial)`, written when the run finishes, and a resume
that skips anything already on disk.

An infrastructure failure is **not** a finished run. It lands at
`<task>-t<trial>.error.json` rather than `<task>-t<trial>.json`, which
keeps it visible for diagnosis while leaving the item outstanding, so the
next resume retries it — the same arrangement `scripts/probe_models.py`
uses, and for the same reason: an infra failure scored as an agent failure
is what `docs/decisions/0004-p0-probe-protocol.md` §3 forbids.

`route_tau2_llm` is only safe entered once, single-threaded, around a whole
run, so `recording_session` wraps the entire batch and each worker thread
binds its own recorder (`Tau2Recorder.bind` sets a `ContextVar`).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from agent_bisect.adapters.tau2 import RunSpec, record_run
from agent_bisect.core.config import redact
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import DuplicateRunError, TapeReader, TapeWriter

#: Longest error text kept on a checkpoint. Redacted first, always.
ERROR_CHARS = 400
#: How many run ids a single item may try before giving up. A fresh id is
#: needed only when a previous attempt crashed after writing its manifest.
MAX_ATTEMPTS = 20


@dataclass(frozen=True)
class BatchItem:
    """One unit of work: a task, run once."""

    domain: str
    task_id: str
    trial: int = 0

    @property
    def base_run_id(self) -> str:
        return f"{self.domain}-{self.task_id}-t{self.trial}"

    @property
    def slug(self) -> str:
        return f"{self.task_id}-t{self.trial}"


@dataclass(frozen=True)
class Checkpoint:
    """What one finished attempt is worth remembering."""

    run_id: str
    domain: str
    task_id: str
    trial: int
    status: str
    steps: int
    termination_reason: str
    reward: float | None = None
    passed: bool | None = None
    error: str | None = None
    recorded_at: str = ""

    @property
    def is_done(self) -> bool:
        return self.status == "done"


def tasks_from_range(spec: str) -> list[str]:
    """`"0-19"` or `"0,3,7"` or `"4"` -> a list of task ids, in order."""
    ids: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            ids.extend(str(number) for number in range(int(start), int(end) + 1))
        else:
            ids.append(part)
    return ids


def items_for(domain: str, task_ids: Iterable[str], trials: int = 1) -> list[BatchItem]:
    return [
        BatchItem(domain=domain, task_id=task_id, trial=trial)
        for task_id in task_ids
        for trial in range(trials)
    ]


def checkpoint_dir(root: Path, domain: str) -> Path:
    return root / "record" / domain


def checkpoint_path(root: Path, item: BatchItem) -> Path:
    return checkpoint_dir(root, item.domain) / f"{item.slug}.json"


def load_checkpoint(root: Path, item: BatchItem) -> Checkpoint | None:
    """The finished checkpoint for `item`, or `None` if it still owes a run."""
    path = checkpoint_path(root, item)
    if not path.exists():
        return None
    try:
        return Checkpoint(**json.loads(path.read_text()))
    except (ValueError, TypeError) as exc:
        # An unreadable checkpoint means the item is not done; re-running it
        # is always safe and always cheaper than guessing what it said.
        print(f"  ignoring unreadable checkpoint {path}: {exc}")
        return None


def save_checkpoint(root: Path, checkpoint: Checkpoint) -> Path:
    """Write a finished run's checkpoint, or an infra failure's error file."""
    item = BatchItem(checkpoint.domain, checkpoint.task_id, checkpoint.trial)
    path = checkpoint_path(root, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = redact(json.dumps(asdict(checkpoint), indent=2, sort_keys=True))
    if not checkpoint.is_done:
        error_path = path.with_suffix(".error.json")
        error_path.write_text(payload)
        return error_path
    path.write_text(payload)
    # A task that eventually succeeded is no longer a failure to explain.
    path.with_suffix(".error.json").unlink(missing_ok=True)
    return path


def load_all(root: Path, domain: str) -> list[Checkpoint]:
    """Every finished checkpoint for `domain`, in task order."""
    directory = checkpoint_dir(root, domain)
    if not directory.exists():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".error.json"):
            continue
        try:
            found.append(Checkpoint(**json.loads(path.read_text())))
        except (ValueError, TypeError):
            continue
    return found


def free_run_id(reader: TapeReader, item: BatchItem) -> str:
    """A run id this tape has no manifest for yet.

    Needed only after a crash: an attempt that died mid-run leaves its
    manifest behind without a checkpoint, and the tape is append-only, so
    the retry gets its own id rather than overwriting the evidence.
    """
    from agent_bisect.core.tape import UnknownRunError

    for attempt in range(1, MAX_ATTEMPTS + 1):
        run_id = item.base_run_id if attempt == 1 else f"{item.base_run_id}-a{attempt}"
        try:
            reader.get_manifest(run_id)
        except UnknownRunError:
            return run_id
    raise RuntimeError(f"{item.base_run_id}: {MAX_ATTEMPTS} attempts already on the tape")


def record_one(
    item: BatchItem,
    *,
    spec_for: Callable[[BatchItem], RunSpec],
    store: BlobStore,
    tape: TapeWriter,
    reader: TapeReader,
    root: Path,
) -> Checkpoint:
    """Record one item and checkpoint it. Never raises for a run-level failure."""
    run_id = free_run_id(reader, item)
    error: str | None = None
    try:
        recorded = record_run(spec_for(item), run_id=run_id, store=store, tape=tape)
    except DuplicateRunError:
        raise
    except Exception as exc:  # noqa: BLE001 - an infra failure is data, not a crash
        # Exception, not BaseException: Ctrl+C must stop the batch rather
        # than be written into a checkpoint as if it were a run's outcome.
        checkpoint = Checkpoint(
            run_id=run_id,
            domain=item.domain,
            task_id=item.task_id,
            trial=item.trial,
            status="aborted_infra",
            steps=0,
            termination_reason="infrastructure_error",
            error=redact(f"{type(exc).__name__}: {exc}")[:ERROR_CHARS],
            recorded_at=datetime.now(UTC).isoformat(),
        )
        save_checkpoint(root, checkpoint)
        return checkpoint
    checkpoint = Checkpoint(
        run_id=run_id,
        domain=item.domain,
        task_id=item.task_id,
        trial=item.trial,
        status="aborted_infra" if recorded.aborted_infra else "done",
        steps=recorded.steps,
        termination_reason=recorded.termination_reason,
        reward=None if recorded.outcome is None else recorded.outcome.reward,
        passed=None if recorded.outcome is None else recorded.outcome.passed,
        error=error,
        recorded_at=datetime.now(UTC).isoformat(),
    )
    save_checkpoint(root, checkpoint)
    return checkpoint


def pending(root: Path, items: Sequence[BatchItem]) -> list[BatchItem]:
    """The items with no finished checkpoint yet."""
    return [item for item in items if load_checkpoint(root, item) is None]


def record_batch(
    items: Sequence[BatchItem],
    *,
    spec_for: Callable[[BatchItem], RunSpec],
    store: BlobStore,
    tape: TapeWriter,
    reader: TapeReader,
    root: Path,
    concurrency: int = 1,
    on_done: Callable[[Checkpoint], None] | None = None,
) -> list[Checkpoint]:
    """Record every outstanding item, resuming from whatever is on disk.

    Must be called inside `adapters.tau2.recording_session()`, which is
    entered once for the whole batch.
    """
    done = [checkpoint for item in items if (checkpoint := load_checkpoint(root, item))]
    outstanding = pending(root, items)
    if not outstanding:
        return done

    def run(item: BatchItem) -> Checkpoint:
        checkpoint = record_one(
            item, spec_for=spec_for, store=store, tape=tape, reader=reader, root=root
        )
        if on_done is not None:
            on_done(checkpoint)
        return checkpoint

    if concurrency <= 1:
        done.extend(run(item) for item in outstanding)
        return done
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        done.extend(pool.map(run, outstanding))
    return done


def summarise(checkpoints: Sequence[Checkpoint]) -> dict[str, object]:
    """Counts and pass rate over finished runs only."""
    finished = [checkpoint for checkpoint in checkpoints if checkpoint.is_done]
    passed = [checkpoint for checkpoint in finished if checkpoint.passed]
    return {
        "recorded": len(finished),
        "aborted_infra": len(checkpoints) - len(finished),
        "passed": len(passed),
        "pass_rate": len(passed) / len(finished) if finished else None,
        "steps_total": sum(checkpoint.steps for checkpoint in finished),
    }


def with_task(spec: RunSpec, item: BatchItem) -> RunSpec:
    """`spec` retargeted at `item`'s domain and task."""
    return replace(spec, domain=item.domain, task_id=item.task_id)
