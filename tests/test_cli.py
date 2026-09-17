"""Tests for the `bisect` CLI: doctor formatting/exit codes, and stub commands.

`doctor`'s own checks are exercised in test_doctor.py against fakes; here
we monkeypatch `agent_bisect.cli.run_doctor` itself so the CLI layer
(exit codes, --json vs human output) is tested with zero real subprocess,
import, or network side effects.
"""

from __future__ import annotations

import json

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


@pytest.mark.parametrize(
    ("command", "phase"),
    [
        ("blame", "P5"),
        ("inject", "P3"),
        ("eval", "P5"),
        ("serve", "P6"),
        ("gate", "P7"),
    ],
)
def test_stub_commands_exit_2_with_message(command, phase):
    result = runner.invoke(cli.app, [command])

    assert result.exit_code == 2
    assert f"not implemented yet (phase {phase})" in result.stdout


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
    assert "no recorded runs" in result.stdout


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
