"""Tests for the `bisect` CLI: doctor formatting/exit codes, and stub commands.

`doctor`'s own checks are exercised in test_doctor.py against fakes; here
we monkeypatch `agent_bisect.cli.run_doctor` itself so the CLI layer
(exit codes, --json vs human output) is tested with zero real subprocess,
import, or network side effects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_bisect import cli
from agent_bisect.core.doctor import CheckResult
from typer.testing import CliRunner

runner = CliRunner()

ALL_PASSING = [
    CheckResult("nvidia_api_key", True, "found"),
    CheckResult("uv_and_python", True, "uv 0.5.0, python 3.12.4"),
]

ONE_FAILING = [
    CheckResult("nvidia_api_key", True, "found"),
    CheckResult("valid_tool_call_rate", False, "not measured yet (P0b)"),
]


@pytest.fixture(autouse=True)
def _isolate_settings_lookup(monkeypatch):
    # doctor() calls get_settings(); avoid touching the real environment/.env.
    monkeypatch.setattr(cli, "get_settings", lambda: object())


def test_doctor_exits_zero_when_all_checks_pass(monkeypatch):
    monkeypatch.setattr(cli, "run_doctor", lambda settings, **kwargs: ALL_PASSING)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "nvidia_api_key" in result.stdout


def test_doctor_exits_nonzero_when_a_check_fails(monkeypatch):
    monkeypatch.setattr(cli, "run_doctor", lambda settings, **kwargs: ONE_FAILING)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1


def test_doctor_human_output_marks_pass_and_fail(monkeypatch):
    monkeypatch.setattr(cli, "run_doctor", lambda settings, **kwargs: ONE_FAILING)

    result = runner.invoke(cli.app, ["doctor"])

    assert "✓ nvidia_api_key" in result.stdout
    assert "✗ valid_tool_call_rate" in result.stdout


def test_doctor_json_output_is_valid_json(monkeypatch):
    monkeypatch.setattr(cli, "run_doctor", lambda settings, **kwargs: ALL_PASSING)

    result = runner.invoke(cli.app, ["doctor", "--json"])

    payload = json.loads(result.stdout)
    assert payload == [
        {"name": "nvidia_api_key", "passed": True, "detail": "found"},
        {"name": "uv_and_python", "passed": True, "detail": "uv 0.5.0, python 3.12.4"},
    ]


def test_gate_prints_the_comment_and_exits_with_the_gate_code(monkeypatch, tmp_path):
    """`bisect gate` is thin: it builds a `GateConfig`, calls `run_gate`, and
    surfaces whatever exit code and comment that returns -- exercised here
    against a fake `run_gate` so the CLI layer needs no worktree or subprocess
    (`tests/test_gate_action.py` covers `run_gate` itself)."""
    from agent_bisect import cli_gate

    document = {"comment_markdown": "Bisect - agent suite unchanged", "is_regression": False}
    monkeypatch.setattr(cli_gate, "run_gate", lambda config: (0, document))

    result = runner.invoke(
        cli.app, ["gate", "--base", "main", "--head", "feature", "--out", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert "agent suite unchanged" in result.stdout


def test_gate_exits_1_on_a_regression(monkeypatch, tmp_path):
    from agent_bisect import cli_gate

    document = {"comment_markdown": "Bisect - agent regression detected", "is_regression": True}
    monkeypatch.setattr(cli_gate, "run_gate", lambda config: (1, document))

    result = runner.invoke(
        cli.app, ["gate", "--base", "main", "--head", "feature", "--out", str(tmp_path)]
    )

    assert result.exit_code == 1


def test_gate_exits_2_on_a_gate_error(monkeypatch, tmp_path):
    from agent_bisect import cli_gate
    from agent_bisect.gate.action import GateError

    def raises(config):
        raise GateError("base ref does not resolve")

    monkeypatch.setattr(cli_gate, "run_gate", raises)

    result = runner.invoke(
        cli.app, ["gate", "--base", "nope", "--head", "feature", "--out", str(tmp_path)]
    )

    assert result.exit_code == 2
    assert "base ref does not resolve" in result.stderr


def test_gate_rejects_an_unsupported_suite(tmp_path):
    result = runner.invoke(
        cli.app,
        ["gate", "--base", "main", "--head", "feature", "--suite", "live", "--out", str(tmp_path)],
    )

    assert result.exit_code == 2


def test_doctor_passes_the_live_flag_through_to_run_doctor(monkeypatch):
    seen = {}

    def fake(settings, **kwargs):
        seen.update(kwargs)
        return ALL_PASSING

    monkeypatch.setattr(cli, "run_doctor", fake)

    runner.invoke(cli.app, ["doctor", "--live"])

    assert seen["live"] is True


def test_doctor_does_not_run_live_by_default(monkeypatch):
    seen = {}

    def fake(settings, **kwargs):
        seen.update(kwargs)
        return ALL_PASSING

    monkeypatch.setattr(cli, "run_doctor", fake)

    runner.invoke(cli.app, ["doctor"])

    assert seen["live"] is False


# ---- the commands that are no longer stubs ----


@pytest.mark.parametrize("command", ["record", "replay", "serve"])
def test_registered_commands_are_no_longer_stubs(command):
    result = runner.invoke(cli.app, [command, "--help"])

    assert result.exit_code == 0
    assert "not implemented yet" not in result.stdout


def test_record_is_the_real_record_command():
    from agent_bisect.cli_record import record

    assert cli.record is record


def test_replay_is_the_real_replay_command():
    from agent_bisect.cli_replay import replay

    assert cli.replay is replay


# ---- serve ----


def _serve_spy(monkeypatch) -> dict:
    seen: dict = {}

    def fake(host, port, data_source, **kwargs):
        seen.update({"host": host, "port": port, "data_source": data_source, **kwargs})

    monkeypatch.setattr(cli, "run_server", fake)
    return seen


def test_serve_defaults_to_loopback_and_8484(monkeypatch, tmp_path):
    seen = _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--runs-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8484


def test_serve_uses_real_data_when_a_tape_exists(monkeypatch, tmp_path):
    (tmp_path / "index.sqlite").write_bytes(b"")
    seen = _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--runs-dir", str(tmp_path)])

    assert seen["data_source"] == "real"
    assert "real" in result.stdout


def test_serve_falls_back_to_fixtures_and_says_so(monkeypatch, tmp_path):
    """Simulated data must never be served without announcing itself."""
    seen = _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--runs-dir", str(tmp_path)])

    assert seen["data_source"] == "fixture"
    assert "simulated" in result.stdout.lower()


def test_serve_fixture_flag_overrides_an_existing_tape(monkeypatch, tmp_path):
    (tmp_path / "index.sqlite").write_bytes(b"")
    seen = _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--fixture", "--runs-dir", str(tmp_path)])

    assert seen["data_source"] == "fixture"
    assert "simulated" in result.stdout.lower()


def test_serve_real_flag_refuses_when_there_is_no_tape(monkeypatch, tmp_path):
    """Better to say there is nothing recorded than to serve an empty page."""
    _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--real", "--runs-dir", str(tmp_path)])

    assert result.exit_code != 0
    assert "no recorded runs" in result.output


def test_serve_data_dir_option_passes_through_to_run_server(monkeypatch, tmp_path):
    """`--real` on an installed wheel needs to find `data/manifest.json` and
    `data/results/*` somewhere other than the current directory."""
    seen = _serve_spy(monkeypatch)
    data_dir = tmp_path / "some-data"

    result = runner.invoke(
        cli.app, ["serve", "--runs-dir", str(tmp_path), "--data-dir", str(data_dir)]
    )

    assert result.exit_code == 0
    assert seen["data_dir"] == data_dir


def test_serve_data_dir_defaults_to_data(monkeypatch, tmp_path):
    seen = _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--runs-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert seen["data_dir"] == Path("data")


def test_serve_models_config_option_passes_through_to_run_server(monkeypatch, tmp_path):
    """Same need as --data-dir: an installed wheel run from elsewhere still
    has to find config/models.toml for a real /api/meta."""
    seen = _serve_spy(monkeypatch)
    models_config = tmp_path / "some-config" / "models.toml"

    result = runner.invoke(
        cli.app, ["serve", "--runs-dir", str(tmp_path), "--models-config", str(models_config)]
    )

    assert result.exit_code == 0
    assert seen["models_path"] == models_config


def test_serve_models_config_defaults_to_config_models_toml(monkeypatch, tmp_path):
    seen = _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--runs-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert seen["models_path"] == Path("config/models.toml")


def test_serve_passes_an_explicit_host_through_as_explicit(monkeypatch, tmp_path):
    """run_server refuses a non-loopback bind unless the operator asked."""
    seen = _serve_spy(monkeypatch)

    runner.invoke(cli.app, ["serve", "--host", "0.0.0.0", "--runs-dir", str(tmp_path)])

    assert seen["host"] == "0.0.0.0"
    assert seen["explicit_host"] is True


def test_serve_does_not_claim_an_explicit_host_by_default(monkeypatch, tmp_path):
    seen = _serve_spy(monkeypatch)

    runner.invoke(cli.app, ["serve", "--runs-dir", str(tmp_path)])

    assert seen["explicit_host"] is False


def test_serve_prints_the_url_it_is_about_to_bind(monkeypatch, tmp_path):
    _serve_spy(monkeypatch)

    result = runner.invoke(cli.app, ["serve", "--port", "9001", "--runs-dir", str(tmp_path)])

    assert "http://127.0.0.1:9001" in result.stdout


def test_inject_is_registered_with_its_three_commands():
    """`bisect inject collect | status | freeze` (P3). Registered in cli.py
    so the collection is driven by the shipped CLI rather than a script."""
    from agent_bisect.cli import app
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["inject", "--help"])

    assert result.exit_code == 0
    for command in ("collect", "status", "freeze"):
        assert command in result.output


def test_blame_and_eval_are_registered_not_stubbed():
    """P5's real commands replace the stubs; typer keeps whichever is
    registered last, so a stub left alongside would be silently ambiguous."""
    from agent_bisect.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()

    for command in ("blame", "eval"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, command
        assert "not implemented" not in result.output.lower()
