"""Record-before-use and resume for judge calls.

Rule 1 of `docs/brief/summary.md` §3 — *record everything, always, before
use; a crash loses nothing, a resume pays for nothing twice* — applies to
the judge exactly as it applies to the agent. The run tape cannot hold
these calls: a judge call is not a step of any tau2 simulation, and giving
it a `Step` row would put a fabricated step on the dashboard's run detail.
So judge traffic gets its own append-only record, with the same shape and
the same discipline:

- the full request and the full response go to the content-addressed
  `core.store.BlobStore` (which is what applies redaction), and a row in
  `<root>/judge.sqlite` indexes them by a **call key**;
- the row is written by `core.llm.LLMClient`'s `record_before_use` hook, so
  it is durable *before* `complete()` hands the response back and before
  any parser can act on it (a hook failure becomes `RecordingError`);
- `lookup(key)` is the resume path: a question already answered is served
  from the record and costs neither a ledger row nor an API call.

The call key is a sha256 over `{model, system, user}` — the whole prompt,
not the item id — so re-judging an item whose trajectory changed correctly
costs a new call, while re-running the same evaluation costs none.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_bisect.core.llm import LLMClient, LLMRequest, LLMResponse, RecordBeforeUse
from agent_bisect.core.store import BlobStore, canonical_json_bytes, sha256_hex

#: Ledger purpose for every judge call, so `bisect eval`'s cost breakdown
#: can split judge spend from replay spend without guessing. `repair`
#: proposals use the same machinery under their own purpose, because
#: `docs/brief/summary.md` §9 scores them in a separate table.
JUDGE_PURPOSE = "judge"
REPAIR_PURPOSE = "repair"

DEFAULT_PHASE = "P5"
#: The P0-chosen judge is a reasoning model: it spends its output budget
#: thinking before it answers. Measured on the first live P5 call, it
#: produced 5,448 characters of reasoning and was cut off mid-word before
#: reaching the JSON -- twice, so the repair retry failed the same way and
#: the item scored as a parse failure having never been asked a question
#: it could answer. The cap has to cover the thinking AND the answer.
DEFAULT_MAX_TOKENS = 8_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS judge_calls (
    call_key TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    item_id TEXT NOT NULL,
    protocol TEXT NOT NULL,
    model TEXT NOT NULL,
    request_ref TEXT NOT NULL,
    response_ref TEXT NOT NULL,
    content TEXT NOT NULL
);
"""


def call_key(*, model: str, system: str, user: str) -> str:
    """Stable identity of one judge question: the model and the whole prompt."""
    return sha256_hex(
        canonical_json_bytes({"model": model, "system": system, "user": user})
    )


@dataclass(frozen=True, slots=True)
class JudgeCall:
    """One answer, and whether this process had to pay for it."""

    content: str
    paid: bool


class JudgeCallStore:
    """Append-only record of judge calls: blobs plus a SQLite index."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._blobs = BlobStore(root)
        self._db_path = root / "judge.sqlite"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def lookup(self, key: str) -> str | None:
        """The recorded answer for `key`, or `None` if it was never asked."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM judge_calls WHERE call_key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row[0])

    def record(
        self,
        *,
        key: str,
        item_id: str,
        protocol: str,
        model: str,
        request: Any,
        response_text: str,
    ) -> None:
        """Store one call. A repeat of the same key keeps the first answer.

        Insert-or-ignore rather than raise: a repeat means the same
        question was asked twice in one process, which is wasteful but not
        wrong, and the first recorded answer is the one every reader has
        already seen.
        """
        request_ref = self._blobs.put_json(request)
        response_ref = self._blobs.put_json({"content": response_text})
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO judge_calls "
                "(call_key, ts, item_id, protocol, model, request_ref, response_ref, content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key, time.time(), item_id, protocol, model, request_ref, response_ref,
                 response_text),
            )

    def calls_recorded(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM judge_calls").fetchone()[0])


#: Builds an `LLMClient` around a record-before-use hook. Injected so the
#: limiter, the ledger and the transport are the caller's, and so a test
#: can supply a fake transport without a network stack.
ClientFactory = Callable[[RecordBeforeUse], LLMClient]


class LedgeredJudgeBackend:
    """Asks the judge model through `core.llm`, once per distinct question."""

    def __init__(
        self,
        *,
        make_client: ClientFactory,
        store: JudgeCallStore,
        model: str,
        phase: str = DEFAULT_PHASE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        purpose: str = JUDGE_PURPOSE,
    ) -> None:
        self._make_client = make_client
        self.store = store
        self.model = model
        self._phase = phase
        self._max_tokens = max_tokens
        self._purpose = purpose

    def ask(
        self, *, system: str, user: str, item_id: str, protocol: str
    ) -> JudgeCall:
        """The judge's raw answer, from the record if it is already there."""
        if not system.strip() or not user.strip():
            raise ValueError("a judge prompt must not be empty")
        key = call_key(model=self.model, system=system, user=user)
        cached = self.store.lookup(key)
        if cached is not None:
            return JudgeCall(content=cached, paid=False)

        request = LLMRequest(
            model=self.model,
            messages=(
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ),
            max_tokens=self._max_tokens,
            purpose=self._purpose,
        )

        async def record(asked: LLMRequest, answered: LLMResponse) -> None:
            self.store.record(
                key=key,
                item_id=item_id,
                protocol=protocol,
                model=self.model,
                request={"model": asked.model, "messages": list(asked.messages)},
                response_text=answered.content,
            )

        client = self._make_client(record)
        response = asyncio.run(client.complete(request, phase=self._phase))
        return JudgeCall(content=response.content, paid=True)
