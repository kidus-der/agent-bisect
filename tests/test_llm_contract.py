"""Three contracts of the LLM client: recording, Retry-After, and rejected credentials."""

from __future__ import annotations

import pytest
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.llm import (
    AUTH_STATUS_CODES,
    MAX_RETRY_AFTER_S,
    AuthenticationError,
    LLMClient,
    LLMClientConfig,
    LLMRequest,
    LLMResponse,
    RecordingError,
    TransportError,
    parse_retry_after,
)

REQUEST = LLMRequest(model="m", messages=({"role": "user", "content": "x"},), purpose="agent")


class FakeTransport:
    def __init__(self, errors: list[BaseException] | None = None) -> None:
        self.calls = 0
        self.errors = list(errors or [])

    async def complete(self, request, *, api_base, api_key) -> LLMResponse:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return LLMResponse(content="hi", tokens_in=7, tokens_out=3)


def _client(tmp_path, transport, *, record_before_use=None, sleeps=None, **kwargs):
    return LLMClient(
        transport,
        BudgetLedger(tmp_path / "ledger.sqlite"),
        api_base="https://integrate.api.nvidia.com/v1",
        api_key="unused-in-tests",
        record_before_use=record_before_use,
        sleep=(sleeps.append if sleeps is not None else _noop_sleep),
        config=LLMClientConfig(requests_per_minute=6000, **kwargs),
    )


async def _noop_sleep(_seconds: float) -> None:
    return None


# ---- record-before-use ----


async def test_a_paid_call_is_ledgered_even_when_the_recording_hook_fails(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")

    async def explode(_request, _response):
        raise OSError("disk full")

    client = LLMClient(
        FakeTransport(),
        ledger,
        api_base="https://integrate.api.nvidia.com/v1",
        api_key="unused-in-tests",
        record_before_use=explode,
        config=LLMClientConfig(requests_per_minute=6000),
    )

    with pytest.raises(RecordingError):
        await client.complete(REQUEST, phase="P0")

    assert ledger.total_calls() == 1
    assert ledger.totals_per_model() == {"m": 1}


async def test_a_response_that_could_not_be_recorded_is_not_returned(tmp_path):
    async def explode(_request, _response):
        raise OSError("disk full")

    client = _client(tmp_path, FakeTransport(), record_before_use=explode)

    with pytest.raises(RecordingError, match="OSError"):
        await client.complete(REQUEST, phase="P0")


async def test_the_recording_failure_is_redacted(tmp_path):
    synthetic = "nvapi" + "-" + "D" * 40

    async def explode(_request, _response):
        raise OSError(f"failed while writing {synthetic}")

    client = _client(tmp_path, FakeTransport(), record_before_use=explode)

    with pytest.raises(RecordingError) as excinfo:
        await client.complete(REQUEST, phase="P0")

    assert synthetic not in str(excinfo.value)


async def test_a_successful_hook_still_returns_the_response(tmp_path):
    seen = []

    async def hook(request, response):
        seen.append((request, response))

    client = _client(tmp_path, FakeTransport(), record_before_use=hook)

    response = await client.complete(REQUEST, phase="P0")

    assert response.content == "hi"
    assert len(seen) == 1


# ---- Retry-After ----


def test_retry_after_parses_plain_seconds():
    assert parse_retry_after("12") == pytest.approx(12.0)


def test_retry_after_parses_an_http_date():
    """RFC 9110 allows an HTTP-date, and NIM may send one."""
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    when = datetime.now(UTC) + timedelta(seconds=30)

    parsed = parse_retry_after(format_datetime(when))

    assert parsed is not None
    assert 20 <= parsed <= 40


def test_an_http_date_in_the_past_means_retry_now():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    when = datetime.now(UTC) - timedelta(seconds=60)

    assert parse_retry_after(format_datetime(when)) == 0.0


def test_retry_after_is_clamped_so_one_bad_header_cannot_stall_a_run():
    assert parse_retry_after(str(MAX_RETRY_AFTER_S * 100)) == MAX_RETRY_AFTER_S


def test_unparseable_retry_after_is_ignored():
    assert parse_retry_after("soon please") is None


def test_a_negative_retry_after_is_treated_as_now():
    assert parse_retry_after("-5") == 0.0


# ---- rejected credentials ----


@pytest.mark.parametrize("status", sorted(AUTH_STATUS_CODES))
async def test_rejected_credentials_stop_immediately_instead_of_retrying(tmp_path, status):
    transport = FakeTransport(
        errors=[TransportError("nope", status_code=status) for _ in range(5)]
    )
    client = _client(tmp_path, transport)

    with pytest.raises(AuthenticationError):
        await client.complete(REQUEST, phase="P0")

    assert transport.calls == 1


async def test_the_credential_error_says_what_to_do_about_it(tmp_path):
    transport = FakeTransport(errors=[TransportError("nope", status_code=401)])
    client = _client(tmp_path, transport)

    with pytest.raises(AuthenticationError) as excinfo:
        await client.complete(REQUEST, phase="P0")

    message = str(excinfo.value).lower()
    assert "nvidia_api_key" in message
    assert "re-run" in message or "resume" in message


async def test_a_credential_error_is_still_a_transport_error_for_existing_handlers(tmp_path):
    transport = FakeTransport(errors=[TransportError("nope", status_code=403)])
    client = _client(tmp_path, transport)

    with pytest.raises(TransportError):
        await client.complete(REQUEST, phase="P0")
