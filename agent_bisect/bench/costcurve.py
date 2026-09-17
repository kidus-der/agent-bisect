"""The cost–accuracy curve, re-derived from re-runs that were already bought.

Sequential sampling makes the N axis nearly free. The draws for one step
arrive in batches, in order, and are all on the tape; asking what the
answer would have been at a smaller `max_n` is a matter of replaying the
first few of them through the same estimator. The m axis is free
*downwards* — testing fewer suspects uses a subset of the same re-runs —
and not free upwards, because a fourth suspect was never re-run at all.

What is measured and what is derived
------------------------------------
Exactly one point on the grid is **measured**: the primary configuration
the evaluation actually ran (N = 16, m = 3). Every other point is
**derived**, and each carries `source` saying so. Two derivations are
approximations, stated here rather than buried:

1. **The boundary.** The O'Brien–Fleming boundary of
   `docs/decisions/0008-sequential-efficacy-boundary.md` is defined for a
   plan of exactly four looks. A truncated plan has fewer, so every
   derived point is computed at the nominal boundary
   (`efficacy_boundary="none"`) and reports it. The primary point is
   reported twice — once measured under the boundary it ran under, once
   derived at the nominal one — so the two are comparable along the curve.
2. **The control arm.** The shared control was forked at the earliest step
   of the m = 3 shortlist. At m < 3 the earliest tested step can be a
   different one, and the derivation reuses the control that was drawn
   rather than inventing a new arm. That is precisely the flat-control
   assumption of `docs/decisions/0005-shared-control.md`, and
   `RecordedSampler.control_reused` records whenever it was leaned on.

Running out of recorded draws is an error, never a guess: an item that
cannot be derived at a point is excluded from that point and named in its
`note`, and the point reports how many items it *was* derived from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from agent_bisect.attribution.estimate import Arm, SequentialConfig, estimate_run

#: Marked on each point so a reader never has to guess which is which.
Source = Literal["measured", "derived"]

DEFAULT_N_VALUES: tuple[int, ...] = (4, 8, 12, 16)
DEFAULT_M_VALUES: tuple[int, ...] = (1, 2, 3, 5)

#: Seed is irrelevant to a sampler that serves recorded outcomes in order,
#: but `estimate_run` requires one.
_UNUSED_SEED = 0


class SamplerExhaustedError(RuntimeError):
    """The derivation asked for a draw that was never bought."""


@dataclass(frozen=True, slots=True)
class CurvePoint:
    """One (N, m) point: what it would have answered and what it would have cost."""

    n: int
    m: int
    accuracy: float
    mean_calls: float
    mean_reruns: float
    n_items: int
    n_excluded: int
    source: Source
    efficacy_boundary: str
    control_reused: bool
    note: str


class RecordedSampler:
    """An `estimate.RerunSampler` that serves stored outcomes in draw order.

    The seed is ignored: these outcomes were produced under the seeds the
    original run derived, and re-deriving them would be re-running the
    agent, which is the cost this whole analysis exists to avoid.
    """

    def __init__(self, records: Sequence[Mapping[str, Any]]) -> None:
        self._queues: dict[tuple[int, str], list[bool]] = {}
        self._calls: dict[tuple[int, str], list[int]] = {}
        self._control_step: int | None = None
        for record in records:
            key = (int(record["step"]), str(record["arm"]))
            self._queues.setdefault(key, []).append(bool(record["passed"]))
            self._calls.setdefault(key, []).append(int(record.get("calls", 0)))
            if record["arm"] == "control":
                self._control_step = int(record["step"])
        self._taken: dict[tuple[int, str], int] = {}
        self._calls_used = 0
        self._reruns_used = 0
        self.control_reused = False

    @property
    def calls_used(self) -> int:
        return self._calls_used

    @property
    def reruns_used(self) -> int:
        return self._reruns_used

    def _key(self, step: int, arm: Arm) -> tuple[int, str]:
        if arm == "control" and (step, arm) not in self._queues:
            if self._control_step is None:
                raise SamplerExhaustedError(
                    f"no control draws were recorded, so step {step} has no control arm"
                )
            self.control_reused = True
            return (self._control_step, arm)
        return (step, arm)

    def sample(self, step: int, arm: Arm, n: int, seed: int) -> Sequence[bool]:
        key = self._key(step, arm)
        queue = self._queues.get(key)
        if queue is None:
            raise SamplerExhaustedError(
                f"no recorded {arm} draws for step {step}; it was never re-run"
            )
        start = self._taken.get(key, 0)
        if start + n > len(queue):
            raise SamplerExhaustedError(
                f"step {step} arm {arm} has {len(queue) - start} draws left, {n} were asked for"
            )
        self._taken[key] = start + n
        self._calls_used += sum(self._calls[key][start : start + n])
        self._reruns_used += n
        return tuple(queue[start : start + n])


def _derived_config(config: SequentialConfig, n: int) -> SequentialConfig:
    """`config` truncated to `max_n = n` at the nominal boundary."""
    return replace(
        config,
        max_n=n,
        batch=min(config.batch, n),
        efficacy_boundary="none",
    )


@dataclass(frozen=True, slots=True)
class _ItemDerivation:
    correct: bool
    calls: int
    reruns: int
    control_reused: bool


def _derive_item(
    document: Mapping[str, Any], planted_step: int, *, n: int, m: int,
    config: SequentialConfig,
) -> _ItemDerivation:
    tested = tuple(document.get("tested_steps") or ())[:m]
    if not tested:
        return _ItemDerivation(correct=False, calls=0, reruns=0, control_reused=False)
    sampler = RecordedSampler(document.get("reruns") or ())
    estimate_doc = document.get("estimate") or {}
    control_mode = estimate_doc.get("control_mode", "shared")
    estimate = estimate_run(
        tested, sampler, _derived_config(config, n), control_mode, seed=_UNUSED_SEED
    )
    judge_calls = int((document.get("cost") or {}).get("judge_calls", 0))
    return _ItemDerivation(
        correct=estimate.blamed_step == planted_step,
        calls=judge_calls + sampler.calls_used,
        reruns=sampler.reruns_used,
        control_reused=sampler.control_reused,
    )


def derive_curve(
    documents: Mapping[str, Mapping[str, Any]],
    planted: Mapping[str, int],
    *,
    n_values: Sequence[int] = DEFAULT_N_VALUES,
    m_values: Sequence[int] = DEFAULT_M_VALUES,
    config: SequentialConfig,
    primary: tuple[int, int] | None = None,
) -> tuple[CurvePoint, ...]:
    """One `CurvePoint` per (N, m), derived from the stored re-runs."""
    if not documents:
        raise ValueError("no items to derive a cost curve from")

    points: list[CurvePoint] = []
    for n in sorted(n_values):
        for m in sorted(m_values):
            derivations: list[_ItemDerivation] = []
            excluded: list[str] = []
            for item_id, document in sorted(documents.items()):
                try:
                    derivations.append(
                        _derive_item(
                            document, planted[item_id], n=n, m=m, config=config
                        )
                    )
                except SamplerExhaustedError as exc:
                    excluded.append(f"{item_id}: {exc}")
            total = len(derivations)
            points.append(
                CurvePoint(
                    n=n,
                    m=m,
                    accuracy=(
                        sum(1 for d in derivations if d.correct) / total if total else 0.0
                    ),
                    mean_calls=(
                        sum(d.calls for d in derivations) / total if total else 0.0
                    ),
                    mean_reruns=(
                        sum(d.reruns for d in derivations) / total if total else 0.0
                    ),
                    n_items=total,
                    n_excluded=len(excluded),
                    source="measured" if primary == (n, m) else "derived",
                    efficacy_boundary=(
                        config.efficacy_boundary if primary == (n, m) else "none"
                    ),
                    control_reused=any(d.control_reused for d in derivations),
                    note="; ".join(excluded),
                )
            )
    return tuple(points)
