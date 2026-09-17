"""Tests for the real (side-effecting) doctor collectors.

Subprocess/import/network are still faked here (monkeypatching
`subprocess.run`, `shutil.which`, and `httpx.get`) — these tests exercise
the collector functions' own logic (argv, error handling, response
parsing), not real tooling or the real network.
"""

from __future__ import annotations

import subprocess

import httpx
from agent_bisect.core import doctor
from agent_bisect.core.config import Settings
from pydantic import SecretStr


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_collect_uv_version_returns_stdout(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed("uv 0.5.0\n"))

    assert doctor.collect_uv_version() == "uv 0.5.0"


def test_collect_uv_version_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed("", returncode=1))

    assert doctor.collect_uv_version() is None


def test_collect_uv_version_returns_none_when_missing(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError("no uv")

    monkeypatch.setattr(subprocess, "run", _raise)

    assert doctor.collect_uv_version() is None


def test_collect_node_version_returns_none_when_not_on_path(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    assert doctor.collect_node_version() is None


def test_collect_node_version_returns_stdout_when_present(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed("v20.11.0\n"))

    assert doctor.collect_node_version() == "v20.11.0"


def test_collect_nim_reachable_no_key():
    settings = Settings(nvidia_api_key=None)

    reachable, detail = doctor.collect_nim_reachable(settings)

    assert reachable is False
    assert "no key" in detail


def test_collect_nim_reachable_success(monkeypatch):
    settings = Settings(nvidia_api_key=SecretStr("nvapi-" + "a" * 40))

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())

    reachable, detail = doctor.collect_nim_reachable(settings)

    assert reachable is True
    assert "200" in detail


def test_collect_nim_reachable_non_200(monkeypatch):
    settings = Settings(nvidia_api_key=SecretStr("nvapi-" + "a" * 40))

    class FakeResponse:
        status_code = 401

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())

    reachable, detail = doctor.collect_nim_reachable(settings)

    assert reachable is False
    assert "401" in detail


def test_collect_nim_reachable_redacts_key_on_error(monkeypatch):
    key = "nvapi-" + "b" * 40
    settings = Settings(nvidia_api_key=SecretStr(key))

    def _raise(*a, **k):
        raise httpx.ConnectError(f"failed with key {key}")

    monkeypatch.setattr(httpx, "get", _raise)

    reachable, detail = doctor.collect_nim_reachable(settings)

    assert reachable is False
    assert key not in detail


def test_collect_tau2_status_reports_import_failure(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("agent_bisect.adapters.tau2_env.ensure_tau2_data_dir", _raise)

    importable, airline_loaded, detail = doctor.collect_tau2_status()

    assert importable is False
    assert airline_loaded is False
    assert "RuntimeError" in detail


def test_collect_tau2_status_real_import_succeeds():
    # tau2 is installed (editable, vendored) for this project's own dev env;
    # exercise the real happy path once.
    importable, airline_loaded, _detail = doctor.collect_tau2_status()

    assert importable is True
    assert airline_loaded is True
