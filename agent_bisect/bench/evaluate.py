"""The P5 report: one JSON document, computed from labels and outcomes only.

`score_outcomes` joins the frozen manifest's labels to what each method
answered; `build_report` turns those scores into every number P5 reports.
Both are pure functions of their arguments — no clock, no filesystem, no
network — so `make reproduce` regenerates the report from stored results
offline and byte-identically.

Rules the code enforces rather than documents:

- **Nothing is dropped.** An outcome with no label, or a label with no
  outcome for a method that ran, raises. A judge that could not answer, a
  search that blamed nothing, a suspect that could not be tested: all are
  scored, as wrong.
- **Only an exact hit counts.** `bench/metrics.classify` has four verdicts
  and accuracy counts one of them.
- **The comparator is fixed, not searched.** The gap is Bisect minus the
  better of the two judge-only baselines *on this split*, which is the
  pre-registered comparison (`docs/decisions/0001-preregistration.md`).
  Which one it was is written into the report, because a gate that did not
  say which comparator it beat would not be checkable.
- **An interval never appears without its sample size**, and a quantity
  that was not measured is absent rather than zero: the flaky ablation is
  `None` when no flaky run exists, and no cost is invented in dollars,
  because this project's spend is measured in API calls and inventing a
  price would be a fabricated number on a results page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_bisect.bench.baselines import EvalMethod, MethodOutcome
from agent_bisect.bench.manifest import DatasetItem
from agent_bisect.bench.metrics import (
    BOOTSTRAP_RESAMPLES,
    MAX_RECALL_M,
    CiValue,
    Verdict,
    accuracy_with_ci,
    classify,
    paired_bootstrap_gap,
    recall_curve,
)

#: The two methods the P5 gate's "best judge" is chosen between.
JUDGE_METHODS: tuple[EvalMethod, ...] = ("judge_all_at_once", "judge_step_by_step")
#: The pre-registered bar: Bisect must beat the best judge by this much.
GATE_POINTS = 15.0


@dataclass(frozen=True, slots=True)
class ScoredItem:
    """One method's answer for one item, joined to that item's label."""

    item_id: str
    run_id: str
    task_group: str
    domain: str
    split: str
    fault_type: str
    position_bucket: str
    planted_step: int
    method: EvalMethod
    predicted_step: int | None
    verdict: Verdict
    correct: bool
    ranking: tuple[int, ...]
    shortlist: tuple[int, ...]
    judge_calls: int
    replay_calls: int
    reruns: int
    parse_failed: bool
    note: str

    @property
    def total_calls(self) -> int:
        return self.judge_calls + self.replay_calls

    @property
    def shortlist_hit(self) -> bool:
        """Whether the shortlist even contained the planted step."""
        return self.planted_step in self.shortlist


def score_outcomes(
    items: Sequence[DatasetItem], outcomes: Sequence[MethodOutcome]
) -> tuple[ScoredItem, ...]:
    """Join labels to answers. Raises rather than silently dropping either side."""
    labels = {item.item_id: item for item in items}
    scored: list[ScoredItem] = []
    seen: dict[EvalMethod, set[str]] = {}
    for outcome in outcomes:
        item = labels.get(outcome.item_id)
        if item is None:
            raise ValueError(
                f"outcome for {outcome.item_id!r} has no label in the manifest; "
                "an unlabelled result must never be scored"
            )
        verdict = classify(predicted=outcome.predicted_step, planted=item.planted_step)
        scored.append(
            ScoredItem(
                item_id=item.item_id,
                run_id=item.run_id,
                task_group=item.group,
                domain=item.domain,
                split=item.split or "unassigned",
                fault_type=item.fault_type,
                position_bucket=item.position_bucket,
                planted_step=item.planted_step,
                method=outcome.method,
                predicted_step=outcome.predicted_step,
                verdict=verdict,
                correct=verdict == "exact",
                ranking=outcome.ranking,
                shortlist=outcome.shortlist or outcome.ranking[:3],
                judge_calls=outcome.judge_calls,
                replay_calls=outcome.replay_calls,
                reruns=outcome.reruns,
                parse_failed=outcome.parse_failed,
                note=outcome.note,
            )
        )
        seen.setdefault(outcome.method, set()).add(outcome.item_id)

    expected = set(labels)
    for method, answered in seen.items():
        missing = sorted(expected - answered)
        if missing:
            raise ValueError(
                f"method {method!r} has no outcome for {', '.join(missing)}; "
                "an item that was not answered is a wrong answer, not a missing row"
            )
    return tuple(scored)


def _by_method(scores: Sequence[ScoredItem]) -> dict[EvalMethod, list[ScoredItem]]:
    grouped: dict[EvalMethod, list[ScoredItem]] = {}
    for score in scores:
        grouped.setdefault(score.method, []).append(score)
    return grouped


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ci_document(value: CiValue) -> dict[str, float]:
    return {"value": value.value, "ci_low": value.ci_low, "ci_high": value.ci_high}


def _method_rows(grouped: Mapping[EvalMethod, Sequence[ScoredItem]]) -> list[dict[str, Any]]:
    return [
        {
            "method": method,
            "n": len(rows),
            "accuracy": _ci_document(accuracy_with_ci([row.correct for row in rows])),
            "mean_calls": _mean([float(row.total_calls) for row in rows]),
            "mean_judge_calls": _mean([float(row.judge_calls) for row in rows]),
            "mean_replay_calls": _mean([float(row.replay_calls) for row in rows]),
            "mean_reruns": _mean([float(row.reruns) for row in rows]),
            "parse_failures": sum(1 for row in rows if row.parse_failed),
        }
        for method, rows in sorted(grouped.items())
    ]


def _best_judge(
    grouped: Mapping[EvalMethod, Sequence[ScoredItem]]
) -> tuple[EvalMethod, float] | None:
    candidates: list[tuple[EvalMethod, float]] = [
        (method, _mean([float(row.correct) for row in grouped[method]]))
        for method in JUDGE_METHODS
        if method in grouped
    ]
    if not candidates:
        return None
    # Ties break on the method name so the choice is reproducible.
    return max(candidates, key=lambda pair: (pair[1], pair[0]))


def _aligned(
    target: Sequence[ScoredItem], comparator: Sequence[ScoredItem]
) -> tuple[list[bool], list[bool], list[str]]:
    """The two arms, item for item, in one order, with each item's task."""
    by_item = {row.item_id: row for row in comparator}
    left: list[bool] = []
    right: list[bool] = []
    groups: list[str] = []
    for row in sorted(target, key=lambda item: item.item_id):
        other = by_item[row.item_id]
        left.append(row.correct)
        right.append(other.correct)
        groups.append(row.task_group)
    return left, right, groups


