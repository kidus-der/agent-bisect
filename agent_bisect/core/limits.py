"""Process-wide rate limiting: load `config/limits.toml`, hand out the shared bucket(s).

There is exactly one limiter registry per process. τ²-bench runs its tasks
in a thread pool and our own scripts run coroutines; both must pull tokens
from the *same* bucket, or the provider sees the sum of several independent
limiters and returns 429s.

`scope` says what the measured ceiling applies to (P0b measures which):

- `"account"` (default) — one bucket covers every model together. Every
  `get_shared_limiter(model)` call returns the same object whatever the
  model is.
- `"model"` — one bucket per model, each at that model's own rate
  (`[limiter.per_model]`, falling back to `requests_per_minute`).

The rate written to the file is always the *measured* ceiling minus the 10%
safety margin from `docs/decisions/0001-preregistration.md`; this module
applies no further margin of its own.
"""

from __future__ import annotations

import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from agent_bisect.core.llm import DEFAULT_REQUESTS_PER_MINUTE, TokenBucketLimiter

DEFAULT_LIMITS_PATH = Path("config/limits.toml")
DEFAULT_MAX_CONCURRENCY = 4
VALID_SCOPES = ("account", "model")
ACCOUNT_BUCKET_KEY = "__account__"


@dataclass(frozen=True)
class LimiterSettings:
    """Immutable limiter configuration. Build a new instance to change a value."""

    requests_per_minute: float = DEFAULT_REQUESTS_PER_MINUTE
    scope: str = "account"
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    per_model: dict[str, float] = field(default_factory=dict)


def _validate(settings: LimiterSettings, source: str) -> LimiterSettings:
    if settings.requests_per_minute <= 0:
        raise ValueError(f"{source}: requests_per_minute must be positive")
    if settings.scope not in VALID_SCOPES:
        raise ValueError(f"{source}: scope must be one of {VALID_SCOPES}, got {settings.scope!r}")
    if settings.max_concurrency <= 0:
        raise ValueError(f"{source}: max_concurrency must be positive")
    for model, rate in settings.per_model.items():
        if rate <= 0:
            raise ValueError(f"{source}: per_model[{model!r}] must be positive")
    return settings


def load_limiter_settings(path: Path = DEFAULT_LIMITS_PATH) -> LimiterSettings:
    """Read `config/limits.toml`. A missing file yields the conservative default."""
    if not path.exists():
        return LimiterSettings()
    with path.open("rb") as handle:
        table = tomllib.load(handle).get("limiter", {})
    per_model = {str(k): float(v) for k, v in (table.get("per_model") or {}).items()}
    return _validate(
        LimiterSettings(
            requests_per_minute=float(
                table.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
            ),
            scope=str(table.get("scope", "account")),
            max_concurrency=int(table.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
            per_model=per_model,
        ),
        str(path),
    )


def limiter_rpm_for(model: str, settings: LimiterSettings) -> float:
    """The rate this model's bucket runs at: its override, else the global rate."""
    return settings.per_model.get(model, settings.requests_per_minute)


_registry_lock = threading.Lock()
_limiters: dict[str, TokenBucketLimiter] = {}
_settings: LimiterSettings | None = None


def get_limiter_settings(path: Path = DEFAULT_LIMITS_PATH) -> LimiterSettings:
    """The process-wide settings, loaded once from `path`."""
    global _settings
    with _registry_lock:
        if _settings is None:
            _settings = load_limiter_settings(path)
        return _settings


def get_shared_limiter(
    model: str, *, settings: LimiterSettings | None = None
) -> TokenBucketLimiter:
    """The bucket this model's calls must pass through. One object per bucket, per process."""
    resolved = settings if settings is not None else get_limiter_settings()
    key = ACCOUNT_BUCKET_KEY if resolved.scope == "account" else model
    with _registry_lock:
        limiter = _limiters.get(key)
        if limiter is None:
            rate = (
                resolved.requests_per_minute
                if resolved.scope == "account"
                else limiter_rpm_for(model, resolved)
            )
            limiter = TokenBucketLimiter(rate)
            _limiters[key] = limiter
        return limiter


def reset_shared_limiters() -> None:
    """Drop the cached settings and buckets. Tests only — never call this in a run."""
    global _settings
    with _registry_lock:
        _limiters.clear()
        _settings = None
