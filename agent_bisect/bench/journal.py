"""The injection pipeline's memory: one small JSON file per decision.

Rule 1 of `docs/brief/summary.md` §3 ends "a crash loses nothing, a
resume pays for nothing twice". A P3 collection is hours of API time, so
every unit of work — a base recording, a stability check, a candidate —
is written the moment it finishes and read back on the next pass instead
of being repeated.

Two surfaces, deliberately different:

- `read`/`write`/`all` are the **work queue**: keyed records that make a
  stage idempotent.
- `log`/`events` are the **append-only ledger** of every decision, kept
  and rejected alike. The dataset card needs the whole funnel, and a
  rejected candidate that left no trace is a number nobody can explain.

A corrupt record raises rather than being treated as absent: silently
re-running it would be cheap, but silently *losing* a kept item would
not, and the two are indistinguishable from here.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_bisect.core.config import redact
from agent_bisect.core.store import sha256_hex

_SAFE_EXTRA = "-_."
_SUFFIX_CHARS = 8
LOG_NAME = "log.jsonl"


def _filename(key: str) -> str:
    """A filesystem-safe name for `key`, unique per key.

    Keys carry run ids and task ids, which contain `/` and `:`. Sanitising
    alone would let two different keys collide, so a key that needed
    sanitising also carries a short digest of its original self.
    """
    safe = "".join(char if char.isalnum() or char in _SAFE_EXTRA else "_" for char in key)
    if safe == key:
        return f"{safe}.json"
    return f"{safe}-{sha256_hex(key.encode('utf-8'))[:_SUFFIX_CHARS]}.json"


class Journal:
    """Checkpoints and the decision log for one collection, under `root`."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        # Records are one file per key, so they need no guarding; the
        # decision log is one file every thread appends to.
        self._log_lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, kind: str, key: str) -> Path:
        return self._root / kind / _filename(key)

    def read(self, kind: str, key: str) -> dict[str, Any] | None:
        """The record for `(kind, key)`, or `None` if this work is still owed."""
        path = self.path_for(kind, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except ValueError as exc:
            raise ValueError(
                f"the {kind} record for {key!r} at {path} is not readable JSON: {exc}"
            ) from exc

    def write(self, kind: str, key: str, record: Mapping[str, Any]) -> Path:
        """Store a finished unit of work. Redacted, like everything on disk."""
        path = self.path_for(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redact(json.dumps(dict(record), indent=2, sort_keys=True)))
        return path

    def all(self, kind: str) -> list[dict[str, Any]]:
        """Every record of `kind`, in filename order."""
        directory = self._root / kind
        if not directory.exists():
            return []
        return [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]

    def log(self, event: Mapping[str, Any]) -> None:
        """Append one decision to the funnel ledger."""
        line = redact(json.dumps(dict(event), sort_keys=True))
        with self._log_lock, (self._root / LOG_NAME).open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def events(self) -> list[dict[str, Any]]:
        """Every logged decision, in the order it was made."""
        path = self._root / LOG_NAME
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