def _gap_document(
    grouped: Mapping[EvalMethod, Sequence[ScoredItem]], *, seed: int, resamples: int
) -> dict[str, Any] | None:
    if "bisect" not in grouped:
        return None
    best = _best_judge(grouped)
    if best is None:
        return None
    comparator, _ = best
    left, right, groups = _aligned(grouped["bisect"], grouped[comparator])
    gap = paired_bootstrap_gap(
        left, right, groups=groups, seed=seed, resamples=resamples
    )
    return {
        "comparator": comparator,
        **_ci_document(gap),
        "points": gap.value * 100.0,
        "resamples": resamples,
        "clears_fifteen_points": gap.value * 100.0 >= GATE_POINTS,
        "ci_above_zero": gap.excludes_zero_above,
    }


def _recall_document(
    grouped: Mapping[EvalMethod, Sequence[ScoredItem]]
) -> dict[str, dict[str, float]]:
    document: dict[str, dict[str, float]] = {}
    for method, rows in sorted(grouped.items()):
        if not any(row.ranking for row in rows):
            continue
        curve = recall_curve(
            [row.ranking for row in rows], [row.planted_step for row in rows], MAX_RECALL_M
        )
        document[method] = {str(m): value for m, value in sorted(curve.items())}
    return document


def _breakdown(
    scores: Sequence[ScoredItem], key: str, label: str
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, EvalMethod], list[ScoredItem]] = {}
    for score in scores:
        buckets.setdefault((getattr(score, key), score.method), []).append(score)
    return [
        {
            label: value,
            "method": method,
            "accuracy": _mean([float(row.correct) for row in rows]),
            "n": len(rows),
        }
        for (value, method), rows in sorted(buckets.items())
    ]


