#!/usr/bin/env python3
"""P8 gate: a clean clone, network blocked, reproduces the report byte for byte.

    uv run python scripts/gates/p8.py [--write-evidence]

The P8 criterion (`docs/LOOP_STATE.md`'s phase board, "P8 Report"): a clean
clone of the repository, with the network blocked, regenerates every
report table and figure identically to what is committed.

Four criteria:

1. **clone** — `git clone` from the local repository (a filesystem path,
   never a URL) succeeds. A local-path clone makes no network call by
   construction, which is itself part of the offline claim: the *source*
   for "clean clone" is never fetched over the network by this gate.
2. **environment** — the clone gets a Python environment without a network
   fetch. `uv sync --offline` is tried first; if the offline cache cannot
   satisfy it (a plausible first-clone gap this script does not paper
   over), the clone is pointed at *this* repository's already-synced
   `.venv` via `UV_PROJECT_ENVIRONMENT` instead, documented in the
   evidence rather than left to be inferred. Either way, no criterion
   below runs unless a working interpreter was obtained without touching
   the network.
3. **offline_render** — inside the clone, `scripts/report/render.py` runs
   to completion with every new INET/INET6 socket blocked
   (`scripts/report/_offline/sitecustomize.py`, first on `PYTHONPATH`) —
   the same mechanism `pytest-socket` gives the test suite, enforced here
   rather than merely documented.
4. **byte_identical** — after that run, `git status --porcelain` inside the
   clone shows no changes to `docs/report.md`, `docs/report/` or the
   `data/results/` sidecars the report reads and regenerates. A gate that
   only checks the script exits 0 would not catch a script that silently
   drifted from what is committed.

This gate does **not** run `make reproduce-p5`: that target needs
`runs/p5/`, which is gitignored and does not exist in any clone (see
docs/report.md's Reproduce section for why that is a separate, machine-
local claim). Running it here would fail the P8 gate for a reason that has
nothing to do with what P8 owns.

Like every other gate, a missing input is a FAIL with a reason, never a
skip. Prints PASS/FAIL per criterion, writes `<runs>/p8/gate.json`, exits
non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.gates.evidence import (  # noqa: E402
    current_commit,
    format_evidence,
    provenance_for,
    render_table,
)

GATE_TEXT = (
    "clean clone with network blocked -> make reproduce regenerates every "
    "figure/table byte-identically"
)
DEFAULT_RUNS_DIR = REPO_ROOT / "runs" / "p8"
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "docs" / "gates" / "P8.md"
OFFLINE_SITECUSTOMIZE = REPO_ROOT / "scripts" / "report" / "_offline"
#: Paths the render step regenerates; checked for a clean `git status` after.
REGENERATED_PATHS = (
    "docs/report.md",
    "docs/report/",
    "data/results/ledger_by_phase.json",
    "data/results/p4_gate.json",
    "data/results/p4_power_table.json",
    "data/results/p5_power_table.json",
    "data/results/flaky_mechanism.json",
    "data/results/p5_summary_dev.json",
    "data/results/p5_items_dev.json",
)
EVIDENCE_SOURCES = (
    "scripts/gates/p8.py",
    "scripts/report/render.py",
    "scripts/report/_offline/sitecustomize.py",
    "Makefile",
)


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def report(self) -> None:
        print(f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}")


def _run(
    cmd: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600
    )


def clone_repo(dest: Path) -> Criterion:
    """A local-path `git clone` — never a URL, so this step itself is offline."""
    result = _run(["git", "clone", "--quiet", str(REPO_ROOT), str(dest)], cwd=REPO_ROOT)
    ok = result.returncode == 0 and dest.exists()
    detail = f"cloned {REPO_ROOT} -> {dest}" if ok else f"git clone failed: {result.stderr.strip()}"
    return Criterion("clone", ok, detail)


def prepare_environment(clone_dir: Path) -> Criterion:
    """Offline sync if the cache allows; otherwise the parent's existing .venv."""
    offline = _run(["uv", "sync", "--offline"], cwd=clone_dir)
    if offline.returncode == 0:
        return Criterion(
            "environment",
            True,
            "`uv sync --offline` satisfied the environment from the local cache "
            "(no network fetch)",
            {"mode": "offline-sync"},
        )
    fallback_venv = REPO_ROOT / ".venv"
    ok = fallback_venv.exists()
    detail = (
        f"`uv sync --offline` could not satisfy the environment from the cache "
        f"({offline.stderr.strip().splitlines()[-1] if offline.stderr.strip() else 'no detail'}); "
        f"fell back to this repository's existing environment at {fallback_venv} "
        "via UV_PROJECT_ENVIRONMENT (documented deviation: the DATA pipeline runs "
        "offline; obtaining the interpreter itself did not, on this run)"
        if ok
        else f"`uv sync --offline` failed and no fallback .venv exists at {fallback_venv}"
    )
    return Criterion("environment", ok, detail, {"mode": "fallback-venv" if ok else "none"})


