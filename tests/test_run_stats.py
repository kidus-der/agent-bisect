"""Tests for the recorded-run statistics that P3's planning needs."""

from __future__ import annotations

import pytest
from agent_bisect.adapters.tau2_batch import items_for, record_batch, with_task
from agent_bisect.adapters.tau2_scenarios import AIRLINE_READS
from agent_bisect.core.run_stats import (
    InjectionBuckets,
    RunStats,
    bucket_of,
    injection_sites,
    summarise_runs,
)
from tests.tau2_offline import Store, quiet_tau2, scripted_session, spec_for

pytestmark = pytest.mark.usefixtures("_no_real_key")

RECORDED = 2


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


@pytest.fixture
def recorded(tmp_path) -> Store:
    store = Store(tmp_path / "runs")
    with scripted_session(AIRLINE_READS, store.root):
        record_batch(
            items_for("airline", [str(index) for index in range(RECORDED)]),
            spec_for=lambda item: with_task(spec_for(AIRLINE_READS), item),
            store=store.blobs,
            tape=store.tape,
            reader=store.reader,
            root=store.root,
        )
    return store


# ---- the early / middle / late split ----


@pytest.mark.parametrize(
    ("position", "total", "expected"),
    [
        (0, 9, "early"),
        (2, 9, "early"),
        (3, 9, "middle"),
        (5, 9, "middle"),
        (6, 9, "late"),
        (8, 9, "late"),
        (0, 1, "early"),
        (0, 2, "early"),
        # Thirds are by fraction of the run, so in a two-step run the
        # second step is 1/2 of the way through: the middle third, not the
        # last. Real runs are 4+ steps, where this never bites.
        (1, 2, "middle"),
        (4, 5, "late"),
    ],
)
def test_a_step_falls_in_the_third_of_the_run_it_belongs_to(position, total, expected):
    assert bucket_of(position, total) == expected


def test_bucket_of_refuses_a_position_outside_the_run():
    with pytest.raises(ValueError, match="position"):
        bucket_of(5, 3)


# ---- injection sites ----


def test_only_tool_steps_are_injection_sites(recorded):
    """A planted fault replaces a tool *result*, so nothing else qualifies."""
    sites = injection_sites(recorded.reader, recorded.blobs, "airline-0-t0")

    steps = {step.step_idx: step for step in recorded.reader.get_steps("airline-0-t0")}
    assert {site.step_idx for site in sites} == {
        idx for idx, step in steps.items() if step.actor == "tool"
    }


def test_a_site_says_whether_its_recorded_result_was_already_an_error(recorded):
    """The airline-reads script looks up a reservation that does not exist."""
    sites = injection_sites(recorded.reader, recorded.blobs, "airline-0-t0")

    errored = [site for site in sites if site.errored]
    assert [site.tool_name for site in errored] == ["get_reservation_details"]


def test_every_site_carries_its_bucket(recorded):
    sites = injection_sites(recorded.reader, recorded.blobs, "airline-0-t0")

    assert all(site.bucket in {"early", "middle", "late"} for site in sites)


def test_injection_sites_of_an_unrecorded_run_are_empty(recorded):
    assert injection_sites(recorded.reader, recorded.blobs, "nope") == []


# ---- the summary ----


def test_summary_counts_the_runs_and_how_many_passed(recorded):
    stats = summarise_runs(recorded.reader, recorded.blobs, recorded.root)

    assert isinstance(stats, RunStats)
    assert stats.runs == RECORDED
    assert stats.passed + stats.failed == RECORDED


def test_summary_reports_mean_steps_and_mean_calls_split_by_actor(recorded):
    stats = summarise_runs(recorded.reader, recorded.blobs, recorded.root)

    assert stats.mean_steps > 0
    assert stats.mean_agent_calls > 0
    assert stats.mean_user_calls > 0
    assert stats.mean_llm_calls == pytest.approx(
        stats.mean_agent_calls + stats.mean_user_calls + stats.mean_evaluator_calls
    )


def test_summary_buckets_the_injection_sites(recorded):
    stats = summarise_runs(recorded.reader, recorded.blobs, recorded.root)

    assert isinstance(stats.injection_sites, InjectionBuckets)
    assert stats.injection_sites.total == stats.injection_sites.early + (
        stats.injection_sites.middle + stats.injection_sites.late
    )
    assert stats.injection_sites.total > 0


def test_summary_reports_clean_sites_separately_from_all_of_them(recorded):
    """A tool result that already errored is a poor thing to break."""
    stats = summarise_runs(recorded.reader, recorded.blobs, recorded.root)

    assert stats.injection_sites.clean < stats.injection_sites.total


def test_summary_of_an_empty_store_says_so_rather_than_dividing_by_zero(tmp_path):
    from agent_bisect.core.store import BlobStore
    from agent_bisect.core.tape import TapeReader

    empty = tmp_path / "runs"
    empty.mkdir()
    stats = summarise_runs(TapeReader(empty), BlobStore(empty), empty)

    assert stats.runs == 0
    assert stats.mean_steps == 0.0


def test_summary_reports_the_call_span_per_run_when_a_ledger_has_one(recorded):
    """Wall time comes from the ledger: the span from a run's first
    reserved call to its last."""
    stats = summarise_runs(recorded.reader, recorded.blobs, recorded.root)

    assert stats.mean_call_span_s >= 0.0


def test_summary_is_serialisable(recorded):
    stats = summarise_runs(recorded.reader, recorded.blobs, recorded.root)

    assert stats.model_dump(mode="json")["runs"] == RECORDED
