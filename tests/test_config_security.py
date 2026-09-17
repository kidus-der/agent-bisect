"""The NVIDIA key may only ever be attached to the NVIDIA host, and tests may never load it.

Two separate properties:

1. A Bearer credential must not follow a redirected `NVIDIA_BASE_URL`. If
   the key is present, the base URL has to be https and the allow-listed
   NVIDIA host, or `Settings` refuses to construct.
2. The test suite must be structurally unable to read the developer's real
   `.env`, whatever the working directory is.

Nothing here compares a secret with `==` against a real value: pytest
prints both sides of a failing comparison.
"""

from __future__ import annotations

import pytest
from agent_bisect.core.config import (
    NVIDIA_ALLOWED_HOST,
    Settings,
    get_settings,
)
from pydantic import SecretStr, ValidationError

# Built at runtime: a literal nvapi-<20+ chars> in source is (correctly)
# blocked by the repo's pre-commit secret scanner, synthetic or not.
SYNTHETIC_KEY = SecretStr("nvapi" + "-" + "B" * 40)
NVIDIA_URL = f"https://{NVIDIA_ALLOWED_HOST}/v1"


# ---- the host allow-list ----


def test_the_key_is_accepted_for_the_nvidia_host():
    settings = Settings(nvidia_api_key=SYNTHETIC_KEY, nvidia_base_url=NVIDIA_URL)

    assert settings.has_nvidia_key is True


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com/v1",
        "https://integrate.api.nvidia.com.evil.example/v1",
        "http://integrate.api.nvidia.com/v1",  # plaintext: the key would go over the wire
        "https://127.0.0.1:8080/v1",
        "http://localhost:8080/v1",
    ],
)
def test_the_key_is_refused_for_any_other_base_url(url):
    with pytest.raises(ValidationError) as excinfo:
        Settings(nvidia_api_key=SYNTHETIC_KEY, nvidia_base_url=url)

    assert NVIDIA_ALLOWED_HOST in str(excinfo.value)


def test_the_refusal_never_echoes_the_key():
    with pytest.raises(ValidationError) as excinfo:
        Settings(nvidia_api_key=SYNTHETIC_KEY, nvidia_base_url="https://evil.example.com/v1")

    assert "nvapi" not in str(excinfo.value)


def test_a_local_base_url_is_fine_when_no_nvidia_key_is_set():
    """Offline MLX development: no credential, so nothing can leak."""
    settings = Settings(nvidia_api_key=None, nvidia_base_url="http://127.0.0.1:8080/v1")

    assert settings.has_nvidia_key is False


def test_the_local_endpoint_is_a_separate_setting_that_never_holds_the_nvidia_key():
    settings = Settings(
        nvidia_api_key=SYNTHETIC_KEY,
        nvidia_base_url=NVIDIA_URL,
        local_base_url="http://127.0.0.1:8080/v1",
    )

    assert settings.local_base_url == "http://127.0.0.1:8080/v1"
    assert settings.local_api_key.get_secret_value() != SYNTHETIC_KEY.get_secret_value()


def test_the_local_api_key_is_not_an_nvidia_key():
    assert "nvapi" not in Settings(nvidia_api_key=None).local_api_key.get_secret_value()


# ---- test isolation from the real .env ----


def test_the_suite_cannot_load_the_real_key_even_from_the_repo_root():
    """The autouse guard in conftest applies here; cwd is the repo root."""
    assert get_settings().has_nvidia_key is False


def test_an_explicit_env_file_is_used_when_it_exists(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text(f"NVIDIA_API_KEY={SYNTHETIC_KEY.get_secret_value()}\n")
    monkeypatch.setenv("BISECT_ENV_FILE", str(env_file))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.has_nvidia_key is True
    assert settings.nvidia_api_key is not None
    # Compare lengths, not values: a failing `==` would print the secret.
    assert len(settings.nvidia_api_key.get_secret_value()) == len(
        SYNTHETIC_KEY.get_secret_value()
    )


def test_a_nonexistent_explicit_env_file_loads_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("BISECT_ENV_FILE", str(tmp_path / "absent.env"))
    get_settings.cache_clear()

    assert get_settings().has_nvidia_key is False


def test_an_explicit_env_file_beats_discovery(tmp_path, monkeypatch):
    """Even standing in a directory with a .env, the explicit path wins."""
    (tmp_path / ".env").write_text("NVIDIA_API_KEY=" + "nvapi" + "-" + "C" * 40 + "\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BISECT_ENV_FILE", str(tmp_path / "absent.env"))
    get_settings.cache_clear()

    assert get_settings().has_nvidia_key is False


def test_pytest_does_not_print_locals_on_failure():
    """--showlocals would dump any frame holding the key on an unrelated failure."""
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    addopts = pyproject["tool"]["pytest"]["ini_options"]["addopts"]

    assert "--showlocals" not in addopts
    assert "-l" not in addopts.split()
