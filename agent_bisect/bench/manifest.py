"""Freezing the planted-fault dataset: the split, the manifest, the hash.

`docs/decisions/0001-preregistration.md` fixes three things this module
implements and nothing else may reinterpret:

1. **dev:test is 1:2**, frozen with a manifest hash *before* any P5
   evaluation. Tuning happens on dev; the test split is touched once.
2. The split is **grouped by task**. Two items from the same tau2 task
   share a world, a policy and usually a trajectory prefix, so splitting
   them would leak the test set into the dev set and flatter every
   number computed afterwards.
3. The split is **stratified** by domain x fault type x position, so
   neither side is missing a stratum and per-stratum accuracy is
   reportable on both.

Freezing writes `manifest.json` and `manifest.sha256` next to it. The
manifest is written as canonical JSON, so re-running freeze on the same
inputs is byte-identical — the only input not derived from the data is
`created_at`, and it is an argument rather than a clock read for exactly
that reason. A manifest that already exists is never overwritten: the
whole point of a frozen split is that it cannot quietly become a
different one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_bisect.bench.faults import FaultType
from agent_bisect.bench.strata import PositionBucket
from agent_bisect.core.store import canonical_json_bytes, sha256_hex

DEFAULT_MANIFEST_PATH = Path("data/manifest.json")
MANIFEST_VERSION = 1
#: 1:2 dev:test.
DEV_SHARE = 1 / 3
#: Floating-point slack when asking "would dev still be at or under 1/3?".
_SHARE_EPSILON = 1e-9
#: How far the dev share may drift from 1:2 before the ratio overrules the
#: strata. The ratio is pre-registered (`0001`); stratum balance is a
#: property we want, not one we promised, so when they disagree the ratio
#: wins and the strata are balanced inside it.
SPLIT_TOLERANCE = 0.10

Split = Literal["dev", "test"]


class ManifestExistsError(Exception):
    """There is already a frozen manifest at this path."""


class ManifestNotFrozenError(Exception):
    """This manifest is not frozen, so nothing may be evaluated against it."""


class ManifestTamperedError(Exception):
    """The manifest's content no longer matches its recorded hash."""


class DatasetItem(BaseModel):
    """One labelled failure: a faulted recording and what was done to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    domain: str
    task_id: str
    #: Assigned by `freeze`; `None` while a candidate is still being collected.
    split: Split | None = None
    base_run_id: str
    base_pass_rate: float = Field(ge=0.0, le=1.0)
    #: The faulted recording that IS this item: a complete failed run.
    run_id: str
    faulted_pass_rate: float = Field(ge=0.0, le=1.0)
    #: The label.
    planted_step: int = Field(ge=0)
    position_bucket: PositionBucket
    fault_type: FaultType
    mutation: dict[str, Any]
    #: The oracle fix: the blob hash of the original, unfaulted tool result.
    oracle: dict[str, Any]
    #: `Intervention.to_ref()` of the `ReplaceToolResult` that planted it.
    intervention: dict[str, Any]
    #: Blob hash of that ref, so the forked recording can be traced back to it.
    intervention_ref: str | None = None
    seeds: list[int]
    n_reruns: int = Field(ge=1)

    @property
    def group(self) -> str:
        """The split's unit: everything from one task moves together."""
        return f"{self.domain}:{self.task_id}"

    @property
    def stratum(self) -> str:
        return f"{self.domain}|{self.fault_type}|{self.position_bucket}"


class FrozenManifest(BaseModel):
    """A manifest whose hash has been checked."""

    model_config = ConfigDict(frozen=True)

    version: int
    frozen: bool
    created_at: str
    tau2_commit: str
    models: dict[str, str]
    config: dict[str, Any]
    counts: dict[str, Any]
    items: list[DatasetItem]
    digest: str

    def split(self, name: Split) -> list[DatasetItem]:
        return [item for item in self.items if item.split == name]


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    """sha256 over the manifest's canonical JSON — order and spacing free."""
    return sha256_hex(canonical_json_bytes(dict(manifest)))


# ---- the split --------------------------------------------------------------


def assign_splits(items: Sequence[Mapping[str, Any] | DatasetItem]) -> dict[str, Split]:
    """Which side each *task* goes to: stratified, grouped, deterministic.

    Greedy over groups ordered by size (largest first, ties by name):
    each group goes to whichever side is currently furthest below its
    target share of the strata that group contributes to. Largest-first
    is what keeps the ratio close — a big group placed last can only
    overshoot.
    """
    parsed = [_as_item(entry) for entry in items]
    totals = _counted(item.stratum for item in parsed)
    groups = _grouped(parsed)
    placed: dict[Split, dict[str, int]] = {"dev": {}, "test": {}}
    assignment: dict[str, Split] = {}
    for group in sorted(groups, key=lambda name: (-len(groups[name]), name)):
        strata = _counted(item.stratum for item in groups[group])
        side = _better_side(strata, totals, placed, len(parsed))
        assignment[group] = side
        for stratum, count in strata.items():
            placed[side][stratum] = placed[side].get(stratum, 0) + count
    return assignment


