"""The strata a planted fault is drawn from: where in the run, and which kind.

Two things are pre-registered in `docs/decisions/0001-preregistration.md`
and are therefore mechanical here, never a judgement call:

- **position** — the fault step is a tool-result step, "stratified early /
  middle / late (thirds of the run's tool-result steps by position in the
  run)". Position is counted among the run's *tool-result* steps, not
  among all its steps: an LLM turn is not a candidate fault site, and
  counting it would make a run with a chatty agent look front-loaded.
- **fault type** — one of the four in `bench.faults`, balanced across the
  dataset.

On top of them this module fixes the *order* candidates are attempted in,
so the pipeline is reproducible: one attempt per bucket per round, buckets
visited in order, the steps inside a bucket shuffled by the run's seed.
A base run therefore contributes at most one kept fault per bucket and at
most three in total, which is what stops one easy task from dominating
the dataset.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Literal

from agent_bisect.bench.faults import FAULT_TYPES, FaultType

PositionBucket = Literal["early", "middle", "late"]

#: In order: a candidate round visits them in this order, and the dataset
#: card reports the strata in it.
POSITION_BUCKETS: tuple[PositionBucket, ...] = ("early", "middle", "late")


def bucket_of(position: int, total: int) -> PositionBucket:
    """Which third of `total` tool-result steps `position` falls in.

    Exact integer thirds, so the three buckets differ in size by at most
    one and a run shorter than three tool steps simply leaves the later
    buckets empty rather than being stretched to fill them.
    """
    if not 0 <= position < total:
        raise ValueError(f"position {position} is not inside a run of {total} tool steps")
    return POSITION_BUCKETS[position * len(POSITION_BUCKETS) // total]


def bucketed(tool_step_indices: Sequence[int]) -> dict[PositionBucket, list[int]]:
    """The run's tool-step indices, split into the three position buckets.

    Keyed by every bucket, including the empty ones: a stratum that is
    absent from a run is information the funnel reports, not a key to
    look up and fail on.
    """
    total = len(tool_step_indices)
    found: dict[PositionBucket, list[int]] = {bucket: [] for bucket in POSITION_BUCKETS}
    for position, step_idx in enumerate(tool_step_indices):
        found[bucket_of(position, total)].append(step_idx)
    return found


def attempt_order(
    buckets: Mapping[PositionBucket, Sequence[int]],
    *,
    seed: int,
    attempts_per_bucket: int,
) -> list[tuple[PositionBucket, int]]:
    """`(bucket, step_idx)` in the order the pipeline should try them.

    Round-robin over the buckets so that a run which exhausts its budget
    part-way still contributed to every stratum it could, rather than
    three early faults and nothing else.
    """
    shortlists = {
        bucket: _shortlist(buckets.get(bucket, ()), seed=seed, bucket=bucket,
                           limit=attempts_per_bucket)
        for bucket in POSITION_BUCKETS
    }
    order: list[tuple[PositionBucket, int]] = []
    for attempt in range(attempts_per_bucket):
        for bucket in POSITION_BUCKETS:
            shortlist = shortlists[bucket]
            if attempt < len(shortlist):
                order.append((bucket, shortlist[attempt]))
    return order


def _shortlist(
    steps: Sequence[int], *, seed: int, bucket: str, limit: int
) -> list[int]:
    shuffled = list(steps)
    random.Random(f"{seed}:{bucket}").shuffle(shuffled)
    return shuffled[:limit]


class FaultBalancer:
    """Keeps the four fault types level across the dataset.

    An accumulator, not a value: `take` records its own choice, because
    balance is a property of the sequence of decisions rather than of any
    one of them. Construct it from the counts already on disk and a
    resumed run continues the same balance instead of restarting it.
    """

    def __init__(self, counts: Mapping[str, int] | None = None) -> None:
        self.counts: dict[str, int] = {fault_type: 0 for fault_type in FAULT_TYPES}
        self.counts.update(counts or {})

    def take(self, allowed: Sequence[FaultType]) -> FaultType:
        """The least-used of `allowed`; ties go to `FAULT_TYPES` order."""
        if not allowed:
            raise ValueError("no fault type can be planted here, so none can be chosen")
        chosen = min(
            allowed, key=lambda fault: (self.counts.get(fault, 0), FAULT_TYPES.index(fault))
        )
        self.counts[chosen] = self.counts.get(chosen, 0) + 1
        return chosen
