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
        ("record", "P1"),
        ("replay", "P2"),
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
