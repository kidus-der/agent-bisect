"""Overview page: the headline result, including the Bisect-vs-best-judge gap."""

from __future__ import annotations

from agent_bisect.server.fixtures.benchmark_builder import build_paired_gap_ci
from agent_bisect.server.fixtures.bundle import build_bundle

SEED = 20260917


def test_overview_headline_has_every_ci(client):
    body = client.get("/api/overview").json()["data"]
    headline = body["headline"]
    for key in ("bisect", "best_judge", "gap"):
        ci = headline[key]
        assert ci["ci_low"] <= ci["value"] <= ci["ci_high"]


def test_overview_headline_gap_matches_the_accuracy_difference(client):
    body = client.get("/api/overview").json()["data"]
    headline = body["headline"]
    expected = headline["bisect"]["value"] - headline["best_judge"]["value"]
    assert headline["gap"]["value"] == round(expected, 4)


def test_gap_ci_is_a_paired_bootstrap_not_an_independent_proportions_interval():
    """The two methods are scored on the *same* dataset (paired), so the gap's
    CI must come from resampling runs together, not from combining each
    method's own independent Wilson interval (which would be too wide/wrong
    for a paired comparison, and is exactly the mistake direction.md's "never
    show an estimate without its real interval" rule exists to prevent)."""
    bundle = build_bundle(SEED)
    gap = build_paired_gap_ci(bundle.plans, bundle.judge_by_run, "bisect", "judge_step_by_step", SEED)
    bisect_ci = next(m for m in bundle.benchmark.methods if m.method == "bisect").accuracy
    judge_ci = next(m for m in bundle.benchmark.methods if m.method == "judge_step_by_step").accuracy
    naive_width = (bisect_ci.ci_high - bisect_ci.ci_low) + (judge_ci.ci_high - judge_ci.ci_low)
    assert (gap.ci_high - gap.ci_low) < naive_width


def test_gap_ci_is_deterministic():
    bundle_a = build_bundle(SEED)
    bundle_b = build_bundle(SEED)
    assert bundle_a.overview.headline.gap.model_dump(mode="json") == (
        bundle_b.overview.headline.gap.model_dump(mode="json")
    )


def test_gap_ci_with_no_labelled_runs_is_a_zero_width_interval_not_a_crash():
    ci = build_paired_gap_ci((), {}, "bisect", "judge_step_by_step", SEED)
    assert ci.value == 0.0
    assert ci.ci_low == ci.ci_high == 0.0