def render_offline(clone_dir: Path, env_mode: str) -> Criterion:
    """Run the report generator in the clone with every new socket blocked."""
    env = {
        "PYTHONPATH": str(OFFLINE_SITECUSTOMIZE),
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    if env_mode == "fallback-venv":
        env["UV_PROJECT_ENVIRONMENT"] = str(REPO_ROOT / ".venv")
        cmd = ["uv", "run", "--no-sync", "python", "scripts/report/render.py"]
    else:
        cmd = ["uv", "run", "python", "scripts/report/render.py"]
    result = _run(cmd, cwd=clone_dir, env=env)
    ok = result.returncode == 0
    detail = (
        "scripts/report/render.py exited 0 with every new network socket blocked"
        if ok
        else f"render.py failed (exit {result.returncode}): {result.stderr.strip()[-500:]}"
    )
    return Criterion("offline_render", ok, detail)


def check_byte_identical(clone_dir: Path) -> Criterion:
    status = _run(["git", "status", "--porcelain", "--", *REGENERATED_PATHS], cwd=clone_dir)
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    ok = status.returncode == 0 and not dirty
    detail = (
        "every regenerated path is byte-identical to what is committed"
        if ok
        else f"{len(dirty)} regenerated path(s) differ from what is committed: {dirty[:10]}"
    )
    return Criterion("byte_identical", ok, detail)


def run_gate(dest: Path | None = None) -> tuple[list[Criterion], Path | None]:
    """Runs the whole gate in a fresh temp clone; the clone is always removed."""
    with tempfile.TemporaryDirectory(prefix="bisect-p8-clone-") as tmp:
        clone_dir = Path(tmp) / "clone" if dest is None else dest
        criteria = [clone_repo(clone_dir)]
        if not criteria[-1].passed:
            return criteria, None

        env_criterion = prepare_environment(clone_dir)
        criteria.append(env_criterion)
        if not env_criterion.passed:
            return criteria, None

        env_mode = env_criterion.data.get("mode", "offline-sync")
        criteria.append(render_offline(clone_dir, env_mode))
        if not criteria[-1].passed:
            return criteria, None

        criteria.append(check_byte_identical(clone_dir))
        return criteria, None


def write_report(criteria: list[Criterion], runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / "gate.json"
    path.write_text(
        json.dumps(
            {
                "gate": "P8",
                "criteria": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail} for c in criteria
                ],
                "passed": all(c.passed for c in criteria),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return path


def write_evidence(criteria: list[Criterion], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        format_evidence(
            gate="P8",
            title="report reproducibility",
            script="scripts/gates/p8.py",
            criteria=criteria,
            gate_text=GATE_TEXT,
            commands=[
                "uv run python scripts/gates/p8.py --write-evidence",
                "make reproduce        # the same check, against the working tree",
                "make reproduce-check  # reproduce, with the network block enforced locally too",
            ],
            provenance=provenance_for(EVIDENCE_SOURCES),
            sections={
                "What this gate does not cover": (
                    "`make reproduce-p5` (re-deriving `data/results/p5_summary.json` from "
                    "the raw `runs/p5/` outcome table) is a separate, machine-local claim: "
                    "`runs/` is gitignored, so no clean clone has it. This gate covers the "
                    "part of P5's reproducibility claim that a clean clone actually can run "
                    "-- the report layer, `scripts/report/render.py`, which reads only "
                    "committed JSON under `data/`. See docs/report.md's Reproduce section."
                ),
                "Regenerated paths checked": render_table(
                    ("Path",), [(f"`{p}`",) for p in REGENERATED_PATHS]
                ),
            },
            commit=current_commit(),
        )
    )
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--write-evidence", action="store_true", help="Regenerate docs/gates/P8.md."
    )
    parser.add_argument(
        "--keep-clone",
        type=Path,
        default=None,
        help="Clone into this path instead of a temp dir, and keep it (debugging).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not shutil.which("git") or not shutil.which("uv"):
        criteria = [Criterion("prerequisites", False, "git and uv must both be on PATH")]
    else:
        criteria, _ = run_gate(args.keep_clone)
    for criterion in criteria:
        criterion.report()
    report = write_report(criteria, args.runs_dir)
    passed = bool(criteria) and all(c.passed for c in criteria)
    print(f"P8 gate: {'PASS' if passed else 'FAILED'} — report at {report}")
    if args.write_evidence:
        print(f"wrote {write_evidence(criteria, DEFAULT_EVIDENCE_PATH)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
