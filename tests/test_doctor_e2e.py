"""Tests for the doctor's end-to-end check: recorded by default, live under `--live`."""

from __future__ import annotations

import json

import pytest
from agent_bisect.core.config import Settings
from agent_bisect.core.doctor import (
    evaluate_e2e_task_reward,
    load_e2e_result,
    run_doctor,
)
from pydantic import SecretStr

MODELS = {
    "agent": "nvidia/nemotron-3-super-120b-a12b",
    "user_sim": "openai/gpt-oss-20b",
    "judge": "moonshotai/kimi-k3",
}


def _e2e(**overrides) -> dict:
    return {"task_id": "0", "reward": 1.0, "agent": MODELS["agent"],
            "user_sim": MODELS["user_sim"], "live": True, **overrides}


def _settings() -> Settings:
    return Settings(nvidia_api_key=SecretStr("nvapi-" + "a" * 40))


# ---- evaluate_e2e_task_reward ----


def test_fails_when_no_end_to_end_run_has_been_recorded():
    result = evaluate_e2e_task_reward(MODELS, None)

    assert result.passed is False
    assert "no end-to-end" in result.detail


def test_passes_on_a_numeric_reward():
    result = evaluate_e2e_task_reward(MODELS, _e2e(reward=0.0))

    assert result.passed is True
    assert "reward=0.0" in result.detail


def test_a_reward_of_zero_still_passes_because_the_gate_asks_for_a_number():
    assert evaluate_e2e_task_reward(MODELS, _e2e(reward=0.0)).passed is True


def test_fails_when_the_reward_is_not_a_number():
    result = evaluate_e2e_task_reward(MODELS, _e2e(reward=None))

    assert result.passed is False
    assert "numeric" in result.detail


def test_fails_when_a_bool_is_passed_off_as_a_reward():
    assert evaluate_e2e_task_reward(MODELS, _e2e(reward=True)).passed is False


def test_fails_when_the_run_used_a_different_agent_than_the_chosen_one():
    result = evaluate_e2e_task_reward(MODELS, _e2e(agent="some/other-model"))

    assert result.passed is False
    assert "some/other-model" in result.detail


def test_fails_when_the_run_used_a_different_user_simulator():
    assert evaluate_e2e_task_reward(MODELS, _e2e(user_sim="some/other")).passed is False


def test_fails_when_models_config_is_missing():
    assert evaluate_e2e_task_reward(None, _e2e()).passed is False


# ---- load_e2e_result ----


def test_load_returns_none_when_the_file_is_absent(tmp_path):
    assert load_e2e_result(tmp_path / "absent.json") is None


def test_load_reads_a_recorded_result(tmp_path):
    path = tmp_path / "e2e.json"
    path.write_text(json.dumps(_e2e()))

    assert load_e2e_result(path) == _e2e()


def test_load_returns_none_on_corrupt_json(tmp_path):
    path = tmp_path / "e2e.json"
    path.write_text("{not json")

    assert load_e2e_result(path) is None


# ---- run_doctor wiring ----


def _collectors(**overrides):
    base = {
        "get_uv_version": lambda: "uv 0.5.0",
        "get_node_version": lambda: "v22.0.0",
        "get_tau2_status": lambda: (True, True, "ok"),
        "get_nim_reachable": lambda: (True, "200"),
        "load_models_config_fn": lambda: {
            **MODELS, "valid_tool_call_rate": 0.99, "airline_pass_rate": 0.55
        },
        "load_e2e_fn": lambda: _e2e(),
    }
    return {**base, **overrides}


def test_without_live_the_doctor_reads_the_recorded_result_and_never_runs_a_task():
    ran = []

    results = run_doctor(
        _settings(),
        **_collectors(run_live_e2e=lambda: ran.append("live") or _e2e()),
    )

    assert ran == []
    assert all(check.passed for check in results)


def test_live_runs_one_task_and_uses_its_reward():
    ran = []

    results = run_doctor(
        _settings(),
        live=True,
        **_collectors(run_live_e2e=lambda: ran.append("live") or _e2e(reward=0.0)),
    )

    assert ran == ["live"]
    e2e = next(c for c in results if c.name == "e2e_task_reward")
    assert e2e.passed is True
    assert "reward=0.0" in e2e.detail


def test_live_failure_is_reported_as_a_failed_check_not_a_crash():
    def explode():
        raise RuntimeError("NIM said no")

    results = run_doctor(_settings(), live=True, **_collectors(run_live_e2e=explode))

    e2e = next(c for c in results if c.name == "e2e_task_reward")
    assert e2e.passed is False
    assert "NIM said no" in e2e.detail


def test_doctor_reports_which_models_were_chosen():
    results = run_doctor(_settings(), **_collectors())

    chosen = next(c for c in results if c.name == "chosen_models")
    assert chosen.passed is True
    assert MODELS["agent"] in chosen.detail


def test_doctor_fails_when_no_models_have_been_chosen():
    results = run_doctor(_settings(), **_collectors(load_models_config_fn=lambda: None))

    chosen = next(c for c in results if c.name == "chosen_models")
    assert chosen.passed is False


@pytest.mark.parametrize("field", ["agent", "user_sim", "judge"])
def test_doctor_requires_every_role_to_be_filled(field):
    config = {**MODELS, "valid_tool_call_rate": 0.99, "airline_pass_rate": 0.55}
    config.pop(field)

    results = run_doctor(_settings(), **_collectors(load_models_config_fn=lambda: config))

    assert next(c for c in results if c.name == "chosen_models").passed is False
