"""The unfinished split is inventoried, never scored."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "p5_partial.py"


def _module():
    spec = importlib.util.spec_from_file_location("p5_partial", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["p5_partial"] = module
    spec.loader.exec_module(module)
    return module


def _index(tmp_path: Path, runs: list[str], outcomes: list[str]) -> Path:
    path = tmp_path / "index.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table runs (run_id text)")
        connection.execute("create table outcomes (run_id text)")
        connection.executemany("insert into runs values (?)", [(r,) for r in runs])
        connection.executemany("insert into outcomes values (?)", [(r,) for r in outcomes])
    return path


def test_a_dead_fork_is_counted_as_recorded_but_not_completed(tmp_path):
    # Arrange: two forks of one parent, one of which never finished
    module = _module()
    index = _index(
        tmp_path,
        runs=["parent", "parent-c1-aaa", "parent-c1-bbb"],
        outcomes=["parent-c1-aaa"],
    )

    with sqlite3.connect(f"file:{index}?mode=ro", uri=True) as connection:
        run_ids = {row[0] for row in connection.execute("select run_id from runs")}
        outcome_ids = {row[0] for row in connection.execute("select run_id from outcomes")}

    # Act
    recorded, finished = module.fork_counts(run_ids, outcome_ids, "parent")

    # Assert: the parent itself is not one of its forks
    assert (recorded, finished) == (2, 1)


def test_every_item_carries_a_null_verdict_by_construction(tmp_path):
    """An item with forks on the tape is still an item with no answer."""
    # Arrange
    module = _module()

    class _Item:
        item_id = "airline-11-k10-tool_error"
        run_id = "parent"
        domain = "airline"
        fault_type = "tool_error"
        planted_step = 10

    index = _index(tmp_path, runs=["parent", "parent-c1-aaa"], outcomes=["parent-c1-aaa"])

    # Act
    rows = module.build_rows([_Item()], index)

    # Assert
    assert rows[0]["verdict"] is None
    assert rows[0]["forks_recorded"] == 1
    assert "never pooled" in module.NOTE