def _better_side(
    strata: Mapping[str, int],
    totals: Mapping[str, int],
    placed: Mapping[Split, Mapping[str, int]],
    total_items: int,
) -> Split:
    # The ratio is a constraint, not a preference. With few task-groups the
    # stratum term can outvote it — four groups of two once split 4:4 —
    # and 1:2 is the thing that was pre-registered.
    group_size = sum(strata.values())
    placed_dev = _size(placed["dev"])
    placed_test = _size(placed["test"])
    projected = (placed_dev + group_size) / (placed_dev + placed_test + group_size)
    if placed_dev and projected > DEV_SHARE + SPLIT_TOLERANCE:
        return "test"

    needs = {
        side: _need(strata, totals, placed[side], side, total_items)
        for side in ("dev", "test")
    }
    if needs["dev"] > needs["test"]:
        return "dev"
    if needs["test"] > needs["dev"]:
        return "test"
    # A dead heat, which is the normal case early on and whenever every
    # stratum is a singleton: fall back on the overall ratio so 1:2 still
    # holds when the strata cannot express it. The test is on the share
    # dev WOULD have after taking this group, not the one it has -- a
    # group is indivisible, so the question is whether it still fits.
    return "dev" if projected <= DEV_SHARE + _SHARE_EPSILON else "test"


def _need(
    strata: Mapping[str, int],
    totals: Mapping[str, int],
    placed: Mapping[str, int],
    side: Split,
    total_items: int,
) -> float:
    """How far below its target `side` is, as a fraction of that target.

    Measured relative to each side's own share, so dev and test start
    level: an absolute deficit would hand every early group to test
    simply because test is twice the size.
    """
    share = DEV_SHARE if side == "dev" else 1.0 - DEV_SHARE
    group_size = sum(strata.values())
    per_stratum = sum(
        count * (totals[stratum] * share - placed.get(stratum, 0)) / (share * totals[stratum])
        for stratum, count in strata.items()
    )
    overall = (
        group_size * (total_items * share - _size(placed)) / (share * max(total_items, 1))
    )
    return per_stratum + overall


def _size(placed: Mapping[str, int]) -> int:
    return sum(placed.values())


def _counted(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _grouped(items: Sequence[DatasetItem]) -> dict[str, list[DatasetItem]]:
    groups: dict[str, list[DatasetItem]] = {}
    for item in items:
        groups.setdefault(item.group, []).append(item)
    return groups


def _as_item(entry: Mapping[str, Any] | DatasetItem) -> DatasetItem:
    return entry if isinstance(entry, DatasetItem) else DatasetItem.model_validate(dict(entry))


# ---- freezing ---------------------------------------------------------------


def build_manifest(
    items: Sequence[Mapping[str, Any] | DatasetItem],
    *,
    models: Mapping[str, str],
    tau2_commit: str,
    config: Mapping[str, Any],
    counts: Mapping[str, Any],
    created_at: datetime,
    assign_split: bool = True,
) -> dict[str, Any]:
    """The manifest dict, split assigned and items in a stable order.

    `assign_split=False` leaves every item unsplit, for a set nothing is
    tuned on — the flaky-world set of
    `docs/decisions/0017-p3-collection-policy.md` §4. A split there would
    be a split for its own sake.
    """
    parsed = [_as_item(entry) for entry in items]
    if not parsed:
        raise ValueError("no items to freeze: an empty dataset is not a dataset")
    assignment = assign_splits(parsed) if assign_split else {}
    placed = sorted(
        (
            item.model_copy(update={"split": assignment.get(item.group)})
            for item in parsed
        ),
        key=lambda item: item.item_id,
    )
    return {
        "version": MANIFEST_VERSION,
        "frozen": True,
        "created_at": created_at.isoformat(),
        "tau2_commit": tau2_commit,
        "models": dict(models),
        "config": dict(config),
        "counts": {
            **dict(counts),
            "items": len(placed),
            "dev": sum(1 for item in placed if item.split == "dev"),
            "test": sum(1 for item in placed if item.split == "test"),
        },
        "items": [item.model_dump(mode="json") for item in placed],
    }


def digest_path(path: Path) -> Path:
    return path.with_suffix(".sha256")


def freeze(
    items: Sequence[Mapping[str, Any] | DatasetItem],
    *,
    path: Path = DEFAULT_MANIFEST_PATH,
    models: Mapping[str, str],
    tau2_commit: str,
    config: Mapping[str, Any],
    counts: Mapping[str, Any],
    created_at: datetime,
    assign_split: bool = True,
) -> Path:
    """Write the frozen manifest and its hash. Never overwrites one."""
    if path.exists():
        raise ManifestExistsError(
            f"{path} is already frozen; a frozen split cannot be replaced. Delete it "
            "deliberately, or freeze to another path."
        )
    manifest = build_manifest(
        items, models=models, tau2_commit=tau2_commit, config=config,
        counts=counts, created_at=created_at, assign_split=assign_split,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(manifest))
    digest_path(path).write_text(manifest_digest(manifest) + "\n")
    return path


def load_frozen(path: Path = DEFAULT_MANIFEST_PATH) -> FrozenManifest:
    """Read a manifest and prove it is the one that was frozen.

    What `bisect eval --split test` gates on: no hash, no evaluation.
    """
    try:
        manifest = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ManifestNotFrozenError(f"no manifest at {path}") from exc
    except ValueError as exc:
        raise ManifestTamperedError(f"{path} is not readable JSON: {exc}") from exc
    if not manifest.get("frozen"):
        raise ManifestNotFrozenError(f"{path} is not marked frozen; it has no usable hash")
    sidecar = digest_path(path)
    if not sidecar.exists():
        raise ManifestNotFrozenError(f"{sidecar} is missing; the manifest hash is unverifiable")
    recorded = sidecar.read_text().strip()
    computed = manifest_digest(manifest)
    if recorded != computed:
        raise ManifestTamperedError(
            f"{path} does not match its recorded hash ({recorded[:12]}… != {computed[:12]}…); "
            "the frozen dataset has been edited"
        )
    return FrozenManifest(**manifest, digest=computed)
