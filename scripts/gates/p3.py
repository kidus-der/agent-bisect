#!/usr/bin/env python3
"""P3 gate: the planted-fault dataset is big enough, honest, and replayable.

From `docs/decisions/0001-preregistration.md`:

  "P3: >= 120 labelled failures. Fallback floor: 60, used **only if** P0's
   measured throughput projects the 120-target collection past 10 h of API
   time. Which one applied is recorded."

and, from the fixed method parameters:

  "stable successes have re-run pass >= 0.75; fault step k stratified early
   / middle / late; 4 fault types; a planted fault is kept if faulted pass
   <= 0.25 at N = 4; dev:test split 1:2, frozen with a manifest hash before
   any P5 evaluation."

Six criteria, one per clause:

1. **count** — enough labelled failures. The 60 floor counts only when
   `docs/decisions/0012-p3-floor.md` exists and records that P0's measured
   throughput triggered it.
2. **thresholds** — every item's base run passed >= 0.75 of its re-runs and
   its faulted pass rate is <= 0.25, at N >= 4.
3. **strata** — all four fault types and all three position buckets are
   present, so per-stratum accuracy is reportable.
4. **split** — 1:2 within rounding, and no task on both sides.
5. **hash** — the manifest matches its recorded sha256 and says it is
   frozen. `load_frozen` refuses otherwise.
6. **replay** — a sample of the items' recordings replays offline, with
   the network blocked in-process, every LLM request hash checked and the
   whole tape consumed.

Prints PASS/FAIL per criterion, writes `<runs>/p3/gate.json`, exits
non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir  # noqa: E402

ensure_tau2_data_dir()

from agent_bisect.bench.faults import FAULT_TYPES  # noqa: E402
from agent_bisect.bench.manifest import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    DEV_SHARE,
    DatasetItem,
    load_frozen,
)
from agent_bisect.bench.strata import POSITION_BUCKETS  # noqa: E402
from agent_bisect.core.store import BlobStore  # noqa: E402
from agent_bisect.core.tape import TapeReader  # noqa: E402

REQUIRED_ITEMS = 120
FALLBACK_FLOOR = 60
FLOOR_DECISION = Path("docs/decisions/0012-p3-floor.md")
STABLE_AT_OR_ABOVE = 0.75
KEEP_AT_OR_BELOW = 0.25
MIN_RERUNS = 4
REPLAY_SAMPLE = 10
#: The split is groups of whole tasks, so it cannot land on 1:2 exactly.
SPLIT_TOLERANCE = 0.10


class NetworkBlockedError(RuntimeError):
    """Something tried to open a socket while the gate was running."""


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def report(self) -> None:
        print(f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}")


@contextmanager
def network_blocked() -> Iterator[None]:
    """Make every new socket raise for the duration of the block."""
    original = socket.socket

    class _Blocked(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise NetworkBlockedError(
                "a socket was opened while replaying; the gate must make no network call"
            )

    socket.socket = _Blocked  # type: ignore[misc]
    try:
        yield
    finally:
        socket.socket = original  # type: ignore[misc]


# ---- the criteria -----------------------------------------------------------


def check_count(items: Sequence[DatasetItem], required: int, floor_decision: Path) -> Criterion:
    floor_recorded = floor_decision.exists()
    needed = FALLBACK_FLOOR if floor_recorded else required
    return Criterion(
        "count",
        len(items) >= needed,
        f"{len(items)} labelled failures (need {needed}"
        + (f"; the {FALLBACK_FLOOR} floor is recorded in {floor_decision})" if floor_recorded
           else f"; no {floor_decision} so the floor does not apply)"),
        {"items": len(items), "required": needed, "floor_recorded": floor_recorded},
    )


def check_thresholds(items: Sequence[DatasetItem]) -> Criterion:
    """Every item is a stable success that the fault actually broke."""
    unstable = [item.item_id for item in items if item.base_pass_rate < STABLE_AT_OR_ABOVE]
    unflipped = [item.item_id for item in items if item.faulted_pass_rate > KEEP_AT_OR_BELOW]
    short = [item.item_id for item in items if item.n_reruns < MIN_RERUNS]
    bad = unstable + unflipped + short
    return Criterion(
        "thresholds",
        not bad,
        f"{len(items) - len(set(bad))}/{len(items)} items have base pass >= "
        f"{STABLE_AT_OR_ABOVE} and faulted pass <= {KEEP_AT_OR_BELOW} at N >= {MIN_RERUNS}"
        + (f"; offenders: {bad[:5]}" if bad else ""),
        {"unstable": unstable[:5], "unflipped": unflipped[:5], "short_reruns": short[:5]},
    )


def check_strata(items: Sequence[DatasetItem]) -> Criterion:
    faults = _tally(item.fault_type for item in items)
    positions = _tally(item.position_bucket for item in items)
    missing = [name for name in FAULT_TYPES if not faults.get(name)]
    missing += [name for name in POSITION_BUCKETS if not positions.get(name)]
    return Criterion(
        "strata",
        not missing,
        f"fault types {faults}, positions {positions}"
        + (f"; missing: {missing}" if missing else ""),
        {"fault_types": faults, "positions": positions, "missing": missing},
    )


def check_split(items: Sequence[DatasetItem]) -> Criterion:
    dev = [item for item in items if item.split == "dev"]
    test = [item for item in items if item.split == "test"]
    share = len(dev) / len(items) if items else 0.0
    sides: dict[str, set[str | None]] = {}
    for item in items:
        sides.setdefault(item.group, set()).add(item.split)
    spanning = [group for group, found in sides.items() if len(found) != 1]
    ratio_ok = abs(share - DEV_SHARE) <= SPLIT_TOLERANCE
    return Criterion(
        "split",
        ratio_ok and not spanning and bool(dev) and bool(test),
        f"dev {len(dev)} : test {len(test)} (dev share {share:.3f}, target {DEV_SHARE:.3f} "
        f"+/- {SPLIT_TOLERANCE}), {len(sides)} tasks"
        + (f"; tasks on both sides: {spanning[:5]}" if spanning else ", none split across sides"),
        {"dev": len(dev), "test": len(test), "dev_share": share, "tasks": len(sides),
         "spanning": spanning[:5]},
    )


def check_hash(manifest_path: Path, digest: str) -> Criterion:
    return Criterion(
        "hash",
        True,
        f"{manifest_path} matches its recorded sha256 {digest[:16]}… and is marked frozen",
        {"digest": digest},
    )


def check_replays(items: Sequence[DatasetItem], runs_dir: Path, sample: int) -> Criterion:
    """A sample of the faulted recordings replays with the network blocked."""
    chosen = _sample(items, sample)
    store = BlobStore(runs_dir)
    reader = TapeReader(runs_dir)
    replayed = 0
    failures: list[str] = []
    for item in chosen:
        try:
            with network_blocked():
                _replay_faulted(item.run_id, store, reader)
        except Exception as exc:  # noqa: BLE001 - any failure is a failed replay
            if len(failures) < 5:
                failures.append(f"{item.run_id}: {type(exc).__name__}: {exc}"[:300])
            continue
        replayed += 1
    short = len(chosen) < min(REPLAY_SAMPLE, len(items))
    return Criterion(
        "replay",
        bool(chosen) and replayed == len(chosen),
        f"{replayed}/{len(chosen)} sampled recordings replayed offline"
        + (f" (fewer than the {REPLAY_SAMPLE} this gate samples by default)" if short else "")
        + (f"; first failures: {failures}" if failures else ""),
        {"replayed": replayed, "sampled": len(chosen), "below_default_sample": short,
         "failures": failures},
    )


def _replay_faulted(run_id: str, store: BlobStore, reader: TapeReader) -> None:
    """Replay one faulted recording from its own tape, executing no tool.

    `tool_mode="snapshot"`, not the default `"verify"`: a faulted
    recording is exactly the case where re-executing the tool does *not*
    reproduce the recorded result, because the result at the planted step
    is the mutation and the tool would answer truthfully. Everything else
    still holds — every LLM request hash is checked, the world is
    restored from the recorded snapshot and its hash checked, the whole
    tape must be consumed, and the reward must come out the same.
    """
    from agent_bisect.adapters.tau2_replay import replay_run

    replay_run(run_id, store=store, reader=reader, tool_mode="snapshot")


def _sample(items: Sequence[DatasetItem], size: int) -> list[DatasetItem]:
    """Evenly spread through the dataset, so the sample is not all one task."""
    if not items or size <= 0:
        return []
    if size >= len(items):
        return list(items)
    stride = len(items) / size
    return [items[int(index * stride)] for index in range(size)]


def _tally(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


# ---- the gate ---------------------------------------------------------------


def run_gate(
    manifest_path: Path, runs_dir: Path, required: int, sample: int, floor_decision: Path
) -> list[Criterion]:
    try:
        manifest = load_frozen(manifest_path)
    except Exception as exc:  # noqa: BLE001 - an unreadable manifest fails every criterion
        return [
            Criterion("hash", False, f"{type(exc).__name__}: {exc}", {}),
            Criterion("count", False, "no frozen manifest to count", {}),
            Criterion("thresholds", False, "no frozen manifest to check", {}),
            Criterion("strata", False, "no frozen manifest to check", {}),
            Criterion("split", False, "no frozen manifest to check", {}),
            Criterion("replay", False, "no frozen manifest to replay from", {}),
        ]
    items = manifest.items
    return [
        check_hash(manifest_path, manifest.digest),
        check_count(items, required, floor_decision),
        check_thresholds(items),
        check_strata(items),
        check_split(items),
        check_replays(items, runs_dir, sample),
    ]


def write_report(runs_dir: Path, criteria: list[Criterion]) -> Path:
    path = runs_dir / "p3" / "gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "gate": "P3",
                "passed": all(criterion.passed for criterion in criteria),
                "criteria": [
                    {"name": criterion.name, "passed": criterion.passed,
                     "detail": criterion.detail, **criterion.data}
                    for criterion in criteria
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / DEFAULT_MANIFEST_PATH)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--required-items", type=int, default=REQUIRED_ITEMS)
    parser.add_argument("--sample", type=int, default=REPLAY_SAMPLE)
    parser.add_argument("--floor-decision", type=Path, default=REPO_ROOT / FLOOR_DECISION)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    criteria = run_gate(
        args.manifest, args.runs_dir, args.required_items, args.sample, args.floor_decision
    )
    for criterion in criteria:
        criterion.report()
    report = write_report(args.runs_dir, criteria)
    passed = all(criterion.passed for criterion in criteria)
    print(f"P3 gate: {'PASS' if passed else 'FAILED'} — report at {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
