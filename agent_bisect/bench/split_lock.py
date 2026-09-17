"""The test split is touched once, and the code is what enforces it.

`docs/decisions/0001-preregistration.md`: *"anything tuned is tuned on the
dev split only; the test split is touched once."* A rule that lives only in
a document is a rule that gets broken at 3 a.m. by someone re-running a
command, so `bisect eval --split test` asks this module first and three
things must hold:

1. **The manifest is frozen.** `bench/manifest.load_frozen` proves the
   split assignment and its hash are the ones that were committed before
   any P5 evaluation existed. No hash, no evaluation.
2. **Tuning is declared finished**, in `docs/decisions/0014-p5-freeze.md` —
   written at the end of dev-split work, by hand, saying so. Its absence
   means dev work is still in progress and the test split is not open.
3. **The test split has not already been opened.** Opening it writes a
   marker recording when. A second full run is a second look at held-out
   data; it is refused unless `--resume` says it is the *same* run being
   continued after an interruption, which is what checkpoints are for.

None of this is a threshold and none of it can be tuned. A locked split
raises `SplitLockedError` with what to do about it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

#: Written by hand at the end of dev-split work. Its content is not parsed:
#: the act of committing it is the declaration.
FREEZE_DECISION = Path("docs/decisions/0014-p5-freeze.md")
#: Written by this module the first time the test split is opened.
MARKER_NAME = "test_split_opened.json"

TEST_SPLIT = "test"


class SplitLockedError(RuntimeError):
    """The test split may not be opened, and this says why.

    Named without a `Test` prefix on purpose: pytest tries to collect any
    class whose name starts with `Test` and warns when it cannot.
    """


@dataclass(frozen=True, slots=True)
class SplitOpening:
    """The record of the one time the test split was opened."""

    opened_at: str
    resumed: bool

    def to_json(self) -> str:
        return json.dumps(
            {"opened_at": self.opened_at, "split": TEST_SPLIT}, indent=2, sort_keys=True
        )


def marker_path(out_dir: Path) -> Path:
    return out_dir / MARKER_NAME


def check_freeze_decision(decision: Path = FREEZE_DECISION) -> None:
    """Refuse unless tuning has been declared finished, in writing."""
    if not decision.exists():
        raise SplitLockedError(
            f"{decision} does not exist. The test split opens only once tuning is "
            "finished; write that decision file first, recording that all tuning was "
            "done on the dev split, then re-run."
        )


def open_test_split(
    out_dir: Path,
    *,
    resume: bool = False,
    now: datetime | None = None,
    decision: Path = FREEZE_DECISION,
) -> SplitOpening:
    """Open the test split once, or say why it cannot be opened again."""
    check_freeze_decision(decision)
    marker = marker_path(out_dir)
    if marker.exists():
        if not resume:
            recorded = json.loads(marker.read_text(encoding="utf-8"))
            raise SplitLockedError(
                f"the test split was already opened at {recorded.get('opened_at')}. "
                "Re-running it is a second look at held-out data. If this is the same "
                "run being continued after an interruption, pass --resume; if it is "
                "genuinely a new evaluation, that is a new experiment and needs a new "
                "decision record."
            )
        return SplitOpening(
            opened_at=str(json.loads(marker.read_text(encoding="utf-8"))["opened_at"]),
            resumed=True,
        )

    opening = SplitOpening(
        opened_at=(now or datetime.now(UTC)).isoformat(), resumed=False
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(opening.to_json() + "\n", encoding="utf-8")
    return opening


def guard(
    split: str,
    out_dir: Path,
    *,
    resume: bool = False,
    now: datetime | None = None,
    decision: Path = FREEZE_DECISION,
) -> SplitOpening | None:
    """The one call `bisect eval` makes. `None` for any split but test."""
    if split != TEST_SPLIT:
        return None
    return open_test_split(out_dir, resume=resume, now=now, decision=decision)
