"""Tests for the one-task end-to-end runner and the single definition of the pinned τ² settings."""

from __future__ import annotations

import json

import pytest
from agent_bisect.adapters import tau2_e2e
from agent_bisect.adapters.tau2_e2e import (
    TAU2_MAX_ERRORS,
    TAU2_MAX_STEPS,
    TAU2_SEED,
    run_airline_task,
    text_run_config,
    trial_seed,
)
from agent_bisect.core.budget import BudgetLedger

AGENT = "nvidia/nemotron-3-super-120b-a12b"
USER_SIM = "openai/gpt-oss-20b"


# ---- the pinned settings (0004 §1) ----


def test_config_carries_the_pinned_tau2_defaults():
    config = text_run_config(AGENT, USER_SIM)

    assert config.max_steps == TAU2_MAX_STEPS == 200
    assert config.max_errors == TAU2_MAX_ERRORS == 10
    assert config.seed == TAU2_SEED == 300
    assert config.num_trials == 1


def test_config_uses_the_default_agent_and_user_implementations():
    config = text_run_config(AGENT, USER_SIM)

    assert (config.agent, config.user) == ("llm_agent", "user_simulator")


def test_config_pins_both_temperatures_to_zero():
    config = text_run_config(AGENT, USER_SIM)

    assert config.llm_args_agent["temperature"] == 0.0
    assert config.llm_args_user["temperature"] == 0.0


def test_config_never_carries_the_api_key_into_tau2s_own_settings():
    """The key is injected per call by the router, so it cannot reach τ²'s results JSON."""
    config = text_run_config(AGENT, USER_SIM)

    assert "nvapi" not in config.model_dump_json()


def test_config_routes_the_chosen_models():
    config = text_run_config(AGENT, USER_SIM)

    assert (config.llm_agent, config.llm_user) == (AGENT, USER_SIM)


# ---- the derived seed ----


def test_trial_seed_is_deterministic():
    assert trial_seed() == trial_seed()


def test_trial_seed_matches_tau2s_own_derivation():
    """τ²'s batch runner seeds `random` with config.seed and draws trial 0's seed."""
    import random

    rng = random.Random()
    rng.seed(TAU2_SEED)
    assert trial_seed() == rng.randint(0, 1000000)


def test_a_different_config_seed_gives_a_different_trial_seed():
    assert trial_seed(301) != trial_seed(300)


# ---- run_airline_task ----


class FakeSimulation:
    def __init__(self, reward: float | None = 1.0, *, has_reward_info: bool = True):
        self.reward_info = type("R", (), {"reward": reward})() if has_reward_info else None
        self.termination_reason = type("T", (), {"value": "agent_stop"})()
        self.messages = [1, 2, 3]


@pytest.fixture
def _offline(monkeypatch, tmp_path):
    """Replace the two τ² entry points and the router; nothing touches the network."""
    from contextlib import contextmanager

    task = type("Task", (), {"id": "0"})()
    monkeypatch.setattr(tau2_e2e, "load_airline_tasks", lambda limit=None: [task])

    @contextmanager
    def fake_route(**_kwargs):
        yield object()

    monkeypatch.setattr(tau2_e2e, "route_tau2_llm", fake_route)
    monkeypatch.setattr(tau2_e2e, "ensure_tau2_data_dir", lambda: None)
    return tmp_path


def _patch_run_single_task(monkeypatch, simulation):
    import tau2.run

    monkeypatch.setattr(tau2.run, "run_single_task", lambda *a, **k: simulation)


def test_returns_the_numeric_reward(_offline, monkeypatch):
    _patch_run_single_task(monkeypatch, FakeSimulation(reward=0.0))

    result = run_airline_task(
        agent_model=AGENT,
        user_sim_model=USER_SIM,
        ledger=BudgetLedger(_offline / "ledger.sqlite"),
        out_path=_offline / "e2e.json",
    )

    assert result["reward"] == 0.0
    assert result["live"] is True


def test_records_which_models_produced_the_run(_offline, monkeypatch):
    _patch_run_single_task(monkeypatch, FakeSimulation())

    result = run_airline_task(
        agent_model=AGENT,
        user_sim_model=USER_SIM,
        ledger=BudgetLedger(_offline / "ledger.sqlite"),
        out_path=_offline / "e2e.json",
    )

    assert (result["agent"], result["user_sim"]) == (AGENT, USER_SIM)


def test_writes_the_result_where_the_doctor_reads_it(_offline, monkeypatch):
    _patch_run_single_task(monkeypatch, FakeSimulation())
    out = _offline / "e2e.json"

    run_airline_task(
        agent_model=AGENT,
        user_sim_model=USER_SIM,
        ledger=BudgetLedger(_offline / "ledger.sqlite"),
        out_path=out,
    )

    assert json.loads(out.read_text())["reward"] == 1.0


def test_a_simulation_without_reward_info_yields_no_reward(_offline, monkeypatch):
    _patch_run_single_task(monkeypatch, FakeSimulation(has_reward_info=False))

    result = run_airline_task(
        agent_model=AGENT,
        user_sim_model=USER_SIM,
        ledger=BudgetLedger(_offline / "ledger.sqlite"),
        out_path=_offline / "e2e.json",
    )

    assert result["reward"] is None


def test_out_path_none_skips_writing(_offline, monkeypatch):
    _patch_run_single_task(monkeypatch, FakeSimulation())

    result = run_airline_task(
        agent_model=AGENT,
        user_sim_model=USER_SIM,
        ledger=BudgetLedger(_offline / "ledger.sqlite"),
        out_path=None,
    )

    assert result["reward"] == 1.0
    assert not (_offline / "e2e.json").exists()
