#!/usr/bin/env python3
"""P2 gate: every recorded run replays step-identically with the network blocked.

From `docs/decisions/0001-preregistration.md`:

  "20/20 runs replay step-identical with the same reward while the network
   is blocked; an altered request raises `DivergenceError`."

Two criteria:

1. **replay** — every recorded run replays with every response served from
   the tape, every tool re-executed and checked against its recorded
   result and state hash, the whole tape consumed, and the same reward.
   Counted as `n/n`.
2. **divergence** — one recorded request is mutated in a scratch copy of
   the store and the replay must raise `DivergenceError` naming the step.
   A gate that only checks the happy path cannot tell a working replay
   from one that never checks anything.

The network is blocked **in-process** for the whole run, not merely
assumed to be idle: `socket.socket` is replaced with something that raises
(the same guarantee `pytest-socket` gives the test suite) so a replay that
quietly reached for a live call fails here rather than passing expensively.

Prints PASS/FAIL per criterion, writes `<runs>/p2/gate.json`, exits
non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir  # noqa: E402

ensure_tau2_data_dir()

from agent_bisect.adapters.tau2_replay import replay_run  # noqa: E402
from agent_bisect.core.replay import DivergenceError  # noqa: E402
from agent_bisect.core.store import BlobStore  # noqa: E402
from agent_bisect.core.tape import TapeReader, canonical_request_hash  # noqa: E402
from scripts.gates.evidence import (  # noqa: E402
    current_commit,
    format_evidence,
    provenance_for,
    render_table,
)

REQUIRED_RUNS = 20
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "docs" / "gates" / "P2.md"
#: The files whose commits actually produced this verdict.
EVIDENCE_SOURCES = (
    "scripts/gates/p2.py",
    "agent_bisect/adapters/tau2_replay.py",
    "agent_bisect/core/replay.py",
    "agent_bisect/core/runner.py",
    "agent_bisect/cli_replay.py",
    "docs/decisions/0010-replay-mechanism.md",
)
GATE_TEXT = (
    "20/20 runs replay step-identical with the same reward while the network is blocked; "
    "an altered request raises `DivergenceError`."
)

#: Not copied into the divergence check's scratch store: the replay needs
#: the tape and the blobs, and nothing else. Other phases' artifacts are
#: megabytes of irrelevance, and the ledger must not be written to twice.
_SCRATCH_IGNORE = shutil.ignore_patterns(
    "p0", "p1", "p2", "p4", "logs", "record", "ledger.sqlite*"
)


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
    """Make every new socket raise for the duration of the block.

    Already-open sockets are left alone: litellm opens an httpx client at
    import time, and closing it would prove nothing about replay.
    """
    original = socket.socket

    class _Blocked(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise NetworkBlockedError(
                "a socket was opened while replaying; replay must make no network call"
            )

    socket.socket = _Blocked  # type: ignore[misc]
    try:
        yield
    finally:
        socket.socket = original  # type: ignore[misc]


def recorded_run_ids(runs_dir: Path) -> list[str]:
    """Every recording on the tape: no forks, and an outcome to compare against."""
    index = runs_dir / "index.sqlite"
    if not index.exists():
        return []
    connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        run_ids = sorted(row[0] for row in connection.execute("SELECT run_id FROM runs"))
    finally:
        connection.close()
    reader = TapeReader(runs_dir)
    return [
        run_id
        for run_id in run_ids
        if reader.get_manifest(run_id).parent_run_id is None
        and reader.get_outcome(run_id) is not None
    ]


def check_replays(runs_dir: Path, run_ids: list[str], required: int) -> Criterion:
    identical = 0
    failures: list[str] = []
    store = BlobStore(runs_dir)
    reader = TapeReader(runs_dir)
    for run_id in run_ids:
        try:
            with network_blocked():
                replay_run(run_id, store=store, reader=reader)
        except Exception as exc:  # noqa: BLE001 - any failure is a failed replay
            if len(failures) < 5:
                failures.append(f"{run_id}: {type(exc).__name__}: {exc}"[:300])
            continue
        identical += 1
    passed = len(run_ids) >= required and identical == len(run_ids)
    return Criterion(
        "replay",
        passed,
        f"{identical}/{len(run_ids)} runs replayed step-identically with the same reward "
        f"(need {required} runs)" + (f"; first failures: {failures}" if failures else ""),
        {"identical": identical, "runs": len(run_ids), "required": required,
         "failures": failures},
    )


def _mutate_one_request(runs_dir: Path, run_id: str) -> int:
    """Change one recorded agent request in place. Returns the step index."""
    store = BlobStore(runs_dir)
    reader = TapeReader(runs_dir)
    steps = reader.get_steps(run_id)
    target = next(step for step in steps if step.actor == "agent" and step.request_ref)
    assert target.request_ref is not None
    request = store.get_json(target.request_ref)
    messages = [dict(message) for message in request["messages"]]
    messages[-1]["content"] = f"{messages[-1].get('content') or ''} (mutated by the P2 gate)"
    mutated = {**request, "messages": messages}
    updated = target.model_copy(
        update={
            "request_ref": store.put_json(mutated),
            "request_hash": canonical_request_hash(mutated),
        }
    )
    connection = sqlite3.connect(runs_dir / "index.sqlite")
    with connection:
        connection.execute(
            "UPDATE steps SET step_json = ? WHERE run_id = ? AND step_idx = ?",
            (updated.model_dump_json(), run_id, target.step_idx),
        )
    connection.close()
    return target.step_idx


def check_divergence_is_detected(runs_dir: Path, run_id: str) -> Criterion:
    """Mutate a request in a scratch copy and require a DivergenceError."""
    scratch = Path(tempfile.mkdtemp(prefix="bisect-p2-"))
    try:
        copy = scratch / "runs"
        shutil.copytree(runs_dir, copy, ignore=_SCRATCH_IGNORE)
        step_idx = _mutate_one_request(copy, run_id)
        try:
            with network_blocked():
                replay_run(run_id, store=BlobStore(copy), reader=TapeReader(copy))
        except DivergenceError as error:
            return Criterion(
                "divergence",
                True,
                f"a mutated request at step {step_idx} raised DivergenceError at step "
                f"{error.step_idx} (actor {error.actor})",
                {"mutated_step": step_idx, "reported_step": error.step_idx,
                 "diff": error.diff[:200]},
            )
        except Exception as exc:  # noqa: BLE001 - the wrong error is still a failure
            return Criterion(
                "divergence",
                False,
                f"a mutated request raised {type(exc).__name__}, not DivergenceError",
                {"mutated_step": step_idx},
            )
        return Criterion(
            "divergence",
            False,
            f"a mutated request at step {step_idx} replayed without complaint",
            {"mutated_step": step_idx},
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_gate(runs_dir: Path, required: int) -> list[Criterion]:
    run_ids = recorded_run_ids(runs_dir)
    criteria = [check_replays(runs_dir, run_ids, required)]
    if run_ids:
        criteria.append(check_divergence_is_detected(runs_dir, run_ids[0]))
    else:
        criteria.append(
            Criterion("divergence", False, "no recorded run to mutate", {})
        )
    return criteria


def write_report(runs_dir: Path, criteria: list[Criterion]) -> Path:
    path = runs_dir / "p2" / "gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "gate": "P2",
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


def _replay_rows(runs_dir: Path, run_ids: list[str]) -> list[tuple[str, str]]:
    """Per run: how many steps came off the tape, and the reward reproduced."""
    reader = TapeReader(runs_dir)
    rows = []
    for run_id in run_ids:
        outcome = reader.get_outcome(run_id)
        steps = reader.get_steps(run_id)
        rows.append(
            (
                f"`{run_id}`",
                str(len(steps)),
                str(sum(1 for step in steps if step.actor != "tool")),
                "—" if outcome is None else f"{outcome.reward}",
            )
        )
    return rows


def write_evidence(runs_dir: Path, criteria: list[Criterion], path: Path) -> Path:
    run_ids = recorded_run_ids(runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        format_evidence(
            gate="P2",
            title="replay",
            script="scripts/gates/p2.py",
            criteria=criteria,
            gate_text=GATE_TEXT,
            commands=[
                "uv run python scripts/gates/p2.py --write-evidence",
                "uv run bisect replay airline-0-t0",
            ],
            provenance=provenance_for(EVIDENCE_SOURCES),
            sections={
                "Runs replayed": (
                    "Every response served from the tape with its request hash checked, "
                    "every tool re-executed and checked against its recorded result and "
                    "state hash, the whole tape consumed, and the same reward reached — "
                    "with `socket.socket` replaced by something that raises for the "
                    "duration.\n\n"
                    + render_table(
                        ("Run", "Steps", "LLM responses from tape", "Reward"),
                        _replay_rows(runs_dir, run_ids),
                    )
                ),
                "Cost": "0 API calls. A replay makes none, by construction.",
            },
            commit=current_commit(),
        )
    )
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--required-runs", type=int, default=REQUIRED_RUNS)
    parser.add_argument(
        "--write-evidence", action="store_true", help="Regenerate docs/gates/P2.md."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    criteria = run_gate(args.runs_dir, args.required_runs)
    for criterion in criteria:
        criterion.report()
    report = write_report(args.runs_dir, criteria)
    passed = all(criterion.passed for criterion in criteria)
    print(f"P2 gate: {'PASS' if passed else 'FAILED'} — report at {report}")
    if args.write_evidence:
        print(f"wrote {write_evidence(args.runs_dir, criteria, DEFAULT_EVIDENCE_PATH)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
