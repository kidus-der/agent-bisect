"""The fixture generator itself: determinism, run counts, edge cases, size budget."""

from __future__ import annotations

import json
from pathlib import Path

from agent_bisect.server.fixtures.bundle import build_bundle
from agent_bisect.server.fixtures.writer import write_bundle

SEED = 12345


def test_build_bundle_is_deterministic():
    first = build_bundle(SEED)
    second = build_bundle(SEED)
    assert [r.model_dump(mode="json") for r in first.run_summaries] == [
        r.model_dump(mode="json") for r in second.run_summaries
    ]
    assert first.benchmark.model_dump(mode="json") == second.benchmark.model_dump(mode="json")


def test_different_seeds_produce_different_data():
    a = build_bundle(SEED)
    b = build_bundle(SEED + 1)
    ids_a = {r.run_id for r in a.run_summaries}
    ids_b = {r.run_id for r in b.run_summaries}
    # Edge-case ids are shared by design; the bulk of ids/content differ.
    assert a.overview.model_dump(mode="json") != b.overview.model_dump(mode="json")
    assert ids_a == ids_b  # same run_id scheme, different content


def test_at_least_260_runs():
    bundle = build_bundle(SEED)
    assert len(bundle.plans) >= 260


def test_both_domains_present():
    bundle = build_bundle(SEED)
    domains = {p.domain for p in bundle.plans}
    assert domains == {"airline", "retail"}


def test_all_four_fault_types_present():
    bundle = build_bundle(SEED)
    fault_types = {p.fault_type for p in bundle.plans if p.fault_type is not None}
    assert fault_types == {"wrong_value", "missing_field", "stale_record", "tool_error"}


def test_roughly_45_percent_failures():
    bundle = build_bundle(SEED)
    failures = sum(1 for p in bundle.plans if not p.passed)
    rate = failures / len(bundle.plans)
    assert 0.30 <= rate <= 0.60


def test_edge_case_runs_present():
    bundle = build_bundle(SEED)
    ids = {p.run_id for p in bundle.plans}
    assert "run-edge-zero-tested" in ids
    assert "run-edge-no-clear" in ids
    assert "run-edge-60-step" in ids
    assert "run-edge-long-payload" in ids
    assert "run-edge-unicode" in ids
    assert "brief-12-step" in ids


def test_brief_run_matches_worked_example():
    bundle = build_bundle(SEED)
    plan = bundle.plan_by_id("brief-12-step")
    assert plan.n_steps == 12
    assert plan.planted_step == 7


def test_no_clear_run_truly_never_clears_delta():
    bundle = build_bundle(SEED)
    plan = bundle.plan_by_id("run-edge-no-clear")
    assert plan.estimate_shared is not None
    assert plan.estimate_shared.blamed_step is None


def test_write_bundle_stays_under_size_budget(tmp_path):
    bundle = build_bundle(SEED)
    out = tmp_path / "fixtures"
    write_bundle(bundle, out)
    total_bytes = sum(f.stat().st_size for f in out.glob("*.json"))
    assert total_bytes < 5 * 1024 * 1024


def test_write_bundle_output_is_valid_json(tmp_path):
    bundle = build_bundle(SEED)
    out = tmp_path / "fixtures"
    write_bundle(bundle, out)
    for f in out.glob("*.json"):
        json.loads(f.read_text())


def test_committed_fixtures_directory_matches_generator(tmp_path):
    """`data/fixtures/` in the repo was generated with seed 20260917 -- verify it still is."""
    from agent_bisect.server.fixture_repository import DEFAULT_FIXTURE_SEED

    committed = Path("data/fixtures/runs_summary.json")
    if not committed.exists():
        return  # nothing committed yet in this checkout; not this test's job to create it
    bundle = build_bundle(DEFAULT_FIXTURE_SEED)
    regenerated = tmp_path / "fixtures"
    write_bundle(bundle, regenerated)
    committed_bytes = committed.read_bytes()
    regenerated_bytes = (regenerated / "runs_summary.json").read_bytes()
    assert committed_bytes == regenerated_bytes
