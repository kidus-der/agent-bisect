"""`demo.blame_cli`'s pure helpers, plus `run_blame_cli`/`main` with
`demo.blame.blame_new_failure` and the recording session faked out.

The real confirmation (a real tau2 orchestrator, real forks) is exercised
end to end by `scripts/gates/p7.py`'s self-test; what's covered here is
this module's own orchestration -- one summary row per failure, the
result file it writes, the CLI's argv handling -- with no tau2 call at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agent_bisect.attribution.estimate import ArmResult, RunEstimate, StepEffect
from agent_bisect.attribution.judge_view import JudgeVerdict
from agent_bisect.attribution.search import BlameConfig, BlameResult
from agent_bisect.core.tape import RunManifest, Step, TapeReader, TapeWriter
from demo.blame_cli import _effect_of, _load_failures, _parse_args, _step_identity


def _step_effect(
    step: int, *, effect: float, ci_low: float, ci_high: float, treated_n: int
) -> StepEffect:
    return StepEffect(
        step=step,
        treated=ArmResult(successes=treated_n, n=treated_n),
        control=ArmResult(successes=0, n=treated_n),
        effect=effect, ci_low=ci_low, ci_high=ci_high,
        n_batches=1, stop_reason="blameworthy",
    )


def _blame_result(*, blamed_step: int | None, step_effects: tuple[StepEffect, ...]) -> BlameResult:
    verdict = JudgeVerdict(
        item_id="item-1", protocol="all_at_once", decisive_step=blamed_step,
        ranking=(), rationale="test", calls=0,
    )
    estimate = None
    if step_effects:
        estimate = RunEstimate(
            step_effects=step_effects, blamed_step=blamed_step, control_mode="shared",
            control_fork_step=step_effects[0].step, treated_reruns=8, control_reruns=8,
            sampler_calls=1,
        )
    return BlameResult(
        item_id="item-1", run_id="run-1", method="bisect", blamed_step=blamed_step,
        estimate=estimate, reruns=(), judge=verdict, shortlist=(0,), tested_steps=(0,),
        interventions={}, untestable=(), judge_calls=0, replay_calls=8,
        config=BlameConfig(),
    )


def test_effect_of_none_when_nothing_was_blamed():
    result = _blame_result(blamed_step=None, step_effects=())

    assert _effect_of(result) is None


def test_effect_of_picks_out_the_blamed_steps_own_effect():
    effects = (
        _step_effect(2, effect=1.0, ci_low=0.54, ci_high=1.0, treated_n=8),
        _step_effect(3, effect=0.0, ci_low=-0.3, ci_high=0.3, treated_n=8),
    )
    result = _blame_result(blamed_step=2, step_effects=effects)

    effect = _effect_of(result)

    assert effect == {"effect": 1.0, "ci_low": 0.54, "ci_high": 1.0, "n": 8}


def test_effect_of_none_when_the_estimate_has_no_matching_step():
    effects = (_step_effect(5, effect=0.0, ci_low=0.0, ci_high=0.0, treated_n=8),)
    result = _blame_result(blamed_step=2, step_effects=effects)

    assert _effect_of(result) is None


def test_load_failures_parses_the_gate_orchestrators_json(tmp_path):
    path = tmp_path / "failures.json"
    path.write_text(
        json.dumps(
            {
                "failures": [
                    {
                        "scenario_name": "a", "run_index": 0,
                        "head_run_id": "demo-a-0-s1", "base_run_id": "demo-a-0-s1",
                    }
                ]
            }
        )
    )

    failures = _load_failures(path)

    assert len(failures) == 1
    assert failures[0].scenario_name == "a"
    assert failures[0].head_run_id == "demo-a-0-s1"


def test_load_failures_of_an_empty_list_is_empty(tmp_path):
    path = tmp_path / "failures.json"
    path.write_text(json.dumps({"failures": []}))

    assert _load_failures(path) == []


def _manifest(run_id: str) -> RunManifest:
    from datetime import UTC, datetime

    return RunManifest(
        run_id=run_id, domain="mock", task_id="t", agent_model="a", user_model="u",
        tau2_commit="unknown", created_at=datetime.now(UTC),
    )


def test_step_identity_is_none_when_nothing_was_blamed(tmp_path):
    reader = TapeReader(tmp_path)

    assert _step_identity(reader, "run-1", None) is None


def test_step_identity_reports_the_blamed_steps_actor_and_tool(tmp_path):
    tape = TapeWriter(tmp_path)
    tape.start_run(_manifest("run-1"))
    tape.append_step(
        Step(
            run_id="run-1", step_idx=0, actor="tool", tool_name="get_users", tool_args={},
            state_before="s", state_after="s", state_hash="h",
        )
    )
    reader = TapeReader(tmp_path)

    identity = _step_identity(reader, "run-1", 0)

    assert identity == {"actor": "tool", "tool_name": "get_users"}


def test_parse_args_reads_the_required_options():
    args = _parse_args(
        [
            "--failures", "f.json", "--head-store", "hs", "--base-store", "bs", "--out", "o",
        ]
    )

    assert args.failures == Path("f.json")
    assert args.head_store == Path("hs")
    assert args.base_store == Path("bs")
    assert args.out == Path("o")
    assert args.seed == 20260917


def test_parse_args_accepts_a_seed_override():
    args = _parse_args(
        ["--failures", "f", "--head-store", "h", "--base-store", "b", "--out", "o", "--seed", "7"]
    )

    assert args.seed == 7


# ---- run_blame_cli / main, with blame_new_failure and the session faked --


def test_run_blame_cli_writes_one_summary_row_per_failure(monkeypatch, tmp_path):
    from contextlib import contextmanager

    import demo.blame_cli as blame_cli_module

    failures_path = tmp_path / "failures.json"
    failures_path.write_text(
        json.dumps(
            {
                "failures": [
                    {
                        "scenario_name": "a", "run_index": 0,
                        "head_run_id": "demo-a-0-s1", "base_run_id": "demo-a-0-s1",
                    },
                    {
                        "scenario_name": "b", "run_index": 1,
                        "head_run_id": "demo-b-1-s1", "base_run_id": "demo-b-1-s1",
                    },
                ]
            }
        )
    )
    (tmp_path / "head").mkdir()
    (tmp_path / "base").mkdir()
    out_dir = tmp_path / "out"

    results = {
        "demo-a-0-s1": _blame_result(blamed_step=2, step_effects=(_step_effect(
            2, effect=1.0, ci_low=0.5, ci_high=1.0, treated_n=8
        ),)),
        "demo-b-1-s1": _blame_result(blamed_step=None, step_effects=()),
    }
    saved = []

    fake_router = SimpleNamespace(completion=lambda **kw: None)

    @contextmanager
    def fake_session(**kwargs):
        yield fake_router

    monkeypatch.setattr(blame_cli_module, "ensure_tau2_data_dir", lambda: None)
    monkeypatch.setattr(blame_cli_module, "recording_session", lambda **kw: fake_session())
    monkeypatch.setattr(
        blame_cli_module, "blame_new_failure",
        lambda failure, **kw: results[failure.head_run_id],
    )
    monkeypatch.setattr(blame_cli_module, "save_blame", lambda root, result: saved.append(result))
    monkeypatch.setattr(
        blame_cli_module, "_step_identity",
        lambda reader, run_id, step: {"actor": "tool", "tool_name": "get_users"} if step else None,
    )

    summaries = blame_cli_module.run_blame_cli(
        failures_path=failures_path, head_store_dir=tmp_path / "head",
        base_store_dir=tmp_path / "base", out_dir=out_dir, seed=1,
    )

    assert len(summaries) == 2
    assert summaries[0]["blamed_step"] == 2
    assert summaries[0]["step"] == {"actor": "tool", "tool_name": "get_users"}
    assert summaries[1]["blamed_step"] is None
    assert len(saved) == 2


def test_main_writes_the_result_file_and_prints_it(monkeypatch, tmp_path, capsys):
    import demo.blame_cli as blame_cli_module

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.setattr(
        blame_cli_module, "run_blame_cli", lambda **kwargs: [{"blamed_step": 2}]
    )

    code = blame_cli_module.main(
        [
            "--failures", str(tmp_path / "f.json"), "--head-store", str(tmp_path / "h"),
            "--base-store", str(tmp_path / "b"), "--out", str(out_dir),
        ]
    )

    assert code == 0
    written = json.loads((out_dir / "failures_result.json").read_text())
    assert written == [{"blamed_step": 2}]
    assert "blamed_step" in capsys.readouterr().out
