"""Tests for agent_bisect.core.doctor: pure evaluators and run_doctor orchestration."""

from __future__ import annotations

import pytest
from agent_bisect.core.config import Settings
from agent_bisect.core.doctor import (
    AIRLINE_PASS_RATE_RANGE,
    MIN_VALID_TOOL_CALL_RATE,
    evaluate_airline_pass_rate,
    evaluate_e2e_task_reward,
    evaluate_key,
    evaluate_nim_reachable,
    evaluate_node,
    evaluate_tau2,
    evaluate_uv_python,
    evaluate_valid_tool_call_rate,
    load_models_config,
    run_doctor,
)
from pydantic import SecretStr

_FAKE_KEY = SecretStr("nvapi-" + "a" * 40)


def _settings(*, nvidia_api_key: SecretStr | None = _FAKE_KEY) -> Settings:
    return Settings(nvidia_api_key=nvidia_api_key)


# ---- evaluate_key ----


def test_evaluate_key_passes_when_present():
    assert evaluate_key(True).passed is True


def test_evaluate_key_fails_when_absent():
    result = evaluate_key(False)

    assert result.passed is False
    assert "NVIDIA_API_KEY" in result.detail


# ---- evaluate_uv_python ----


def test_evaluate_uv_python_passes_with_version():
    result = evaluate_uv_python("uv 0.5.0", "3.12.4")

    assert result.passed is True
    assert "3.12.4" in result.detail


def test_evaluate_uv_python_fails_without_uv():
    assert evaluate_uv_python(None, "3.12.4").passed is False


# ---- evaluate_node ----


def test_evaluate_node_passes_with_version():
    assert evaluate_node("v20.11.0").passed is True


def test_evaluate_node_fails_without_node():
    result = evaluate_node(None)

    assert result.passed is False
    assert "brew install node" in result.detail


# ---- evaluate_tau2 ----


def test_evaluate_tau2_passes_when_importable_and_data_loads():
    assert evaluate_tau2(True, True, "").passed is True


@pytest.mark.parametrize(("importable", "airline_loaded"), [(False, False), (True, False)])
def test_evaluate_tau2_fails_otherwise(importable, airline_loaded):
    assert evaluate_tau2(importable, airline_loaded, "boom").passed is False


# ---- evaluate_nim_reachable ----


def test_evaluate_nim_reachable_passthrough():
    assert evaluate_nim_reachable(True, "GET /v1/models -> 200").passed is True
    assert evaluate_nim_reachable(False, "timeout").passed is False


# ---- P0b-dependent evaluators: absent config.toml -> "not measured yet" ----


def test_valid_tool_call_rate_fails_when_config_absent():
    result = evaluate_valid_tool_call_rate(None)

    assert result.passed is False
    assert "not measured yet" in result.detail


def test_valid_tool_call_rate_passes_at_threshold():
    result = evaluate_valid_tool_call_rate({"valid_tool_call_rate": MIN_VALID_TOOL_CALL_RATE})

    assert result.passed is True


def test_valid_tool_call_rate_fails_below_threshold():
    below_threshold = MIN_VALID_TOOL_CALL_RATE - 0.01
    result = evaluate_valid_tool_call_rate({"valid_tool_call_rate": below_threshold})

    assert result.passed is False


def test_airline_pass_rate_fails_when_config_absent():
    result = evaluate_airline_pass_rate(None)

    assert result.passed is False
    assert "not measured yet" in result.detail


@pytest.mark.parametrize("rate", [AIRLINE_PASS_RATE_RANGE[0], AIRLINE_PASS_RATE_RANGE[1], 0.55])
def test_airline_pass_rate_passes_inside_window(rate):
    assert evaluate_airline_pass_rate({"airline_pass_rate": rate}).passed is True


@pytest.mark.parametrize("rate", [0.0, 0.34, 0.76, 1.0])
def test_airline_pass_rate_fails_outside_window(rate):
    assert evaluate_airline_pass_rate({"airline_pass_rate": rate}).passed is False


def test_e2e_task_reward_fails_when_config_absent():
    result = evaluate_e2e_task_reward(None)

    assert result.passed is False
    assert "not measured yet" in result.detail


def test_e2e_task_reward_passes_when_present():
    assert evaluate_e2e_task_reward({"e2e_task_reward": 0.8}).passed is True


# ---- load_models_config ----


def test_load_models_config_returns_none_when_missing(tmp_path):
    assert load_models_config(tmp_path / "missing.toml") is None


def test_load_models_config_reads_toml(tmp_path):
    path = tmp_path / "models.toml"
    path.write_text('valid_tool_call_rate = 0.97\nairline_pass_rate = 0.5\n')

    config = load_models_config(path)

    assert config == {"valid_tool_call_rate": 0.97, "airline_pass_rate": 0.5}


# ---- run_doctor orchestration, everything faked ----


def test_run_doctor_all_pass_when_everything_is_healthy_and_configured(tmp_path):
    settings = _settings()
    models_config = {
        "valid_tool_call_rate": 0.97,
        "airline_pass_rate": 0.55,
        "e2e_task_reward": 1.0,
    }

    results = run_doctor(
        settings,
        get_uv_version=lambda: "uv 0.5.0",
        get_node_version=lambda: "v20.11.0",
        get_tau2_status=lambda: (True, True, ""),
        get_nim_reachable=lambda: (True, "GET /v1/models -> 200"),
        load_models_config_fn=lambda: models_config,
    )

    assert all(r.passed for r in results)
    assert [r.name for r in results] == [
        "nvidia_api_key",
        "uv_and_python",
        "node",
        "tau2",
        "nim_reachable",
        "valid_tool_call_rate",
        "airline_pass_rate",
        "e2e_task_reward",
    ]


def test_run_doctor_fails_only_on_not_measured_yet_checks_when_config_absent():
    settings = _settings()

    results = run_doctor(
        settings,
        get_uv_version=lambda: "uv 0.5.0",
        get_node_version=lambda: "v20.11.0",
        get_tau2_status=lambda: (True, True, ""),
        get_nim_reachable=lambda: (True, "GET /v1/models -> 200"),
        load_models_config_fn=lambda: None,
    )

    by_name = {r.name: r for r in results}
    assert by_name["nvidia_api_key"].passed is True
    assert by_name["uv_and_python"].passed is True
    assert by_name["node"].passed is True
    assert by_name["tau2"].passed is True
    assert by_name["nim_reachable"].passed is True
    assert by_name["valid_tool_call_rate"].passed is False
    assert by_name["airline_pass_rate"].passed is False
    assert by_name["e2e_task_reward"].passed is False


def test_run_doctor_propagates_missing_key(tmp_path):
    settings = _settings(nvidia_api_key=None)

    results = run_doctor(
        settings,
        get_uv_version=lambda: "uv 0.5.0",
        get_node_version=lambda: "v20.11.0",
        get_tau2_status=lambda: (True, True, ""),
        get_nim_reachable=lambda: (False, "no key to test with"),
        load_models_config_fn=lambda: None,
    )

    by_name = {r.name: r for r in results}
    assert by_name["nvidia_api_key"].passed is False
    assert by_name["nim_reachable"].passed is False
