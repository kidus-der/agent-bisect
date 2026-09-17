"""The two P5 commands: what they refuse, and what they print when they do not."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer
from agent_bisect.attribution.judge_view import JudgeVerdict, RankedStep
from agent_bisect.attribution.search import RerunOutcome
from agent_bisect.bench.manifest import DatasetItem, freeze
from agent_bisect.cli_blame import (
    MISSING_KEY_EXIT_CODE,
    NO_STEP_BLAMED_EXIT_CODE,
    BlameRun,
    blame_run,
    format_human,
    payload_of,
)
from agent_bisect.cli_eval import MANIFEST_EXIT_CODE, SPLIT_LOCKED_EXIT_CODE, eval_
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import RunManifest, Step, TapeReader, TapeWriter
from typer.testing import CliRunner

runner = CliRunner()


# ---- a tiny recorded run to blame ----


def _tape(root: Path) -> tuple[TapeReader, BlobStore]:
    blobs = BlobStore(root)
    writer = TapeWriter(root)
    writer.start_run(
        RunManifest(
            run_id="r1", domain="airline", task_id="1", agent_model="a",
            user_model="u", tau2_commit="abc",
            created_at=datetime(2026, 9, 17, tzinfo=UTC),
        )
    )
    blank = blobs.put_json({})
    payload = blobs.put_json({"role": "tool", "content": "value"})
    for idx, actor in enumerate(["user", "agent", "tool", "agent"]):
        writer.append_step(
            Step(
                run_id="r1", step_idx=idx, actor=actor,  # type: ignore[arg-type]
                tool_name="get_reservation_details" if actor == "tool" else None,
                response_ref=blank if actor != "tool" else None,
                tool_result_ref=payload if actor == "tool" else None,
                state_before=blank, state_after=blank, state_hash="h",
            )
        )
    return TapeReader(root), blobs


class StubJudge:
    model = "fake-judge"

    def __init__(self, ranking: list[int]) -> None:
        self.ranking = ranking

    def ask(self, *, system, user, item_id, protocol):  # pragma: no cover - unused
        raise AssertionError("blame_run is given a verdict via judge_item's stub")


class ScriptedExecutor:
    def __init__(self, passing: set[int]) -> None:
        self.passing = passing
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        passed = request.arm == "treated" and request.fork_step in self.passing
        return RerunOutcome(passed=passed, n_steps=4, calls=3)


def _verdict(steps: list[int]) -> JudgeVerdict:
    return JudgeVerdict(
        item_id="r1", protocol="all_at_once", decisive_step=steps[0],
        ranking=tuple(
            RankedStep(step=s, rank=i + 1, score=0.9 - 0.1 * i, rationale="r")
            for i, s in enumerate(steps)
        ),
        rationale="the tool answered wrongly", calls=1,
    )


def _blame(tmp_path, monkeypatch, *, ranking, passing, max_n=4):
    from agent_bisect import cli_blame
    from agent_bisect.bench import baselines

    reader, blobs = _tape(tmp_path / "runs")
    monkeypatch.setattr(
        baselines, "judge_all_at_once", lambda *a, **k: _verdict(ranking)
    )
    monkeypatch.setattr(cli_blame, "DEFAULT_JUDGE_CONFIG", baselines.DEFAULT_JUDGE_CONFIG)
    executor = ScriptedExecutor(passing)
    run = blame_run(
        "r1",
        reader=reader,
        store=blobs,
        judge_backend=StubJudge(ranking),
        executor=executor,
        task_text=lambda domain, task: ("do the thing", "follow the policy"),
        top_m=3,
        max_n=max_n,
        seed=1,
        runs_dir=tmp_path / "runs",
        control_mode="per_step",
    )
    return run, executor


# ---- blame ----


def test_blame_names_the_step_whose_effect_clears_delta(tmp_path, monkeypatch):
    # Arrange / Act
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2, 1], passing={2})

    # Assert
    assert run.result.blamed_step == 2


def test_blame_writes_its_result_where_the_dashboard_reads_it(tmp_path, monkeypatch):
    # Arrange / Act
    _blame(tmp_path, monkeypatch, ranking=[2], passing={2})

    # Assert
    assert (tmp_path / "runs" / "blame" / "r1.json").exists()


def test_blame_blames_nothing_when_no_effect_clears_delta(tmp_path, monkeypatch):
    # Arrange / Act
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2, 1], passing=set())

    # Assert
    assert run.result.blamed_step is None


def test_the_printed_payload_carries_the_evidence_and_the_cost(tmp_path, monkeypatch):
    # Arrange
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2, 1], passing={2})

    # Act
    payload = payload_of(run, tmp_path / "runs")

    # Assert
    assert payload["blamed_step"] == 2
    assert payload["cost"]["judge_calls"] == 1
    assert payload["cost"]["replay_calls"] > 0
    assert payload["step_effects"]


def test_the_payload_names_the_intervention_applied_to_each_suspect(
    tmp_path, monkeypatch
):
    # Arrange / Act
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2, 1], passing={2})
    payload = payload_of(run, tmp_path / "runs")

    # Assert: step 2 is a tool step, step 1 an agent step
    assert payload["interventions"]["2"] == "truthful_tool_result"
    assert payload["interventions"]["1"] == "resample"


def test_the_human_output_marks_the_blamed_step(tmp_path, monkeypatch):
    # Arrange
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2, 1], passing={2})

    # Act
    text = format_human(payload_of(run, tmp_path / "runs"))

    # Assert
    assert "blame: step 2" in text
    assert "←" in text


def test_the_human_output_says_so_when_nothing_was_blamed(tmp_path, monkeypatch):
    # Arrange
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2], passing=set())

    # Act
    text = format_human(payload_of(run, tmp_path / "runs"))

    # Assert
    assert "no step blamed" in text


def test_blame_without_a_key_exits_one(tmp_path, monkeypatch, isolated_env):
    # Arrange
    from agent_bisect.cli_blame import blame

    app = typer.Typer()
    app.command()(blame)

    # Act
    result = runner.invoke(app, ["r1"])

    # Assert
    assert result.exit_code == MISSING_KEY_EXIT_CODE


def test_the_no_step_blamed_exit_code_is_distinct_from_an_error():
    # Arrange / Act / Assert
    assert NO_STEP_BLAMED_EXIT_CODE not in (0, 1)


# ---- eval ----


def _frozen(tmp_path) -> Path:
    path = tmp_path / "manifest.json"
    items = [
        DatasetItem(
            item_id=f"item-{i}", domain="airline", task_id=str(i),
            base_run_id=f"b{i}", base_pass_rate=1.0, run_id=f"r{i}",
            faulted_pass_rate=0.0, planted_step=2, position_bucket="middle",
            fault_type="wrong_value", mutation={}, oracle={}, intervention={},
            seeds=[1], n_reruns=4,
        )
        for i in range(6)
    ]
    freeze(
        items, path=path, models={"agent": "a", "judge": "j"},
        tau2_commit="abc", config={"delta": 0.1}, counts={"kept": 6},
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    return path


def _app():
    app = typer.Typer()
    app.command(name="eval")(eval_)
    return app


def test_eval_refuses_an_unfrozen_manifest(tmp_path):
    # Arrange / Act
    result = runner.invoke(
        _app(), ["--manifest", str(tmp_path / "absent.json"), "--split", "dev"]
    )

    # Assert
    assert result.exit_code == MANIFEST_EXIT_CODE


def test_eval_refuses_a_tampered_manifest(tmp_path):
    # Arrange
    path = _frozen(tmp_path)
    document = json.loads(path.read_text())
    document["counts"]["kept"] = 99
    path.write_text(json.dumps(document))

    # Act
    result = runner.invoke(_app(), ["--manifest", str(path), "--split", "dev"])

    # Assert
    assert result.exit_code == MANIFEST_EXIT_CODE
    assert "hash" in result.output + str(result.stderr or "")


def test_eval_refuses_the_test_split_without_the_freeze_decision(tmp_path, monkeypatch):
    # Arrange
    path = _frozen(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Act
    result = runner.invoke(
        _app(),
        ["--manifest", str(path), "--split", "test", "--out-dir", str(tmp_path / "p5")],
    )

    # Assert
    assert result.exit_code == SPLIT_LOCKED_EXIT_CODE


def test_report_only_rebuilds_the_report_without_a_key(tmp_path, isolated_env):
    # Arrange
    path = _frozen(tmp_path)
    out_dir = tmp_path / "p5"
    out_dir.mkdir()
    frozen = json.loads(path.read_text())
    dev = [item for item in frozen["items"] if item["split"] == "dev"]
    rows = [
        {
            "item_id": item["item_id"], "run_id": item["run_id"], "method": method,
            "predicted_step": 2 if method == "bisect" else 1,
            "ranking": [2, 1], "shortlist": [2, 1], "judge_calls": 1,
            "replay_calls": 100 if method == "bisect" else 0, "total_calls": 101,
            "reruns": 10, "control_reruns": 4, "parse_failed": False, "note": "",
        }
        for item in dev
        for method in ("bisect", "judge_all_at_once")
    ]
    (out_dir / "outcomes.json").write_text(json.dumps(rows))

    # Act
    result = runner.invoke(
        _app(),
        [
            "--manifest", str(path), "--split", "dev", "--report-only",
            "--out-dir", str(out_dir), "--results-dir", str(tmp_path / "results"),
        ],
    )

    # Assert
    assert result.exit_code == 0, result.output
    assert (tmp_path / "results" / "p5_summary.json").exists()


def test_report_only_is_offline_and_deterministic(tmp_path, isolated_env):
    # Arrange
    path = _frozen(tmp_path)
    out_dir = tmp_path / "p5"
    out_dir.mkdir()
    frozen = json.loads(path.read_text())
    dev = [item for item in frozen["items"] if item["split"] == "dev"]
    rows = [
        {
            "item_id": item["item_id"], "run_id": item["run_id"], "method": "bisect",
            "predicted_step": 2, "ranking": [2], "shortlist": [2], "judge_calls": 1,
            "replay_calls": 100, "total_calls": 101, "reruns": 10,
            "control_reruns": 4, "parse_failed": False, "note": "",
        }
        for item in dev
    ]
    (out_dir / "outcomes.json").write_text(json.dumps(rows))
    args = [
        "--manifest", str(path), "--split", "dev", "--report-only",
        "--out-dir", str(out_dir), "--results-dir", str(tmp_path / "results"),
    ]

    # Act
    runner.invoke(_app(), args)
    first = (tmp_path / "results" / "p5_summary.json").read_bytes()
    runner.invoke(_app(), args)
    second = (tmp_path / "results" / "p5_summary.json").read_bytes()

    # Assert
    assert first == second


def test_a_blame_run_is_a_pair_of_a_result_and_the_judge_output(tmp_path, monkeypatch):
    # Arrange / Act
    run, _ = _blame(tmp_path, monkeypatch, ranking=[2], passing={2})

    # Assert
    assert isinstance(run, BlameRun)
    assert run.judgement.all_at_once.decisive_step == 2
    assert run.judgement.step_by_step is None, "blame runs only the cheap protocol"


@pytest.mark.parametrize("arm", ["treated", "control"])
def test_both_arms_are_bought_for_each_tested_step(tmp_path, monkeypatch, arm):
    # Arrange / Act
    _, executor = _blame(tmp_path, monkeypatch, ranking=[2, 1], passing={2})

    # Assert
    assert any(request.arm == arm for request in executor.requests)
