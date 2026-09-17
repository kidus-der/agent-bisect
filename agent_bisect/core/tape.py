"""Step records and the append-only tape: `Step`, `RunManifest`, `Outcome`,
`canonical_request_hash`, and the `TapeWriter`/`TapeReader` pair over a
SQLite (WAL) index.

A run is one manifest row, N step rows (one per agent/user/tool turn), and
at most one outcome row. Large payloads (request/response bodies, tool
results, state snapshots) don't live in the row itself -- a `Step` carries
only blob-store hashes (`request_ref`, `response_ref`, `tool_result_ref`,
`state_before`, `state_after`); the payloads themselves go through
`core.store.BlobStore`, which is what actually applies redaction.

Step rows are insert-only: recording the same `(run_id, step_idx)` twice
raises `DuplicateStepError` rather than overwriting -- replay divergence
must be a loud error, never a silent respend (rule 3 in
`docs/brief/summary.md` §3, and the "insert-only" requirement in
`docs/decisions/0001-preregistration.md`'s P1 gate).

`TapeWriter`/`TapeReader` follow `core.budget.BudgetLedger`'s pattern:
short-lived connections opened per operation, WAL mode. That, not a
shared connection guarded by a lock, is what makes `append_step` safe to
call from tau2's own worker threads -- each call gets its own connection
object, and SQLite's WAL mode serializes the underlying writes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_bisect.core.config import redact
from agent_bisect.core.store import canonical_json_bytes, sha256_hex

Actor = Literal["agent", "user", "tool"]

_SAMPLING_PARAM_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "seed",
    "frequency_penalty",
    "presence_penalty",
    "stop",
    "n",
    "logprobs",
    "response_format",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL,
    step_idx INTEGER NOT NULL,
    step_json TEXT NOT NULL,
    PRIMARY KEY (run_id, step_idx)
);
CREATE TABLE IF NOT EXISTS outcomes (
    run_id TEXT PRIMARY KEY,
    outcome_json TEXT NOT NULL
);
"""


class DuplicateRunError(Exception):
    """Raised when a run_id already has a manifest row."""


class DuplicateStepError(Exception):
    """Raised when a (run_id, step_idx) pair is inserted more than once."""


class DuplicateOutcomeError(Exception):
    """Raised when a run_id already has an outcome row."""


class UnknownRunError(Exception):
    """Raised when reading a run_id that has no manifest row."""


class UnknownStepError(Exception):
    """Raised when reading a (run_id, step_idx) pair that has no step row."""


def canonical_request_hash(request: dict[str, Any]) -> str:
    """Stable sha256 over the parts of a model request that affect sampling.

    Includes `model`, `messages`, `tools`, and any of a fixed set of
    sampling params present in `request` (temperature, top_p, max_tokens,
    seed, ...). Excludes everything else -- api key, api_base,
    timeout(s), metadata, and any other volatile field a caller's request
    dict happens to carry -- so two requests that would produce the same
    sampling distribution hash identically regardless of how they were
    assembled or in what key order.

    Used by the replay engine (`core.replay`, not part of this module) to
    detect divergence: a mismatch between a step's recorded
    `request_hash` and the hash of the request replay is about to make is
    a hard error, never a silent live fallback.
    """
    canonical = {
        "model": request.get("model"),
        "messages": request.get("messages"),
        "tools": request.get("tools"),
        "params": {key: request[key] for key in _SAMPLING_PARAM_KEYS if key in request},
    }
    return sha256_hex(canonical_json_bytes(canonical))


