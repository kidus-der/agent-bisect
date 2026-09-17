"""The P3 gate: each criterion passes only when it should.

The gate is what turns "we collected some data" into "the pre-registered
dataset exists", so each clause is tested against a dataset that violates
exactly it. The replay criterion needs real recordings and is exercised
end to end in `tests/test_tau2_inject_e2e.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from agent_bisect.bench.manifest import DatasetItem, freeze, load_frozen
from scripts.gates.p3 import (
    check_count,
    check_split,
    check_strata,
    check_thresholds,
    run_gate,
    write_report,
)

FROZEN_AT = datetime(2026, 9, 17, tzinfo=UTC)
MODELS = {"agent": "a/m", "user_sim": "u/m", "judge": "j/m"}
FAULTS = ("wrong_value", "missing_field", "stale_record", "tool_error")
BUCKETS = ("early", "middle", "late")


def item(index: int, **overrides) -> DatasetItem:
    task = str(index // 4)
    fields = {
        "item_id": f"airline-{task}-k{index}-x",
        "domain": "airline",
        "task_id": task,
        "base_run_id": f"airline-{task}-t0",
        "base_pass_rate": 1.0,
        "run_id": f"airline-{task}-k{index}",
        "faulted_pass_rate": 0.0,
        "planted_step": index,
        "position_bucket": BUCKETS[index % 3],
        "fault_type": FAULTS[index % 4],
        "mutation": {"fault_type": FAULTS[index % 4], "path": [], "path_str": "<result>",
                     "old": 1, "new": 2, "detail": "changed"},
        "oracle": {"tool_result_ref": "d" * 64, "step_idx": index},
        "intervention": {"name": "replace_tool_result", "hash": "e" * 64,
                         "describe": "replaced", "fields": {"step": index}},
        "seeds": [1, 2, 3, 4],
        "n_reruns": 4,
    }
    fields.update(overrides)
    return DatasetItem(**fields)  # pyright: ignore[reportArgumentType]


def dataset(count: int = 24, **overrides) -> list[DatasetItem]:
    return [item(index, **overrides) for index in range(count)]


def split_evenly(items: list[DatasetItem]) -> list[DatasetItem]:
    """dev for the first third of the tasks, test for the rest."""
    tasks = sorted({entry.task_id for entry in items})
    dev = set(tasks[: max(1, len(tasks) // 3)])
    return [
        entry.model_copy(update={"split": "dev" if entry.task_id in dev else "test"})
        for entry in items
    ]


# ---- count ----


def test_count_needs_the_pre_registered_target(tmp_path):
    assert check_count(dataset(120), 120, tmp_path / "absent.md").passed
    assert not check_count(dataset(119), 120, tmp_path / "absent.md").passed


def test_the_sixty_floor_applies_only_when_it_was_recorded(tmp_path):
    recorded = tmp_path / "0012-p3-floor.md"
    recorded.write_text("the throughput rule triggered")

    assert check_count(dataset(60), 120, recorded).passed
    assert not check_count(dataset(59), 120, recorded).passed
    assert not check_count(dataset(60), 120, tmp_path / "absent.md").passed


# ---- thresholds ----


def test_thresholds_reject_an_unstable_base_run():
    assert check_thresholds(dataset(8)).passed
    assert not check_thresholds(dataset(8, base_pass_rate=0.5)).passed


def test_thresholds_reject_a_fault_that_did_not_flip_the_run():
    assert check_thresholds(dataset(8, faulted_pass_rate=0.5)).passed is False
    assert check_thresholds(dataset(8, faulted_pass_rate=0.25)).passed


def test_thresholds_reject_too_few_re_runs():
    assert not check_thresholds(dataset(8, n_reruns=2)).passed


# ---- strata ----


def test_strata_need_every_fault_type_and_every_position():
    assert check_strata(dataset(24)).passed
    assert not check_strata(dataset(24, fault_type="wrong_value")).passed
    assert not check_strata(dataset(24, position_bucket="early")).passed


# ---- split ----


def test_the_split_must_be_one_to_two_and_task_grouped():
    assert check_split(split_evenly(dataset(24))).passed


def test_a_task_on_both_sides_fails_the_split():
    items = split_evenly(dataset(24))
    crossed = [items[0].model_copy(update={"split": "test"}), *items[1:]]

    criterion = check_split(crossed)

    assert not criterion.passed
    assert "both sides" in criterion.detail


def test_an_all_test_split_fails():
    items = [entry.model_copy(update={"split": "test"}) for entry in dataset(24)]

    assert not check_split(items).passed


# ---- the whole gate ----


def test_the_gate_fails_loudly_without_a_manifest(tmp_path):
    criteria = run_gate(tmp_path / "missing.json", tmp_path, 120, 3, tmp_path / "absent.md")

    assert [criterion.passed for criterion in criteria] == [False] * 6
    assert criteria[0].name == "hash"


def test_the_gate_fails_when_the_manifest_was_edited(tmp_path):
    path = tmp_path / "manifest.json"
    freeze([entry.model_dump(mode="json") for entry in dataset(24)], path=path, models=MODELS,
           tau2_commit="abc", config={}, counts={}, created_at=FROZEN_AT)
    manifest = json.loads(path.read_text())
    manifest["items"][0]["planted_step"] = 99
    path.write_text(json.dumps(manifest))

    criteria = run_gate(path, tmp_path, 120, 3, tmp_path / "absent.md")

    assert not criteria[0].passed
    assert "hash" in criteria[0].detail.lower()


def test_the_gate_writes_a_report(tmp_path):
    criteria = run_gate(tmp_path / "missing.json", tmp_path, 120, 3, tmp_path / "absent.md")

    report = json.loads(write_report(tmp_path, criteria).read_text())

    assert report["gate"] == "P3"
    assert report["passed"] is False
    assert len(report["criteria"]) == 6


def test_a_frozen_manifest_passes_everything_but_the_replay(tmp_path):
    """No tape here, so `replay` is the only criterion that can fail."""
    path = tmp_path / "manifest.json"
    freeze([entry.model_dump(mode="json") for entry in dataset(120)], path=path, models=MODELS,
           tau2_commit="abc", config={}, counts={}, created_at=FROZEN_AT)

    criteria = {c.name: c for c in run_gate(path, tmp_path, 120, 3, tmp_path / "absent.md")}

    assert load_frozen(path).counts["items"] == 120
    assert [criteria[name].passed for name in ("hash", "count", "thresholds", "strata", "split")]
    assert not criteria["replay"].passed


@pytest.mark.parametrize("name", ["count", "thresholds", "strata", "split", "hash", "replay"])
def test_every_criterion_is_reported(tmp_path, name, capsys):
    criteria = run_gate(tmp_path / "missing.json", tmp_path, 120, 3, tmp_path / "absent.md")

    for criterion in criteria:
        criterion.report()

    assert name in capsys.readouterr().out
