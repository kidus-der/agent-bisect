#!/usr/bin/env python3
"""P1 gate: 20 recorded runs, every step restores to its recorded hash, no key anywhere.

From `docs/decisions/0001-preregistration.md`:

  "20 recorded runs; restoring any step reproduces its recorded DB hash at
   100% of steps; a redaction test proves the key appears in no blob or log."

Three criteria, checked against a real recording store:

1. **runs** — at least 20 runs with an outcome, each pinned to a real tau2
   commit. A run that aborted on infrastructure has no outcome row and is
   not counted, because an infra failure is not a recorded run.
2. **state** — for *every* step of *every* run, restoring `state_before`
   into a fresh environment reproduces `state_hash_before`, and restoring
   `state_after` reproduces `state_hash`. 100%, not "almost".
3. **redaction** — the whole store scanned for key-shaped material: every
   blob decompressed, every SQLite file, every log and every checkpoint.

Makes no network call. Prints PASS/FAIL per criterion, writes
`<runs>/p1/gate.json`, and exits non-zero if anything failed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir  # noqa: E402

ensure_tau2_data_dir()

from agent_bisect.adapters.tau2 import UNKNOWN_COMMIT, RunSpec, build_orchestrator  # noqa: E402
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter  # noqa: E402
from agent_bisect.core.store import BlobStore  # noqa: E402
from agent_bisect.core.tape import RunManifest, TapeReader  # noqa: E402

REQUIRED_RUNS = 20
#: The shape of an NVIDIA key, built rather than written out so this file
#: never contains a key-shaped literal of its own.
KEY_PATTERN = re.compile((r"nvapi" + r"-") + r"[A-Za-z0-9_\-]{32,}")
#: Files whose bytes are scanned as-is. Blobs are decompressed first.
SCANNED_SUFFIXES = (".json", ".jsonl", ".log", ".txt", ".sqlite", ".sqlite-wal", ".sqlite-shm")


@dataclass
class Criterion:
    """One PASS/FAIL line of the gate."""

    name: str
    passed: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def report(self) -> None:
        print(f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}")


def _finished_runs(reader: TapeReader, root: Path) -> list[RunManifest]:
    """Every run on the tape that has an outcome, oldest first."""
    import sqlite3

    index = root / "index.sqlite"
    if not index.exists():
        return []
    connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        run_ids = [row[0] for row in connection.execute("SELECT run_id FROM runs").fetchall()]
    finally:
        connection.close()
    manifests = [reader.get_manifest(run_id) for run_id in sorted(run_ids)]
    return [
        manifest
        for manifest in manifests
        # A fork is a derived run, not a recording; and an infra abort has
        # no outcome, so it was never a run either.
        if manifest.parent_run_id is None and reader.get_outcome(manifest.run_id) is not None
    ]


def check_runs(manifests: list[RunManifest], required: int) -> Criterion:
    unpinned = [m.run_id for m in manifests if m.tau2_commit in ("", UNKNOWN_COMMIT)]
    passed = len(manifests) >= required and not unpinned
    detail = f"{len(manifests)} recorded runs with an outcome (need {required})"
    if unpinned:
        detail += f"; {len(unpinned)} not pinned to a tau2 commit: {unpinned[:3]}"
    return Criterion(
        "runs",
        passed,
        detail,
        {"runs": len(manifests), "required": required, "unpinned": unpinned},
    )


def _spec_of(manifest: RunManifest) -> RunSpec:
    params = manifest.params or {}
    return RunSpec(
        domain=manifest.domain,
        task_id=manifest.task_id,
        agent_model=manifest.agent_model,
        user_model=manifest.user_model,
        seed=manifest.seed,
        temperature=params.get("temperature", 0.0),
        max_steps=params.get("max_steps", 200),
        max_errors=params.get("max_errors", 10),
    )


def check_state_restores(
    manifests: list[RunManifest], reader: TapeReader, blobs: BlobStore
) -> Criterion:
    """Restore every recorded step into a fresh environment and re-hash it."""
    checked = 0
    reproduced = 0
    failures: list[str] = []
    for manifest in manifests:
        steps = reader.get_steps(manifest.run_id)
        if not steps:
            continue
        environment = build_orchestrator(_spec_of(manifest), f"{manifest.run_id}-gate").environment
        snapshotter = Tau2Snapshotter(environment)
        for step in steps:
            checked += 1
            before_ok = _restores_to(snapshotter, blobs, step.state_before, step.state_hash_before)
            after_ok = _restores_to(snapshotter, blobs, step.state_after, step.state_hash)
            if before_ok and after_ok:
                reproduced += 1
            elif len(failures) < 5:
                failures.append(
                    f"{manifest.run_id} step {step.step_idx}: "
                    f"before_ok={before_ok} after_ok={after_ok}"
                )
    percentage = 100.0 * reproduced / checked if checked else 0.0
    passed = checked > 0 and reproduced == checked
    return Criterion(
        "state",
        passed,
        f"{reproduced}/{checked} steps restored to their recorded hash ({percentage:.1f}%)"
        + (f"; first failures: {failures}" if failures else ""),
        {"checked": checked, "reproduced": reproduced, "failures": failures},
    )


def _restores_to(
    snapshotter: Tau2Snapshotter, blobs: BlobStore, ref: str, expected: str | None
) -> bool:
    if expected is None:
        # A recording made before `state_hash_before` existed cannot be
        # checked on that side; say so rather than score it as a pass.
        return False
    snapshotter.restore(blobs.get_json(ref))
    return snapshotter.state_hash() == expected


def scan_for_key_material(root: Path) -> list[str]:
    """Every file under `root` that contains something key-shaped.

    Blobs are decompressed before scanning — a key inside a zstd frame is
    still a key, and would be invisible to a scan of the compressed bytes.
    """
    blobs = BlobStore(root)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            if path.suffix == ".zst":
                data = blobs.get_bytes(path.stem)
            elif path.suffix in SCANNED_SUFFIXES:
                data = path.read_bytes()
            else:
                continue
        except Exception as exc:  # noqa: BLE001 - an unreadable artifact is a finding
            found.append(f"{path.name}: unreadable ({type(exc).__name__})")
            continue
        if KEY_PATTERN.search(data.decode("utf-8", errors="ignore")):
            found.append(str(path.relative_to(root)))
    return found


def check_redaction(root: Path, extra_roots: list[Path]) -> Criterion:
    found: list[str] = []
    scanned_roots = [root, *[path for path in extra_roots if path.exists()]]
    for scanned in scanned_roots:
        found.extend(scan_for_key_material(scanned))
    return Criterion(
        "redaction",
        not found,
        (
            f"no key-shaped material in {len(scanned_roots)} scanned trees"
            if not found
            else f"{len(found)} artifacts contain key-shaped material: {found[:5]}"
        ),
        {"hits": found, "roots": [str(path) for path in scanned_roots]},
    )


def run_gate(runs_dir: Path, required: int, extra_roots: list[Path]) -> list[Criterion]:
    reader = TapeReader(runs_dir)
    blobs = BlobStore(runs_dir)
    manifests = _finished_runs(reader, runs_dir)
    return [
        check_runs(manifests, required),
        check_state_restores(manifests, reader, blobs),
        check_redaction(runs_dir, extra_roots),
    ]


def write_report(runs_dir: Path, criteria: list[Criterion]) -> Path:
    path = runs_dir / "p1" / "gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "gate": "P1",
                "passed": all(criterion.passed for criterion in criteria),
                "criteria": [
                    {
                        "name": criterion.name,
                        "passed": criterion.passed,
                        "detail": criterion.detail,
                        **criterion.data,
                    }
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
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--required-runs", type=int, default=REQUIRED_RUNS)
    parser.add_argument(
        "--also-scan",
        type=Path,
        nargs="*",
        default=None,
        help="Extra trees to scan for key material (default: <runs-dir>/logs).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    extra = args.also_scan if args.also_scan is not None else [args.runs_dir / "logs"]
    criteria = run_gate(args.runs_dir, args.required_runs, list(extra))
    for criterion in criteria:
        criterion.report()
    report = write_report(args.runs_dir, criteria)
    passed = all(criterion.passed for criterion in criteria)
    print(f"P1 gate: {'PASS' if passed else 'FAILED'} — report at {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