class Step(BaseModel):
    """One row: an agent/user/tool turn within a run.

    `state_before`/`state_after`/`state_hash` are the snapshot fields:
    `state_before` is the blob-store hash of the world state a replayer
    must `restore()` before re-executing this step; `state_after` is the
    state immediately following it; `state_hash` is the domain
    snapshotter's own hash of that post-step state (for tau2, its
    `Environment.get_db_hash()`), checked after every restore.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    step_idx: int = Field(ge=0)
    parent_run_id: str | None = None
    fork_step: int | None = None
    actor: Actor
    request_hash: str | None = None
    request_ref: str | None = None
    response_ref: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result_ref: str | None = None
    state_before: str
    state_after: str
    state_hash: str
    model: str | None = None
    params: dict[str, Any] | None = None
    seed: int | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class RunManifest(BaseModel):
    """One row per run: everything pinned at record time.

    `fork_step`/`parent_run_id` identify a fork -- a run created by
    rewinding another run to a step and continuing from there -- from a
    fresh recording (both `None`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    domain: str
    task_id: str
    agent_model: str
    user_model: str
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    tau2_commit: str
    created_at: datetime
    parent_run_id: str | None = None
    fork_step: int | None = None


class Outcome(BaseModel):
    """Run-level result. `passed` always equals `reward == 1.0`.

    `passed` may be omitted at construction (it's then derived from
    `reward`) or passed explicitly, in which case it's validated for
    consistency -- either way the invariant in
    `docs/brief/summary.md` ("pass = reward == 1.0") can't be violated by
    a caller passing mismatched values.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    reward: float
    # Default is never actually used: `_derive_passed` (mode="before") fills
    # this in from `reward` before pydantic applies field defaults, for
    # every dict-style construction (the only kind used in this codebase).
    # It's here so a type checker sees `Outcome(run_id=..., reward=...)`,
    # with `passed` omitted, as valid.
    passed: bool = False

    @model_validator(mode="before")
    @classmethod
    def _derive_passed(cls, data: Any) -> Any:
        if isinstance(data, dict) and "passed" not in data and "reward" in data:
            return {**data, "passed": data["reward"] == 1.0}
        return data

    @model_validator(mode="after")
    def _check_passed_matches_reward(self) -> Outcome:
        expected = self.reward == 1.0
        if self.passed != expected:
            raise ValueError(
                f"passed={self.passed} inconsistent with reward={self.reward} "
                "(pass = reward == 1.0)"
            )
        return self


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class TapeWriter:
    """Append-only writer over the SQLite tape index at `<root>/index.sqlite`."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._db_path = root / "index.sqlite"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return _connect(self._db_path)

    def start_run(self, manifest: RunManifest) -> None:
        """Insert the manifest row for a new run. Raises `DuplicateRunError` on reuse."""
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO runs (run_id, manifest_json) VALUES (?, ?)",
                    (manifest.run_id, redact(manifest.model_dump_json())),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateRunError(f"run already started: {manifest.run_id!r}") from exc

    def append_step(self, step: Step) -> None:
        """Insert one step row. Raises `DuplicateStepError` on a repeated (run_id, step_idx).

        Large payloads (request/response bodies, tool results, state) live
        in the blob store by reference and are redacted there; `redact()`
        is applied here too, to the row's own JSON text, as a second,
        independent layer over whatever this `Step` carries directly
        (`tool_args`, `params`) -- belt and suspenders for rule 5 in
        `docs/brief/summary.md` §3 ("the key never leaves .env").
        """
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO steps (run_id, step_idx, step_json) VALUES (?, ?, ?)",
                    (step.run_id, step.step_idx, redact(step.model_dump_json())),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateStepError(
                    f"step already recorded: run_id={step.run_id!r} step_idx={step.step_idx}"
                ) from exc

    def record_outcome(self, outcome: Outcome) -> None:
        """Insert the outcome row for a run. Raises `DuplicateOutcomeError` on reuse."""
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO outcomes (run_id, outcome_json) VALUES (?, ?)",
                    (outcome.run_id, redact(outcome.model_dump_json())),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateOutcomeError(
                    f"outcome already recorded: {outcome.run_id!r}"
                ) from exc


class TapeReader:
    """Read-only view over the same SQLite tape index."""

    def __init__(self, root: Path) -> None:
        self._db_path = root / "index.sqlite"

    def _connect(self) -> sqlite3.Connection:
        return _connect(self._db_path)

    def get_manifest(self, run_id: str) -> RunManifest:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise UnknownRunError(run_id)
        return RunManifest.model_validate_json(row[0])

    def get_steps(self, run_id: str) -> list[Step]:
        """All steps for `run_id`, ordered by `step_idx`. Empty list if the run has none yet."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT step_json FROM steps WHERE run_id = ? ORDER BY step_idx", (run_id,)
            ).fetchall()
        return [Step.model_validate_json(row[0]) for row in rows]

    def get_step(self, run_id: str, step_idx: int) -> Step:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT step_json FROM steps WHERE run_id = ? AND step_idx = ?",
                (run_id, step_idx),
            ).fetchone()
        if row is None:
            raise UnknownStepError(f"run_id={run_id!r} step_idx={step_idx}")
        return Step.model_validate_json(row[0])

    def get_outcome(self, run_id: str) -> Outcome | None:
        """The outcome for `run_id`, or `None` if the run has no outcome row yet."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT outcome_json FROM outcomes WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return Outcome.model_validate_json(row[0])
