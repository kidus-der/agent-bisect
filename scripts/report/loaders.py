"""Loaders for the committed inputs the report reads.

Every function here reads a file under `data/` or `docs/gates/` and returns
plain `dict`/`list` structures — no live computation, no fallback defaults
that would let a missing file silently produce a number. A missing input
raises `FileNotFoundError`, which `render.py` lets propagate rather than
catching, so a broken input fails `make reproduce` loudly instead of
regenerating a table with a hole in it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"

MANIFEST_STRICT = DATA_DIR / "manifest.json"
MANIFEST_EXTENDED = DATA_DIR / "manifest_extended.json"
MANIFEST_FLAKY = DATA_DIR / "manifest_flaky.json"
P5_SUMMARY = RESULTS_DIR / "p5_summary.json"
P5_ITEMS = RESULTS_DIR / "p5_items.json"
P4_GATE = RESULTS_DIR / "p4_gate.json"
LEDGER_BY_PHASE = RESULTS_DIR / "ledger_by_phase.json"
FLAKY_MECHANISM = RESULTS_DIR / "flaky_mechanism.json"
P5_POWER_TABLE = RESULTS_DIR / "p5_power_table.json"
P4_POWER_TABLE = RESULTS_DIR / "p4_power_table.json"
P5_SUMMARY_DEV = RESULTS_DIR / "p5_summary_dev.json"
P5_ITEMS_DEV = RESULTS_DIR / "p5_items_dev.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path = MANIFEST_STRICT) -> dict[str, Any]:
    return _read_json(path)


def load_manifest_extended() -> dict[str, Any]:
    return _read_json(MANIFEST_EXTENDED)


def load_manifest_flaky() -> dict[str, Any]:
    return _read_json(MANIFEST_FLAKY)


def load_p5_summary(path: Path = P5_SUMMARY) -> dict[str, Any]:
    return _read_json(path)


def load_p5_items(path: Path = P5_ITEMS) -> list[dict[str, Any]]:
    return _read_json(path)


def load_p4_gate() -> dict[str, Any]:
    return _read_json(P4_GATE)


def load_ledger_by_phase() -> dict[str, Any]:
    return _read_json(LEDGER_BY_PHASE)


def load_flaky_mechanism() -> dict[str, Any]:
    return _read_json(FLAKY_MECHANISM)


def load_p5_power_table() -> dict[str, Any]:
    return _read_json(P5_POWER_TABLE)


def load_p4_power_table() -> dict[str, Any]:
    return _read_json(P4_POWER_TABLE)


def load_p5_summary_dev() -> dict[str, Any]:
    return _read_json(P5_SUMMARY_DEV)


def load_p5_items_dev() -> list[dict[str, Any]]:
    return _read_json(P5_ITEMS_DEV)
