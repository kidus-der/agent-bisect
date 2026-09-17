"""Tests for the process-wide limiter registry and its TOML configuration."""

from __future__ import annotations

import threading

import pytest
from agent_bisect.core.limits import (
    DEFAULT_MAX_CONCURRENCY,
    LimiterSettings,
    get_shared_limiter,
    limiter_rpm_for,
    load_limiter_settings,
    reset_shared_limiters,
)
from agent_bisect.core.llm import TokenBucketLimiter


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_limiters()
    yield
    reset_shared_limiters()


def _write(tmp_path, body: str):
    path = tmp_path / "limits.toml"
    path.write_text(body)
    return path


def test_loads_requests_per_minute_from_toml(tmp_path):
    path = _write(tmp_path, "[limiter]\nrequests_per_minute = 144\n")

    settings = load_limiter_settings(path)

    assert settings.requests_per_minute == 144


def test_defaults_to_account_scope_when_unspecified(tmp_path):
    path = _write(tmp_path, "[limiter]\nrequests_per_minute = 30\n")

    assert load_limiter_settings(path).scope == "account"


def test_reads_per_model_overrides(tmp_path):
    path = _write(
        tmp_path,
        "[limiter]\nrequests_per_minute = 100\nscope = 'model'\n"
        "[limiter.per_model]\n'z-ai/glm-5.3-flash' = 40\n",
    )

    settings = load_limiter_settings(path)

    assert settings.scope == "model"
    assert settings.per_model == {"z-ai/glm-5.3-flash": 40.0}


def test_missing_file_falls_back_to_the_conservative_default(tmp_path):
    settings = load_limiter_settings(tmp_path / "absent.toml")

    assert settings.requests_per_minute > 0
    assert settings.max_concurrency == DEFAULT_MAX_CONCURRENCY


def test_rejects_a_non_positive_rate(tmp_path):
    path = _write(tmp_path, "[limiter]\nrequests_per_minute = 0\n")

    with pytest.raises(ValueError, match="requests_per_minute"):
        load_limiter_settings(path)


def test_rejects_an_unknown_scope(tmp_path):
    path = _write(tmp_path, "[limiter]\nrequests_per_minute = 10\nscope = 'galaxy'\n")

    with pytest.raises(ValueError, match="scope"):
        load_limiter_settings(path)


def test_account_scope_shares_one_bucket_across_models():
    settings = LimiterSettings(requests_per_minute=60, scope="account")

    first = get_shared_limiter("model-a", settings=settings)
    second = get_shared_limiter("model-b", settings=settings)

    assert first is second


def test_model_scope_gives_each_model_its_own_bucket():
    settings = LimiterSettings(requests_per_minute=60, scope="model")

    first = get_shared_limiter("model-a", settings=settings)
    second = get_shared_limiter("model-b", settings=settings)

    assert first is not second
    assert get_shared_limiter("model-a", settings=settings) is first


def test_limiter_rpm_for_prefers_the_per_model_override():
    settings = LimiterSettings(
        requests_per_minute=100, scope="model", per_model={"slow": 25.0}
    )

    assert limiter_rpm_for("slow", settings) == 25.0
    assert limiter_rpm_for("other", settings) == 100.0


def test_shared_limiter_is_one_object_across_threads():
    settings = LimiterSettings(requests_per_minute=600, scope="account")
    seen: list[TokenBucketLimiter] = []
    barrier = threading.Barrier(8)

    def grab():
        barrier.wait()
        seen.append(get_shared_limiter("any", settings=settings))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(seen) == 8
    assert all(limiter is seen[0] for limiter in seen)


def test_sync_acquire_paces_calls_from_many_threads():
    """One bucket must pace threads, not each thread separately."""
    clock_lock = threading.Lock()
    now = [0.0]
    slept: list[float] = []

    def clock() -> float:
        with clock_lock:
            return now[0]

    def sleep(seconds: float) -> None:
        with clock_lock:
            slept.append(seconds)
            now[0] += seconds

    # capacity 4/min: 4 immediate grants, then every further call must wait.
    limiter = TokenBucketLimiter(4, clock=clock, sleep_sync=sleep)
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        limiter.acquire_sync()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 8 calls through a 4-token bucket: at least the last 4 had to wait.
    assert len(slept) >= 4
    assert all(seconds > 0 for seconds in slept)
