"""The P3 cost projection: arithmetic, and the rule it feeds.

The pre-registration lets the 120 target fall back to 60 "only if P0's
measured throughput projects the 120-target collection past 10 h of API
time". That is a decision taken from this script's output, so the
arithmetic and the verdict are pinned here.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from scripts.p3_projection import (
    DEFAULT_CALLS_PER_RUN,
    FALLBACK_FLOOR,
    TARGET_ITEMS,
    Inputs,
    calls_per_round,
    calls_per_task,
    items_per_stable_run,
    main,
    measure_calls_per_run,
    project,
    verdict,
)


def inputs(**overrides) -> Inputs:
    fields = dict(
        calls_per_run=20.0, calls_per_hour=1000.0, pass_rate=0.5, stable_rate=0.5,
        attempts_per_bucket=2, target=120, source="test",
    )
    fields.update(overrides)
    return Inputs(**fields)  # pyright: ignore[reportArgumentType]


# ---- the model ----


def test_a_round_costs_four_partial_re_runs_in_each_bucket():
    """N = 4 forks per bucket, each paying only for the suffix after its
    fork step: an early fork re-runs almost everything, a late one almost
    nothing."""
    assert calls_per_round(20.0) == pytest.approx(4 * 20.0 * (5 / 6 + 1 / 2 + 1 / 6))


def test_a_task_pays_for_stability_only_if_its_base_run_passed():
    never_passes = calls_per_task(inputs(pass_rate=0.0))

    assert never_passes == 20.0


def test_a_task_that_always_passes_and_is_stable_pays_the_full_model():
    full = calls_per_task(inputs(pass_rate=1.0, stable_rate=1.0, attempts_per_bucket=2))

    assert full == pytest.approx(20.0 * (1 + 4) + 2 * calls_per_round(20.0))


def test_more_attempts_per_bucket_yield_more_items_per_run():
    one = items_per_stable_run(0.35, 1)
    two = items_per_stable_run(0.35, 2)

    assert one < two <= 3.0


def test_a_run_never_yields_more_than_the_three_kept_faults():
    assert items_per_stable_run(1.0, 5) == 3.0


def test_a_higher_keep_rate_needs_fewer_tasks_and_fewer_hours():
    low = project(inputs(), 0.20)
    high = project(inputs(), 0.50)

    assert high.tasks_needed < low.tasks_needed
    assert high.hours < low.hours


def test_the_projection_scales_with_the_target():
    half = project(inputs(target=60), 0.35)
    full = project(inputs(target=120), 0.35)

    assert full.calls == 2 * half.calls


# ---- the rule ----


def test_the_floor_triggers_only_when_every_keep_rate_busts_the_budget():
    cheap = [project(inputs(calls_per_hour=1_000_000.0), rate) for rate in (0.2, 0.35, 0.5)]
    dear = [project(inputs(calls_per_hour=1.0), rate) for rate in (0.2, 0.35, 0.5)]

    assert verdict(cheap, 10.0, TARGET_ITEMS)["target"] == TARGET_ITEMS
    assert verdict(dear, 10.0, TARGET_ITEMS)["target"] == FALLBACK_FLOOR
    assert verdict(dear, 10.0, TARGET_ITEMS)["floor_triggered"] is True


def test_the_rule_is_not_answered_for_a_target_it_is_not_about():
    dear = [project(inputs(target=60, calls_per_hour=1.0), rate) for rate in (0.2, 0.5)]

    decision = verdict(dear, 10.0, 60)

    assert decision["rule_applies"] is False
    assert decision["floor_triggered"] is False
    assert decision["target"] == 60


# ---- measured inputs ----


def test_calls_per_run_falls_back_when_there_is_no_tape(tmp_path):
    measured, source = measure_calls_per_run(tmp_path)

    assert measured == DEFAULT_CALLS_PER_RUN
    assert "no tape" in source


def test_calls_per_run_is_read_off_the_tape_when_there_is_one(tmp_path):
    _tape_with(tmp_path, recordings={"r1": 6, "r2": 10}, forks={"f1": 100})

    measured, source = measure_calls_per_run(tmp_path)

    assert measured == 8.0
    assert "2 recordings" in source


def test_a_fork_is_not_a_recording_and_does_not_count(tmp_path):
    _tape_with(tmp_path, recordings={"r1": 4}, forks={"f1": 400})

    measured, _source = measure_calls_per_run(tmp_path)

    assert measured == 4.0


def _tape_with(root, *, recordings: dict[str, int], forks: dict[str, int]) -> None:
    """A minimal tape: manifests plus LLM and tool steps."""
    connection = sqlite3.connect(root / "index.sqlite")
    with connection:
        connection.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, manifest_json TEXT)")
        connection.execute(
            "CREATE TABLE steps (run_id TEXT, step_idx INTEGER, step_json TEXT)"
        )
        for run_id, calls in {**recordings, **forks}.items():
            parent = None if run_id in recordings else "r1"
            connection.execute(
                "INSERT INTO runs VALUES (?, ?)",
                (run_id, json.dumps({"run_id": run_id, "parent_run_id": parent})),
            )
            for index in range(calls):
                connection.execute(
                    "INSERT INTO steps VALUES (?, ?, ?)",
                    (run_id, index, json.dumps({"actor": "agent"})),
                )
            # Tool steps cost no model call and must not be counted.
            connection.execute(
                "INSERT INTO steps VALUES (?, ?, ?)",
                (run_id, calls, json.dumps({"actor": "tool"})),
            )
    connection.close()


# ---- the command ----


def test_the_script_prints_a_table_and_a_verdict(tmp_path, capsys):
    assert main(["--runs-dir", str(tmp_path)]) == 0

    printed = capsys.readouterr().out
    assert "keep" in printed
    assert "verdict:" in printed
    assert "20%" in printed and "50%" in printed


def test_the_script_can_emit_json(tmp_path, capsys):
    main(["--runs-dir", str(tmp_path), "--json"])

    report = json.loads(capsys.readouterr().out)
    assert len(report["projections"]) == 3
    assert report["inputs"]["target_items"] == TARGET_ITEMS
    assert "floor_triggered" in report["verdict"]
