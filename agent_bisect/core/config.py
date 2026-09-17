"""Configuration loading: environment variables, secrets, and paths.

Loads `.env` via python-dotenv and exposes a frozen `Settings` model. The
NVIDIA API key is stored as a pydantic `SecretStr`, which never appears in
cleartext in `repr()`/`str()`. Any free text that might contain the key
(log lines, exception messages built from request/response bodies) MUST be
passed through `redact()` before it leaves `core.llm`.

Never `cat .env`, never echo the key, never let a command's output contain
it. To check presence, test `settings.nvidia_api_key is not None` — a
boolean, never the value itself.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_RUNS_DIR = "runs"
DEFAULT_DATA_DIR = "data"

# Matches NVIDIA NIM API keys: `nvapi-` followed by URL-safe key material.
_NVIDIA_KEY_PATTERN = re.compile(r"nvapi-[A-Za-z0-9_\-]+")
_REDACTED = "nvapi-***REDACTED***"


def redact(text: str) -> str:
    """Mask any NVIDIA API key material found in free text.

    Use on every string that reaches a log line or an exception message in
    `core.llm` (request repr, response body, error text) — the text may
    originate from the NVIDIA API and could echo the key back.
    """
    return _NVIDIA_KEY_PATTERN.sub(_REDACTED, text)


class Settings(BaseModel):
    """Process-wide configuration. Frozen: construct a new instance to change a value."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    nvidia_api_key: SecretStr | None
    nvidia_base_url: str = DEFAULT_NVIDIA_BASE_URL
    runs_dir: Path = Path(DEFAULT_RUNS_DIR)
    data_dir: Path = Path(DEFAULT_DATA_DIR)

    @property
    def has_nvidia_key(self) -> bool:
        """Boolean-only presence check — never exposes the key value."""
        return self.nvidia_api_key is not None


def _settings_from_env() -> Settings:
    raw_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    return Settings(
        nvidia_api_key=SecretStr(raw_key) if raw_key else None,
        nvidia_base_url=os.environ.get("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL),
        runs_dir=Path(os.environ.get("BISECT_RUNS_DIR", DEFAULT_RUNS_DIR)),
        data_dir=Path(os.environ.get("BISECT_DATA_DIR", DEFAULT_DATA_DIR)),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load `.env` (if present) and return the cached process-wide settings.

    `usecwd=True` is load-bearing. Bare `load_dotenv()` resolves the file
    relative to the *calling module's* directory, so it walks up from
    `agent_bisect/core/` and finds the repo's own `.env` no matter what the
    working directory is. That made it impossible for a test to isolate
    itself from the real key — a test pointed at an empty temp directory
    still loaded the live key and could print it in an assertion diff.
    Resolving from the working directory means `chdir` isolates properly,
    and it is also the behaviour a CLI should have: the `.env` belongs to
    the project you are standing in.

    Call `get_settings.cache_clear()` in tests that mutate the environment.
    """
    load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=False)
    return _settings_from_env()
