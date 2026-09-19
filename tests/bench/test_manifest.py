"""Freezing the dataset: the 1:2 split, the manifest and its hash.

Pre-registered (`docs/decisions/0001-preregistration.md`): "dev:test split
1:2, frozen with a manifest hash before any P5 evaluation" and "anything
tuned is tuned on the dev split only; the test split is touched once".
Three properties carry that: the split is grouped by TASK so no task
appears on both sides, it is stratified so neither side is missing a
fault type or a position, and a frozen manifest cannot be quietly
replaced or edited.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from agent_bisect.bench.manifest import (
    DEV_SHARE,
    ManifestExistsError,
    ManifestNotFrozenError,
    ManifestTamperedError,
    assign_splits,
    freeze,
    load_frozen,
    manifest_digest,
)
from agent_bisect.bench.strata import POSITION_BUCKETS

FROZEN_AT = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
MODELS = {"agent": "a/model", "user_sim": "u/model", "judge": "j/model"}
CONFIG = {"n_reruns": 4, "keep_at_or_below": 0.25, "stable_at_or_above": 0.75}


def item(index: int, *, domain="airline", task="0", fault="wrong_value", bucket="early") -> dict:
    return {
        "item_id": f"{domain}-{task}-k{index}-{fault}",
        "domain": domain,
        "task_id": task,
        "base_run_id": f"{domain}-{task}-t0",
        "base_pass_rate": 1.0,
        "run_id": f"{domain}-{task}-k{index}-{fault}-s0",
        "faulted_pass_rate": 0.0,
        "planted_step": index,
        "position_bucket": bucket,
        "fault_type": fault,
        "mutation": {"fault_type": fault, "path": ["status"], "path_str": "status",
                     "old": "confirmed", "new": "pending", "detail": "rolled back"},
        "oracle": {"tool_result_ref": "d" * 64, "step_idx": index},
        "intervention": {"name": "replace_tool_result", "hash": "e" * 64,
                         "describe": "tool result replaced", "fields": {"step": index}},
        "seeds": [1, 2, 3, 4],
        "n_reruns": 4,
    }


def many(count: int, *, tasks: int = 12) -> list[dict]:
    faults = ("wrong_value", "missing_field", "stale_record", "tool_error")
    return [
        item(
            index,
            domain="airline" if index % 2 else "retail",
            task=str(index % tasks),
            fault=faults[index % len(faults)],
            bucket=POSITION_BUCKETS[index % len(POSITION_BUCKETS)],
        )
        for index in range(count)
    ]


# ---- the split ----


def test_every_item_of_a_task_lands_on_the_same_side():
    items = many(60)

    splits = assign_splits(items)

    by_task: dict[str, set[str]] = {}
    for entry in items:
        key = f"{entry['domain']}:{entry['task_id']}"
        by_task.setdefault(key, set()).add(splits[key])
    assert all(len(sides) == 1 for sides in by_task.values())


def test_the_split_is_one_to_two_within_rounding():
    items = many(120, tasks=30)

    splits = assign_splits(items)
    dev = sum(1 for entry in items if splits[f"{entry['domain']}:{entry['task_id']}"] == "dev")

    assert abs(dev / len(items) - DEV_SHARE) <= 0.08


def test_both_sides_carry_every_fault_type_and_every_position():
    items = many(120, tasks=30)

    splits = assign_splits(items)
    seen: dict[str, set[str]] = {"dev": set(), "test": set()}
    for entry in items:
        side = splits[f"{entry['domain']}:{entry['task_id']}"]
        seen[side].add(entry["fault_type"])
        seen[side].add(entry["position_bucket"])

    assert seen["dev"] == seen["test"]


def test_the_split_is_deterministic():
    items = many(60)

    assert assign_splits(items) == assign_splits(list(reversed(items)))


# ---- freezing ----


def test_freezing_writes_a_manifest_and_its_hash(tmp_path):
    path = tmp_path / "manifest.json"

    freeze(many(12), path=path, models=MODELS, tau2_commit="abc123",
           config=CONFIG, counts={"kept": 12}, created_at=FROZEN_AT)

    manifest = json.loads(path.read_text())
    assert manifest["frozen"] is True
    assert len(manifest["items"]) == 12
    assert path.with_suffix(".sha256").read_text().strip() == manifest_digest(manifest)


def test_freezing_twice_on_the_same_input_is_byte_identical(tmp_path):
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    arguments = dict(models=MODELS, tau2_commit="abc123", config=CONFIG,
                     counts={"kept": 12}, created_at=FROZEN_AT)

    freeze(many(12), path=first, **arguments)  # pyright: ignore[reportArgumentType]
    freeze(list(reversed(many(12))), path=second, **arguments)  # pyright: ignore[reportArgumentType]

    assert first.read_bytes() == second.read_bytes()


def test_a_frozen_manifest_refuses_to_be_overwritten(tmp_path):
    path = tmp_path / "manifest.json"
    arguments = dict(models=MODELS, tau2_commit="abc123", config=CONFIG,
                     counts={"kept": 12}, created_at=FROZEN_AT)
    freeze(many(12), path=path, **arguments)  # pyright: ignore[reportArgumentType]

    with pytest.raises(ManifestExistsError, match="frozen"):
        freeze(many(24), path=path, **arguments)  # pyright: ignore[reportArgumentType]


def test_freezing_refuses_an_empty_dataset(tmp_path):
    with pytest.raises(ValueError, match="no items"):
        freeze([], path=tmp_path / "manifest.json", models=MODELS, tau2_commit="abc123",
               config=CONFIG, counts={}, created_at=FROZEN_AT)


def test_every_item_is_validated_before_it_is_frozen(tmp_path):
    broken = many(2)
    del broken[0]["planted_step"]

    with pytest.raises(ValueError, match="planted_step"):
        freeze(broken, path=tmp_path / "manifest.json", models=MODELS, tau2_commit="abc",
               config=CONFIG, counts={}, created_at=FROZEN_AT)


# ---- reading it back ----


def test_a_frozen_manifest_loads_with_its_items(tmp_path):
    path = tmp_path / "manifest.json"
    freeze(many(12), path=path, models=MODELS, tau2_commit="abc123",
           config=CONFIG, counts={"kept": 12}, created_at=FROZEN_AT)

    loaded = load_frozen(path)

    assert len(loaded.items) == 12
    assert {entry.split for entry in loaded.items} == {"dev", "test"}
    assert loaded.tau2_commit == "abc123"


def test_an_edited_manifest_is_refused(tmp_path):
    path = tmp_path / "manifest.json"
    freeze(many(12), path=path, models=MODELS, tau2_commit="abc123",
           config=CONFIG, counts={"kept": 12}, created_at=FROZEN_AT)
    manifest = json.loads(path.read_text())
    manifest["items"][0]["planted_step"] = 999
    path.write_text(json.dumps(manifest))

    with pytest.raises(ManifestTamperedError, match="hash"):
        load_frozen(path)


def test_a_manifest_without_its_hash_is_not_frozen(tmp_path):
    path = tmp_path / "manifest.json"
    freeze(many(12), path=path, models=MODELS, tau2_commit="abc123",
           config=CONFIG, counts={"kept": 12}, created_at=FROZEN_AT)
    path.with_suffix(".sha256").unlink()

    with pytest.raises(ManifestNotFrozenError, match="hash"):
        load_frozen(path)


def test_splits_can_be_read_off_a_frozen_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    freeze(many(30), path=path, models=MODELS, tau2_commit="abc123",
           config=CONFIG, counts={"kept": 30}, created_at=FROZEN_AT)

    loaded = load_frozen(path)

    assert len(loaded.split("dev")) + len(loaded.split("test")) == 30
    assert {entry.split for entry in loaded.split("test")} == {"test"}


def test_a_set_nothing_is_tuned_on_freezes_without_a_split(tmp_path):
    """The flaky-world set (`0017` section 4): a split there would be a
    split for its own sake."""
    path = tmp_path / "manifest_flaky.json"

    freeze(many(12), path=path, models=MODELS, tau2_commit="abc123",
           config=CONFIG, counts={"kept": 12}, created_at=FROZEN_AT, assign_split=False)

    loaded = load_frozen(path)
    assert {entry.split for entry in loaded.items} == {None}
    assert loaded.counts["dev"] == 0
    assert loaded.counts["test"] == 0


def test_an_extended_manifest_keeps_the_strict_split(tmp_path):
    """A task on one side of a frozen manifest cannot move in another, or
    the two disagree about what "test" means and any comparison between
    them leaks (`docs/decisions/0021-p3-outcome.md`)."""
    strict_path = tmp_path / "manifest.json"
    strict_items = many(30, tasks=10)
    freeze(strict_items, path=strict_path, models=MODELS, tau2_commit="abc",
           config=CONFIG, counts={}, created_at=FROZEN_AT)
    inherited = load_frozen(strict_path).splits_by_group()

    extended_path = tmp_path / "manifest_extended.json"
    freeze(strict_items + many(20, tasks=4), path=extended_path, models=MODELS,
           tau2_commit="abc", config=CONFIG, counts={}, created_at=FROZEN_AT,
           inherit_splits=inherited)

    extended = load_frozen(extended_path).splits_by_group()
    assert all(extended[group] == side for group, side in inherited.items())


def test_inheriting_nothing_is_an_ordinary_split(tmp_path):
    path = tmp_path / "manifest.json"

    freeze(many(30), path=path, models=MODELS, tau2_commit="abc", config=CONFIG,
           counts={}, created_at=FROZEN_AT, inherit_splits={})

    assert {entry.split for entry in load_frozen(path).items} == {"dev", "test"}
