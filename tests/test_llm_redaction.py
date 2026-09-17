"""A provider exception must not carry the key out through the chained cause.

`raise TransportError(redact(...)) from exc` redacts the *message* but keeps
the original, unredacted exception reachable as `__cause__`/`__context__`, so
any traceback print or `logging.exception` puts the key back on screen. These
tests pin the whole surface: the message, the repr, the chain, and the
formatted traceback.
"""

from __future__ import annotations

import logging
import traceback

import pytest
from agent_bisect.adapters.tau2_llm import RetryConfig, Tau2Router
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.llm import (
    LiteLLMTransport,
    LLMRequest,
    TransportError,
    transport_error_from,
)

# Built at runtime: a literal nvapi-<20+ chars> in source is (correctly)
# blocked by the repo's pre-commit secret scanner, synthetic or not.
SYNTHETIC_KEY = "nvapi" + "-" + "A" * 64
API_BASE = "https://integrate.api.nvidia.com/v1"


def _leaky() -> Exception:
    return RuntimeError(
        f"POST /chat/completions failed, Authorization: Bearer {SYNTHETIC_KEY}"
    )


def _everything_about(exc: BaseException) -> str:
    """Every rendering a developer or a log handler could produce."""
    return "\n".join(
        [
            str(exc),
            repr(exc),
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            repr(exc.__cause__),
            repr(exc.__context__),
        ]
    )


# ---- the helper ----


def test_helper_redacts_the_message():
    error = transport_error_from(_leaky())

    assert SYNTHETIC_KEY not in str(error)
    assert "REDACTED" in str(error)


def test_helper_keeps_the_original_type_so_the_error_stays_diagnosable():
    error = transport_error_from(_leaky())

    assert "RuntimeError" in str(error)


def test_helper_drops_the_unredacted_cause_and_context():
    try:
        raise _leaky()
    except RuntimeError as exc:
        error = transport_error_from(exc)

    assert error.__cause__ is None
    assert error.__context__ is None
    assert error.__suppress_context__ is True


def test_helper_carries_status_and_retry_after_through():
    error = transport_error_from(_leaky(), status_code=429, retry_after=3.0)

    assert (error.status_code, error.retry_after) == (429, 3.0)


# ---- the production transport ----


async def test_transport_never_leaks_the_key_through_a_raised_exception(monkeypatch):
    import litellm

    async def explode(**_kwargs):
        raise _leaky()

    monkeypatch.setattr(litellm, "acompletion", explode)

    with pytest.raises(TransportError) as excinfo:
        await LiteLLMTransport().complete(
            LLMRequest(model="m", messages=({"role": "user", "content": "x"},)),
            api_base=API_BASE,
            api_key=SYNTHETIC_KEY,
        )

    assert SYNTHETIC_KEY not in _everything_about(excinfo.value)


async def test_transport_error_survives_logging_exception_without_leaking(
    monkeypatch, caplog
):
    import litellm

    async def explode(**_kwargs):
        raise _leaky()

    monkeypatch.setattr(litellm, "acompletion", explode)

    with caplog.at_level(logging.DEBUG):
        try:
            await LiteLLMTransport().complete(
                LLMRequest(model="m", messages=({"role": "user", "content": "x"},)),
                api_base=API_BASE,
                api_key=SYNTHETIC_KEY,
            )
        except TransportError:
            logging.getLogger(__name__).exception("call failed")

    assert SYNTHETIC_KEY not in caplog.text


# ---- the tau2 bridge ----


def test_router_never_leaks_the_key_when_it_gives_up(tmp_path):
    def explode(**_kwargs):
        raise _leaky()

    router = Tau2Router(
        api_base=API_BASE,
        api_key=SYNTHETIC_KEY,
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        limiter_for=lambda _m: type("L", (), {"acquire_sync": lambda self: None})(),
        completion_fn=explode,
        phase="P0",
        config=RetryConfig(max_elapsed_s=0.0),
        sleep=lambda _s: None,
    )

    with pytest.raises(TransportError) as excinfo:
        router.completion(model="m", messages=[])

    assert SYNTHETIC_KEY not in _everything_about(excinfo.value)


def test_router_retry_path_does_not_relink_the_original_exception(tmp_path):
    """The re-raise happens inside an `except`, which would re-chain it."""
    calls = {"n": 0}

    def explode(**_kwargs):
        calls["n"] += 1
        raise _leaky()

    router = Tau2Router(
        api_base=API_BASE,
        api_key=SYNTHETIC_KEY,
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        limiter_for=lambda _m: type("L", (), {"acquire_sync": lambda self: None})(),
        completion_fn=explode,
        phase="P0",
        config=RetryConfig(max_elapsed_s=0.0),
        sleep=lambda _s: None,
    )

    with pytest.raises(TransportError) as excinfo:
        router.completion(model="m", messages=[])

    assert excinfo.value.__cause__ is None
    assert SYNTHETIC_KEY not in _everything_about(excinfo.value)
