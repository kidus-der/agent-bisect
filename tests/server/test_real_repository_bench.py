"""`RealRepository.overview`/`.benchmark`/`.dataset` against real output of
`bench.evaluate.build_report` + `bench.results.write_results` +
`bench.manifest.freeze` -- the actual production functions, not hand-typed
JSON, per team-lead's instruction: build these tests on what the pipeline
itself produces."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from agent_bisect.bench.evaluate import ScoredItem, build_report
from agent_bisect.bench.manifest import DatasetItem, freeze
from agent_bisect.bench.metrics import classify
from agent_bisect.bench.results import write_results
from agent_bisect.core.tape import Outcome, RunManifest, Step, TapeWriter
from agent_bisect.server.real_repository import RealRepository
from agent_bisect.server.repository import DataNotAvailable

#: Belt-and-suspenders alongside this module's explicit `data_dir=` on
#: every construction below -- see conftest.py's `isolated_repo_cwd`.
pytestmark = pytest.mark.usefixtures("isolated_repo_cwd")


def _scored(
    item_id: str,
    method: str,
    run_id: str,
    *,
    planted: int,
    predicted: int | None,
    ranking: tuple[int, ...] = (),
) -> ScoredItem:
    verdict = classify(predicted=predicted, planted=planted)
    return ScoredItem(
        item_id=item_id,
        run_id=run_id,
        task_group=f"airline:{item_id}",
        domain="airline",
        split="test",
        fault_type="wrong_value",
        position_bucket="early",
        planted_step=planted,
        method=method,  # type: ignore[arg-type]
        predicted_step=predicted,
        verdict=verdict,
        correct=verdict == "exact",
        ranking=ranking,
        shortlist=ranking,
        judge_calls=1,
        replay_calls=18,
        reruns=2,
        parse_failed=False,
        note="",
    )


def _write_tape_run(runs_dir: Path, run_id: str) -> None:
    """A minimal real recording, just enough for `_run_summary_by_id`."""
    writer = TapeWriter(runs_dir)
    writer.start_run(
        RunManifest(
            run_id=run_id,
            domain="airline",
            task_id="refund_after_cancellation",
            agent_model="m",
            user_model="u",
            tau2_commit="c",
            created_at=datetime.now(UTC),
        )
    )
    writer.append_step(
        Step(
            run_id=run_id,
            step_idx=0,
            actor="agent",
            state_before="a",
            state_after="a",
            state_hash="h",
        )
    )
    writer.record_outcome(Outcome(run_id=run_id, reward=0.0))


@pytest.fixture
def p5_repo(tmp_path) -> RealRepository:
    """A `RealRepository` whose `data/results/*` came from real `build_report`
    + `write_results`, and whose tape index has the run `build_report`'s
    hero item points at."""
    runs_dir = tmp_path / "runs"
    data_dir = tmp_path / "data"
    _write_tape_run(runs_dir, "real-run-1")
    _write_tape_run(runs_dir, "real-run-2")

    scores = [
        _scored("item-a", "bisect", "real-run-1", planted=5, predicted=5, ranking=(5, 3)),
        _scored("item-a", "judge_all_at_once", "real-run-1", planted=5, predicted=None),
        _scored("item-b", "bisect", "real-run-2", planted=7, predicted=7, ranking=(7, 2)),
        _scored("item-b", "judge_all_at_once", "real-run-2", planted=7, predicted=None),
    ]
    report = build_report(scores, split="test", seed=20260917, bootstrap_resamples=200)
    write_results(
        scores=scores,
        outcome_rows=[],
        report=report,
        runs_dir=runs_dir / "p5",
        results_dir=data_dir / "results",
    )
    return RealRepository(runs_dir=runs_dir, data_dir=data_dir)


def test_benchmark_is_not_available_before_any_evaluation(tmp_path):
    repo = RealRepository(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data")
    with pytest.raises(DataNotAvailable):
        repo.benchmark()


def test_benchmark_reads_the_real_method_comparison(p5_repo):
    summary = p5_repo.benchmark()
    methods = {m.method: m for m in summary.methods}
    assert methods["bisect"].accuracy.value == 1.0
    assert methods["bisect"].mean_cost_usd is None  # never fabricated
    assert methods["judge_all_at_once"].accuracy.value == 0.0


def test_benchmark_cost_histogram_buckets_bisects_real_call_counts(p5_repo):
    summary = p5_repo.benchmark()
    # Both bisect rows spent judge_calls(1) + replay_calls(18) = 19 calls,
    # the same real total_calls build_report/item_rows computed -- one bucket.
    assert len(summary.cost_histogram) == 1
    assert summary.cost_histogram[0].count == 2


def test_benchmark_flaky_ablation_is_none_when_no_flaky_run_exists(p5_repo):
    assert p5_repo.benchmark().flaky_ablation is None


def test_overview_is_not_available_before_any_evaluation(tmp_path):
    repo = RealRepository(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data")
    with pytest.raises(DataNotAvailable):
        repo.overview()


def test_overview_headline_and_kpis_are_real(p5_repo):
    payload = p5_repo.overview()
    assert payload.headline.bisect.value == 1.0
    assert payload.headline.best_judge_method == "judge_all_at_once"
    assert payload.headline.gap.value == 1.0
    assert payload.kpis.runs_recorded == 2
    assert payload.kpis.cost_per_diagnosis_usd is None  # never fabricated
    assert payload.kpis.cost_per_diagnosis_calls is None  # nothing blamed yet (no runs/blame/)


def test_overview_recall_provenance_mirrors_the_real_report(p5_repo):
    provenance = p5_repo.overview().recall_provenance
    assert provenance.measured_to_m == 3
    assert provenance.beyond_is_judge_ranking_only is True


def test_overview_hero_run_is_the_earliest_exact_bisect_diagnosis(p5_repo):
    hero = p5_repo.overview().hero_run
    assert hero is not None
    assert hero.run_id == "real-run-1"  # "item-a" < "item-b", both exact


def test_overview_hero_run_is_none_without_degrading_the_rest(tmp_path):
    """Caught against p5-blame's real toy output: P5 results with no
    matching tape index (`runs/index.sqlite` never built) must not take
    the whole Overview payload down -- only the one slot that needs it."""
    runs_dir = tmp_path / "runs"
    data_dir = tmp_path / "data"
    # No _write_tape_run call: the hero item's run_id resolves nowhere.
    scores = [
        _scored("item-a", "bisect", "unindexed-run", planted=5, predicted=5, ranking=(5, 3)),
        _scored("item-a", "judge_all_at_once", "unindexed-run", planted=5, predicted=None),
    ]
    report = build_report(scores, split="test", seed=20260917, bootstrap_resamples=200)
    write_results(
        scores=scores,
        outcome_rows=[],
        report=report,
        runs_dir=runs_dir / "p5",
        results_dir=data_dir / "results",
    )
    repo = RealRepository(runs_dir=runs_dir, data_dir=data_dir)

    payload = repo.overview()

    assert payload.hero_run is None
    assert payload.headline.bisect.value == 1.0


def test_dataset_is_not_available_before_a_frozen_manifest(tmp_path):
    repo = RealRepository(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data")
    with pytest.raises(DataNotAvailable):
        repo.dataset(1, 10)


def test_dataset_reads_a_real_frozen_manifest(tmp_path):
    data_dir = tmp_path / "data"
    item = DatasetItem(
        item_id="item-a",
        domain="airline",
        task_id="refund_after_cancellation",
        base_run_id="base-run-1",
        base_pass_rate=0.9,
        run_id="real-run-1",
        faulted_pass_rate=0.1,
        planted_step=5,
        position_bucket="early",
        fault_type="wrong_value",
        mutation={},
        oracle={},
        intervention={},
        seeds=[1, 2],
        n_reruns=2,
    )
    freeze(
        [item],
        path=data_dir / "manifest.json",
        models={"agent_model": "m"},
        tau2_commit="deadbeef",
        config={},
        counts={},
        created_at=datetime.now(UTC),
    )
    repo = RealRepository(runs_dir=tmp_path / "runs", data_dir=data_dir)

    page, total = repo.dataset(1, 10)

    assert total == 1
    assert page.entries[0].run_id == "real-run-1"
    assert page.entries[0].split in ("dev", "test")
