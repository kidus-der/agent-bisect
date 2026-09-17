"""The statistics P5 reports, and nothing that decides anything.

Four things, all pure:

- `classify` — how a prediction relates to the label: `exact`, `earlier`,
  `later`, or `none`. Only `exact` is correct. "No step blamed" is `none`
  and scores as **wrong**, never as a missing observation; a benchmark
  that dropped its non-detections would report the accuracy of the
  subset it happened to answer.
- `accuracy_with_ci` — a proportion with its Wilson score interval, reusing
  `attribution.estimate.wilson_interval` so the benchmark and the
  estimator cannot disagree about what a 95% interval is.
- `recall_at` / `recall_curve` — how often the planted step is inside the
  judge's top m. Reported separately from accuracy because a shortlist
  that omits the culprit caps every replay method at zero for that item
  (`docs/brief/summary.md` §2).
- `paired_bootstrap_gap` — the pre-registered P5 gate statistic: a 95%
  percentile interval for `accuracy(a) - accuracy(b)` from
  `BOOTSTRAP_RESAMPLES` resamples, **clustered on the task**.

Why the bootstrap is clustered
------------------------------
Two items planted in the same tau2 task share a world, a policy and
usually a trajectory prefix, so their errors are correlated. Resampling
items independently would treat them as independent evidence and produce
an interval that is too narrow — exactly the direction that would make a
gate pass when it should not. Whole tasks are resampled with replacement
and every item of a drawn task comes with it.

The comparison is paired: the same resampled items are scored for both
methods, which removes item difficulty from the difference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from agent_bisect.attribution.estimate import DEFAULT_CONF, wilson_interval

#: Pre-registered in `docs/decisions/0001-preregistration.md`.
BOOTSTRAP_RESAMPLES = 10_000

#: How a prediction relates to the planted step. Only `exact` is correct.
Verdict = Literal["exact", "earlier", "later", "none"]

#: recall@m is reported for m = 1..10, so the judge is asked to rank 10.
MAX_RECALL_M = 10

_ALPHA = 1.0 - DEFAULT_CONF


@dataclass(frozen=True, slots=True)
class CiValue:
    """A point estimate with its interval. Mirrors `server.schemas_benchmark.CiValue`."""

    value: float
    ci_low: float
    ci_high: float

    @property
    def excludes_zero_above(self) -> bool:
        """Whether the whole interval sits above zero -- the P5 gate's question."""
        return self.ci_low > 0.0


def classify(*, predicted: int | None, planted: int) -> Verdict:
    """How `predicted` relates to `planted`. `None` is a wrong answer, not a gap."""
    if predicted is None:
        return "none"
    if predicted == planted:
        return "exact"
    return "earlier" if predicted < planted else "later"


def accuracy_with_ci(correct: Sequence[bool], conf: float = DEFAULT_CONF) -> CiValue:
    """A proportion of hits with its Wilson score interval."""
    total = len(correct)
    if total == 0:
        raise ValueError("cannot take the accuracy of an empty sample")
    hits = sum(1 for hit in correct if hit)
    interval = wilson_interval(hits, total, conf=conf)
    return CiValue(value=hits / total, ci_low=interval.low, ci_high=interval.high)


def recall_at(
    rankings: Sequence[Sequence[int]], planted: Sequence[int], m: int
) -> float:
    """How often the planted step is among the first `m` ranked suspects."""
    if len(rankings) != len(planted):
        raise ValueError(
            f"rankings and planted steps must be the same length, got "
            f"{len(rankings)} and {len(planted)}"
        )
    if m <= 0:
        raise ValueError(f"m must be positive, got {m}")
    if not rankings:
        raise ValueError("cannot take recall over an empty sample")
    hits = sum(1 for ranking, label in zip(rankings, planted, strict=True)
               if label in tuple(ranking)[:m])
    return hits / len(rankings)


def recall_curve(
    rankings: Sequence[Sequence[int]], planted: Sequence[int], max_m: int = MAX_RECALL_M
) -> Mapping[int, float]:
    """recall@m for m = 1..max_m."""
    return {m: recall_at(rankings, planted, m) for m in range(1, max_m + 1)}


def _group_index(groups: Sequence[str]) -> tuple[tuple[str, ...], dict[str, np.ndarray]]:
    names = tuple(dict.fromkeys(groups))
    members = {
        name: np.array([i for i, group in enumerate(groups) if group == name], dtype=np.int64)
        for name in names
    }
    return names, members


def paired_bootstrap_gap(
    a: Sequence[bool],
    b: Sequence[bool],
    *,
    groups: Sequence[str],
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
    conf: float = DEFAULT_CONF,
) -> CiValue:
    """A percentile CI for `accuracy(a) - accuracy(b)`, resampling whole tasks.

    `groups[i]` is the task item `i` belongs to. Tasks are drawn with
    replacement until the resample holds as many tasks as the original;
    every item of a drawn task comes with it, so a resample is not
    necessarily the same size as the sample, which is correct for a
    cluster bootstrap.
    """
    if not (len(a) == len(b) == len(groups)):
        raise ValueError(
            f"both arms and the groups must be the same length, got "
            f"{len(a)}, {len(b)} and {len(groups)}"
        )
    if not a:
        raise ValueError("cannot bootstrap an empty sample")

    left = np.asarray(a, dtype=float)
    right = np.asarray(b, dtype=float)
    observed = float(left.mean() - right.mean())

    names, members = _group_index(groups)
    rng = np.random.default_rng(seed)
    differences = np.empty(resamples, dtype=float)
    count = len(names)
    for draw in range(resamples):
        chosen = rng.integers(0, count, size=count)
        indices = np.concatenate([members[names[index]] for index in chosen])
        differences[draw] = left[indices].mean() - right[indices].mean()

    low, high = np.quantile(differences, [_ALPHA / 2.0, 1.0 - _ALPHA / 2.0])
    if conf != DEFAULT_CONF:
        alpha = 1.0 - conf
        low, high = np.quantile(differences, [alpha / 2.0, 1.0 - alpha / 2.0])
    return CiValue(value=observed, ci_low=float(low), ci_high=float(high))
