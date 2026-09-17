"""Tests for LLMClient: retry/backoff, Retry-After, record-before-use ordering, ledger writes.

Uses a `ScriptedTransport` fake (never real network) driven by a fake
clock/sleeper, so retry delays are asserted exactly instead of waited on.
"""

from __future__ import annotations

import asyncio

import pytest
from agent_bisect.core.budget import BudgetExceededError, BudgetLedger
from agent_bisect.core.llm import (
    LLMClient,
    LLMClientConfig,
    LLMRequest,
    LLMResponse,
    TokenBucketLimiter,
    TransportError,
    compute_backoff_s,
)


@pytest.fixture(autouse=True)
def _clear_phase_env(monkeypatch):
    monkeypatch.delenv("BISECT_PHASE", raising=False)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingSleeper:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


class ScriptedTransport:
    """Replays a scripted sequence of outcomes: exceptions to raise, or a final response."""

    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def complete(self, request, *, api_base, api_key):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _request(
    *,
    model: str = "m",
    messages: tuple[dict[str, str], ...] = ({"role": "user", "content": "hi"},),
    purpose: str = "test",
) -> LLMRequest:
    return LLMRequest(model=model, messages=messages, purpose=purpose)


def _response(
    *, content: str = "ok", tokens_in: int = 1, tokens_out: int = 1
) -> LLMResponse:
    return LLMResponse(content=content, tokens_in=tokens_in, tokens_out=tokens_out)


def _client(transport, ledger, *, clock=None, sleeper=None, rand=None, config=None):
    clock = clock or FakeClock()
    sleeper = sleeper or RecordingSleeper(clock)
    limiter = TokenBucketLimiter(6000, clock=clock, sleep=sleeper)
    client = LLMClient(
        transport,
        ledger,
        api_base="https://example.invalid/v1",
        api_key="nvapi-test",
        config=config,
        limiter=limiter,
        clock=clock,
        sleep=sleeper,
        rand=rand or (lambda: 0.5),
    )
    return client, sleeper, clock


@pytest.mark.asyncio
async def test_successful_call_records_ok_in_ledger(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport([_response(tokens_in=3, tokens_out=4)])
    client, _, _ = _client(transport, ledger)

    response = await client.complete(_request(), phase="P0")

    assert response.tokens_in == 3
    assert ledger.total_calls() == 1
    assert ledger.totals_per_phase() == {"P0": 1}


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport(
        [TransportError("rate limited", status_code=429), _response()]
    )
    client, sleeper, _ = _client(transport, ledger)

    response = await client.complete(_request())

    assert transport.calls == 2
    assert response.content == "ok"
    assert ledger.total_calls() == 2  # one failed attempt + one success


@pytest.mark.asyncio
async def test_retry_after_header_overrides_computed_backoff(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport(
        [TransportError("rate limited", status_code=429, retry_after=7.5), _response()]
    )
    client, sleeper, _ = _client(transport, ledger, rand=lambda: 1.0)

    await client.complete(_request())

    assert sleeper.calls == [7.5]


@pytest.mark.asyncio
async def test_backoff_used_when_no_retry_after(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport(
        [TransportError("server error", status_code=503), _response()]
    )
    client, sleeper, _ = _client(transport, ledger, rand=lambda: 0.5)

    await client.complete(_request())

    # attempt=0: ceiling = min(30, 1 * 2**0) = 1.0; rand()=0.5 -> 0.5s
    assert sleeper.calls == [pytest.approx(0.5)]


@pytest.mark.asyncio
async def test_timeout_without_status_code_is_retried(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport([TransportError("timed out", status_code=None), _response()])
    client, sleeper, _ = _client(transport, ledger)

    response = await client.complete(_request())

    assert response.content == "ok"


@pytest.mark.asyncio
async def test_non_retryable_status_raises_immediately(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport([TransportError("bad request", status_code=400)])
    client, sleeper, _ = _client(transport, ledger)

    with pytest.raises(TransportError):
        await client.complete(_request(), phase="P7")

    assert transport.calls == 1
    assert sleeper.calls == []
    assert ledger.totals_per_phase()["P7"] == 1


@pytest.mark.asyncio
async def test_gives_up_after_max_elapsed_s(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    outcomes = [
        TransportError("rate limited", status_code=429, retry_after=100.0) for _ in range(5)
    ]
    transport = ScriptedTransport(outcomes)
    config = LLMClientConfig(max_elapsed_s=50.0)
    client, sleeper, clock = _client(transport, ledger, config=config)

    with pytest.raises(TransportError):
        await client.complete(_request())

    assert transport.calls <= len(outcomes)


@pytest.mark.asyncio
async def test_budget_exceeded_blocks_call_before_transport_is_invoked(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite", max_calls=0)
    transport = ScriptedTransport([_response()])
    client, _, _ = _client(transport, ledger)

    with pytest.raises(BudgetExceededError):
        await client.complete(_request())

    assert transport.calls == 0


@pytest.mark.asyncio
async def test_record_before_use_completes_before_response_returned(tmp_path):
    ledger = BudgetLedger(tmp_path / "l.sqlite")
    transport = ScriptedTransport([_response()])
    order: list[str] = []

    async def record_before_use(request, response):
        await asyncio.sleep(0)
        order.append("recorded")

    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    limiter = TokenBucketLimiter(6000, clock=clock, sleep=sleeper)
    client = LLMClient(
        transport,
        ledger,
        api_base="https://example.invalid/v1",
        api_key="nvapi-test",
        limiter=limiter,
        record_before_use=record_before_use,
        clock=clock,
        sleep=sleeper,
    )

    await client.complete(_request())
    order.append("returned")

    assert order == ["recorded", "returned"]


def test_compute_backoff_s_is_bounded_by_ceiling():
    for attempt in range(6):
        for rand_value in (0.0, 0.5, 0.999):
            delay = compute_backoff_s(
                attempt, base_delay_s=1.0, max_delay_s=30.0, rand=lambda v=rand_value: v
            )
            ceiling = min(30.0, 1.0 * 2**attempt)
            assert 0.0 <= delay <= ceiling


def test_compute_backoff_s_respects_max_delay_ceiling():
    delay = compute_backoff_s(20, base_delay_s=1.0, max_delay_s=30.0, rand=lambda: 1.0)

    assert delay == pytest.approx(30.0)