def _sankey(scores: Sequence[ScoredItem], method: EvalMethod) -> list[dict[str, Any]]:
    counts: dict[tuple[str, Verdict], int] = {}
    for score in scores:
        if score.method != method:
            continue
        key = (score.fault_type, score.verdict)
        counts[key] = counts.get(key, 0) + 1
    return [
        {"fault_type": fault, "label": verdict, "count": count}
        for (fault, verdict), count in sorted(counts.items())
    ]


def _failures(grouped: Mapping[EvalMethod, Sequence[ScoredItem]]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": row.item_id,
            "run_id": row.run_id,
            "fault_type": row.fault_type,
            "position_bucket": row.position_bucket,
            "planted_step": row.planted_step,
            "predicted_step": row.predicted_step,
            "verdict": row.verdict,
            "shortlist": list(row.shortlist),
            "shortlist_hit": row.shortlist_hit,
            "parse_failed": row.parse_failed,
            "note": row.note,
        }
        for row in sorted(grouped.get("bisect", ()), key=lambda item: item.item_id)
        if not row.correct
    ]


def _flaky_document(
    flaky: Sequence[ScoredItem], *, seed: int, resamples: int
) -> dict[str, Any]:
    """Bisect on snapshots vs the same search re-running the prefix live.

    Both arms come from the **flaky** run: it is the same items, the same
    judge shortlist and the same estimator, differing only in whether the
    prefix is restored from a snapshot or re-executed. On deterministic
    tau2 the two agree by construction, which is why the ablation is only
    computed where the world is flaky.
    """
    flaky_grouped = _by_method(flaky)
    bisect_rows = flaky_grouped.get("bisect", ())
    live_rows = flaky_grouped.get("rerun_live", ())
    left, right, groups = _aligned(bisect_rows, live_rows)
    difference = paired_bootstrap_gap(
        left, right, groups=groups, seed=seed, resamples=resamples
    )
    return {
        "arms": [
            {
                "name": "snapshot",
                "accuracy": _ci_document(accuracy_with_ci([row.correct for row in bisect_rows])),
            },
            {
                "name": "no_snapshot",
                "accuracy": _ci_document(accuracy_with_ci([row.correct for row in live_rows])),
            },
        ],
        "difference": {**_ci_document(difference), "resamples": resamples},
        "n_items": len(bisect_rows),
        # Stated so nobody reads the deterministic world's numbers as the
        # ablation's: the comparison only means something in the flaky world.
        "world": "flaky",
    }


def build_report(
    scores: Sequence[ScoredItem],
    *,
    split: str,
    seed: int,
    bootstrap_resamples: int = BOOTSTRAP_RESAMPLES,
    flaky_scores: Sequence[ScoredItem] | None = None,
    cost_curve: Sequence[Mapping[str, Any]] | None = None,
    manifest_digest: str | None = None,
    estimator_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Every number P5 reports, from labels and answers alone."""
    if not scores:
        raise ValueError("no items to evaluate; a split with no items is not a result")
    grouped = _by_method(scores)
    items = {score.item_id for score in scores}
    return {
        "config": {
            "split": split,
            "seed": seed,
            "n_items": len(items),
            "bootstrap_resamples": bootstrap_resamples,
            "manifest_digest": manifest_digest,
            "estimator": dict(estimator_config) if estimator_config else None,
            "gate_points": GATE_POINTS,
        },
        "methods": _method_rows(grouped),
        "gap": _gap_document(grouped, seed=seed, resamples=bootstrap_resamples),
        "recall": _recall_document(grouped),
        "heatmap": _breakdown(scores, "fault_type", "fault_type"),
        "by_position": _breakdown(scores, "position_bucket", "position"),
        "sankey": _sankey(scores, "bisect"),
        "cost_curve": [dict(point) for point in cost_curve] if cost_curve else None,
        "flaky_ablation": (
            None
            if flaky_scores is None
            else _flaky_document(
                flaky_scores, seed=seed, resamples=bootstrap_resamples
            )
        ),
        "failures": _failures(grouped),
    }
