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
from urllib.parse import urlparse

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

#: The ONLY host the NVIDIA key may ever be sent to.
NVIDIA_ALLOWED_HOST = "integrate.api.nvidia.com"
DEFAULT_NVIDIA_BASE_URL = f"https://{NVIDIA_ALLOWED_HOST}/v1"
#: Offline development against a local server (e.g. mlx_lm.server). Kept as a
#: separate setting precisely so it can never be handed the NVIDIA key; see
#: docs/decisions/0001-preregistration.md ("local MLX models: development and
#: tests only, never for reported numbers").
DEFAULT_LOCAL_API_KEY = "local-dev-unused"
#: An explicit dotenv path. Wins over discovery; a path that does not exist
#: loads nothing. The test suite sets this so it cannot reach a real .env.
ENV_FILE_VAR = "BISECT_ENV_FILE"
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
    local_base_url: str | None = None
    local_api_key: SecretStr = SecretStr(DEFAULT_LOCAL_API_KEY)
    runs_dir: Path = Path(DEFAULT_RUNS_DIR)
    data_dir: Path = Path(DEFAULT_DATA_DIR)

    @property
    def has_nvidia_key(self) -> bool:
        """Boolean-only presence check — never exposes the key value."""
        return self.nvidia_api_key is not None

    @model_validator(mode="after")
    def _key_only_goes_to_the_nvidia_host(self) -> Settings:
        """Refuse to hold the NVIDIA key alongside a base URL that is not NVIDIA's.

        `nvidia_base_url` comes straight from the environment. If it were
        pointed anywhere else — a typo, a stale export, a hostile value —
        every request would carry `Authorization: Bearer <key>` to that
        host. Failing at construction means the key is never paired with an
        endpoint that should not see it, and the error text never contains
        the key itself.
        """
        if self.nvidia_api_key is None:
            return self
        parsed = urlparse(self.nvidia_base_url)
        if parsed.scheme != "https" or parsed.hostname != NVIDIA_ALLOWED_HOST:
            raise ValueError(
                f"NVIDIA_API_KEY is set but NVIDIA_BASE_URL is {self.nvidia_base_url!r}; "
                f"the key may only be sent to https://{NVIDIA_ALLOWED_HOST}. "
                f"For a local endpoint use BISECT_LOCAL_BASE_URL and unset NVIDIA_API_KEY."
            )
        return self


def _settings_from_env() -> Settings:
    raw_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    return Settings(
        nvidia_api_key=SecretStr(raw_key) if raw_key else None,
        nvidia_base_url=os.environ.get("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL),
        local_base_url=os.environ.get("BISECT_LOCAL_BASE_URL") or None,
        local_api_key=SecretStr(
            os.environ.get("BISECT_LOCAL_API_KEY", DEFAULT_LOCAL_API_KEY)
        ),
        runs_dir=Path(os.environ.get("BISECT_RUNS_DIR", DEFAULT_RUNS_DIR)),
        data_dir=Path(os.environ.get("BISECT_DATA_DIR", DEFAULT_DATA_DIR)),
    )


def _dotenv_path() -> str:
    """`$BISECT_ENV_FILE` if set (even when absent), else discovery from the cwd."""
    explicit = os.environ.get(ENV_FILE_VAR)
    if explicit is not None:
        return explicit
    return find_dotenv(usecwd=True)


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
    load_dotenv(dotenv_path=_dotenv_path(), override=False)
    return _settings_from_env()
