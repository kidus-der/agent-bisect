"""Tests for agent_bisect.core.config: settings loading and redaction."""

from __future__ import annotations

from pathlib import Path

from agent_bisect.core.config import get_settings, redact

FAKE_KEY = "nvapi-" + "a" * 40


def test_get_settings_reads_key_from_env(isolated_env, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)

    settings = get_settings()

    assert settings.has_nvidia_key is True
    assert settings.nvidia_api_key is not None
    assert settings.nvidia_api_key.get_secret_value() == FAKE_KEY


def test_get_settings_no_key_present(isolated_env):
    settings = get_settings()

    assert settings.has_nvidia_key is False
    assert settings.nvidia_api_key is None


def test_get_settings_defaults(isolated_env):
    settings = get_settings()

    assert settings.nvidia_base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.runs_dir == Path("runs")
    assert settings.data_dir == Path("data")


def test_get_settings_overrides_from_env(isolated_env, monkeypatch):
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("BISECT_RUNS_DIR", "custom-runs")
    monkeypatch.setenv("BISECT_DATA_DIR", "custom-data")

    settings = get_settings()

    assert settings.nvidia_base_url == "https://example.invalid/v1"
    assert settings.runs_dir == Path("custom-runs")
    assert settings.data_dir == Path("custom-data")


def test_settings_repr_never_contains_key(isolated_env, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)

    settings = get_settings()

    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings)


def test_settings_loads_dotenv_file(isolated_env, monkeypatch):
    env_file = isolated_env / ".env"
    env_file.write_text(f"NVIDIA_API_KEY={FAKE_KEY}\n")
    # The autouse guard in conftest points BISECT_ENV_FILE at a path that does
    # not exist, so a test that wants a dotenv loaded must name its own.
    monkeypatch.setenv("BISECT_ENV_FILE", str(env_file))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.has_nvidia_key is True
    assert settings.nvidia_api_key is not None
    # Never assert on the value directly: a mismatch would print whatever was
    # actually loaded, and that could be the developer's real key.
    assert settings.nvidia_api_key.get_secret_value() == FAKE_KEY, "loaded a different .env"


def test_an_isolated_working_directory_never_picks_up_an_outside_dotenv(isolated_env):
    """Regression: bare load_dotenv() resolved .env relative to core/config.py, so it
    found the repo's real key however the test chdir'd. usecwd=True fixes that."""
    outside = isolated_env.parent / "outside"
    outside.mkdir(exist_ok=True)
    (outside / ".env").write_text(f"NVIDIA_API_KEY={FAKE_KEY}\n")

    settings = get_settings()

    assert settings.has_nvidia_key is False


def test_redact_masks_key_in_text():
    text = f"request failed, key was {FAKE_KEY} in the header"

    redacted = redact(text)

    assert FAKE_KEY not in redacted
    assert "nvapi-***REDACTED***" in redacted


def test_redact_masks_multiple_occurrences():
    text = f"{FAKE_KEY} and also {FAKE_KEY}"

    redacted = redact(text)

    assert FAKE_KEY not in redacted
    assert redacted.count("nvapi-***REDACTED***") == 2


def test_redact_leaves_text_without_key_untouched():
    text = "no secrets here"

    assert redact(text) == text


def test_redact_handles_empty_string():
    assert redact("") == ""
