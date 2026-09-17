"""Async LiteLLM wrapper for calling NVIDIA NIM.

Provider prefix: NIM models are called through litellm's generic
OpenAI-compatible route — `openai/<model>` with `api_base` set to NVIDIA's
endpoint — rather than litellm's dedicated `nvidia_nim/` provider. NIM is
OpenAI-protocol-compatible, and the generic route avoids provider-specific
parameter handling that isn't needed here. `LiteLLMTransport.complete`
constructs the `openai/<model>` string; the bare model id used everywhere
else (`LLMRequest.model`, the ledger, `config/models.toml`) has no prefix.

Rate limiting: `TokenBucketLimiter` is a single process-wide async
token-bucket limiter, configurable in requests/min via `config/limits.toml`
(default 30, until P0b measures the real per-model ceiling).

Retries: exponential backoff with full jitter on HTTP 429/5xx and on
timeouts/connection errors. A `Retry-After` response header always takes
precedence over the computed backoff delay. Retries continue until
`max_elapsed_s` since the first attempt is exhausted — a call is only
failed after that budget runs out, never on the first error.

Every call is registered in the budget ledger (`core.budget`): the ledger
is checked *before* each attempt (so a call that would exceed the cap
never reaches the network) and a row is written after every attempt,
success or failure. A `record_before_use` callback, when supplied, is
awaited with `(request, response)` and MUST complete before `complete()`
returns the response to its caller — this lets a caller durably archive
raw traffic before any downstream code can act on it.

The HTTP/LLM transport is dependency-injected via the `Transport`
protocol, so `LLMClient` is tested entirely against fakes — no real
network call happens in the test suite (`--disable-socket` enforces this).
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from agent_bisect.core.budget import BudgetLedger, current_phase
from agent_bisect.core.config import redact

DEFAULT_REQUESTS_PER_MINUTE = 30.0
DEFAULT_MAX_ELAPSED_S = 300.0
DEFAULT_BASE_DELAY_S = 1.0
DEFAULT_MAX_DELAY_S = 30.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
#: Credentials rejected. Never retried: the key will not become valid by
#: waiting, and retrying just burns the elapsed budget on every call.
AUTH_STATUS_CODES = frozenset({401, 403})
#: A Retry-After far in the future would otherwise stall a whole run.
MAX_RETRY_AFTER_S = 120.0


class LLMRequest(BaseModel):
    """One chat-completion request. Immutable: build a new instance to change a field."""

    model_config = ConfigDict(frozen=True)

    model: str
    messages: tuple[dict[str, str], ...]
    max_tokens: int | None = None
    tools: tuple[dict, ...] | None = None
    purpose: str = "unspecified"


class LLMResponse(BaseModel):
    """One chat-completion response."""

    model_config = ConfigDict(frozen=True)

    content: str
    tokens_in: int
    tokens_out: int
    raw: dict = Field(default_factory=dict)


class RecordingError(RuntimeError):
    """A call was made and ledgered, but `record_before_use` could not archive it.

    Raised instead of returning the response: record-before-use means a
    caller must never act on traffic that was not durably recorded.
    """


class TransportError(Exception):
    """Raised by a `Transport` on any failure. `message` is redacted before storage."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(redact(message))
        self.status_code = status_code
        self.retry_after = retry_after


AUTH_GUIDANCE = (
    "credentials rejected by the provider (HTTP {status}). NVIDIA_API_KEY is "
    "missing, revoked or has been rotated. Fix the key and re-run: finished "
    "work is checkpointed and will be skipped, so the run resumes where it "
    "stopped."
)


class AuthenticationError(TransportError):
    """The provider rejected the credential (401/403).

    A subclass of `TransportError` so existing handlers still catch it,
    but it is never retried and it carries the operator instructions: a
    long job should stop on the first one rather than spend its whole
    retry budget re-sending a key that will not start working.
    """


def parse_retry_after(value: str | None) -> float | None:
    """RFC 9110 `Retry-After`: delay-seconds **or** an HTTP-date.

    Returns seconds to wait, clamped to `MAX_RETRY_AFTER_S` so one bad
    header cannot stall a run, and floored at 0 for a date already past.
    `None` when the value is absent or unparseable, so the caller falls
    back to its own backoff.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return min(max(0.0, float(text)), MAX_RETRY_AFTER_S)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delay = (when - datetime.now(UTC)).total_seconds()
    return min(max(0.0, delay), MAX_RETRY_AFTER_S)


def terminal_error(exc: TransportError) -> TransportError:
    """The exception to raise when giving up, upgrading 401/403 on the way.

    A `TransportError` can reach the client from anywhere (a custom
    transport, a fake, a layer that built one by hand), so the auth
    upgrade is applied where the decision to stop is made rather than only
    where the provider exception is first normalised.
    """
    if isinstance(exc, AuthenticationError) or exc.status_code not in AUTH_STATUS_CODES:
        return exc
    error = AuthenticationError(
        f"{AUTH_GUIDANCE.format(status=exc.status_code)} [{exc}]",
        status_code=exc.status_code,
        retry_after=exc.retry_after,
    )
    error.__cause__ = None
    error.__context__ = None
    error.__suppress_context__ = True
    return error


def transport_error_from(
    exc: BaseException,
    *,
    status_code: int | None = None,
    retry_after: float | None = None,
) -> TransportError:
    """Build a `TransportError` that keeps NOTHING of the original reachable.

    `raise TransportError(redact(str(exc))) from exc` only redacts the
    message. The original exception stays reachable as `__cause__`, and a
    provider error commonly quotes the request — headers included — so one
    `logging.exception` or an unhandled traceback puts the key back on
    screen. The chain is severed on both links (`__cause__` and
    `__context__`) and suppressed in tracebacks; the original type and its
    redacted message are folded into the new message so the error stays
    diagnosable. Raise the result with `from None`.
    """
    resolved_status = (
        status_code if status_code is not None else getattr(exc, "status_code", None)
    )
    cls = AuthenticationError if resolved_status in AUTH_STATUS_CODES else TransportError
    message = redact(f"{type(exc).__name__}: {exc}")
    if cls is AuthenticationError:
        message = f"{AUTH_GUIDANCE.format(status=resolved_status)} [{message}]"
    error = cls(
        message,
        status_code=resolved_status,
        retry_after=retry_after if retry_after is not None else _extract_retry_after(exc),
    )
    error.__cause__ = None
    error.__context__ = None
    error.__suppress_context__ = True
    return error


class Transport(Protocol):
    """Dependency-injected transport. Tests supply a fake; production uses `LiteLLMTransport`."""

    async def complete(
        self, request: LLMRequest, *, api_base: str, api_key: str
    ) -> LLMResponse: ...


class LiteLLMTransport:
    """Production `Transport`: calls NIM via `litellm.acompletion` on the `openai/` route."""

    async def complete(
        self, request: LLMRequest, *, api_base: str, api_key: str
    ) -> LLMResponse:
        import litellm
        from litellm.types.utils import ModelResponse

        failure: TransportError | None = None
        raw = None
        try:
            # We never pass stream=True, so litellm always returns a
            # ModelResponse; its signature's Union with CustomStreamWrapper
            # only applies to the streaming path.
            raw = cast(
                ModelResponse,
                await litellm.acompletion(
                    model=f"openai/{request.model}",
                    messages=list(request.messages),
                    max_tokens=request.max_tokens,
                    tools=list(request.tools) if request.tools else None,
                    api_base=api_base,
                    api_key=api_key,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - normalized by transport_error_from
            failure = transport_error_from(exc)
        if failure is not None:
            # Raised OUTSIDE the except block on purpose. `raise ... from None`
            # inside one still sets __context__ to the exception being handled
            # -- it is only hidden from tracebacks, not detached -- and that
            # object holds the unredacted provider text. Out here there is no
            # exception being handled, so __context__ stays None.
            raise failure
        assert raw is not None

        choice = raw.choices[0]
        # `usage` is set dynamically by litellm's ModelResponse.__init__ and
        # isn't a declared pydantic field, so pyright can't see it statically.
        usage = getattr(raw, "usage", None)
        tokens_in = int(usage.prompt_tokens) if usage is not None else 0
        tokens_out = int(usage.completion_tokens) if usage is not None else 0
        return LLMResponse(
            content=choice.message.content or "",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            raw=raw.model_dump(),
        )


def _extract_retry_after(exc: BaseException) -> float | None:
    headers = getattr(exc, "response", None)
    headers = getattr(headers, "headers", None) if headers is not None else None
    if not headers:
        return None
    return parse_retry_after(headers.get("Retry-After") or headers.get("retry-after"))


def compute_backoff_s(
    attempt: int,
    *,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    rand: Callable[[], float] = random.random,
) -> float:
    """Full-jitter exponential backoff: `uniform(0, min(max_delay, base * 2**attempt))`."""
    ceiling = min(max_delay_s, base_delay_s * (2**attempt))
    return rand() * ceiling


class TokenBucketLimiter:
    """Token-bucket rate limiter, usable from coroutines *and* from threads.

    Intended as one process-wide instance shared by every call site (see
    `core.limits.get_shared_limiter`). τ²-bench runs its tasks in a thread
    pool and calls LiteLLM synchronously, while our own code is async — so
    the bucket's state is guarded by a `threading.Lock` rather than an
    `asyncio.Lock`, and the lock is never held across a sleep. `_reserve()`
    is the only critical section: it either grants a token or reports how
    long the caller must wait before trying again.

    `clock`/`sleep`/`sleep_sync` are injected so tests run against a fake
    clock instead of real wall-clock waits.
    """

    def __init__(
        self,
        requests_per_minute: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sleep_sync: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self._capacity = requests_per_minute
        self._tokens = requests_per_minute
        self._refill_per_s = requests_per_minute / 60.0
        self._clock = clock
        self._sleep = sleep
        self._sleep_sync = sleep_sync
        self._last_refill = clock()
        self._lock = threading.Lock()

    @property
    def requests_per_minute(self) -> float:
        return self._capacity

    def _reserve(self) -> float:
        """Take a token and return 0.0, or return the seconds to wait first."""
        with self._lock:
            now = self._clock()
            elapsed = now - self._last_refill
            self._last_refill = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_s)
            if self._tokens >= 1:
                self._tokens -= 1
                return 0.0
            return (1 - self._tokens) / self._refill_per_s

    async def acquire(self) -> None:
        while True:
            wait_s = self._reserve()
            if wait_s <= 0:
                return
            await self._sleep(wait_s)

    def acquire_sync(self) -> None:
        """Blocking `acquire()`, for τ²'s synchronous, threaded call sites."""
        while True:
            wait_s = self._reserve()
            if wait_s <= 0:
                return
            self._sleep_sync(wait_s)


RecordBeforeUse = Callable[[LLMRequest, LLMResponse], Awaitable[None]]


@dataclass(frozen=True)
class LLMClientConfig:
    requests_per_minute: float = DEFAULT_REQUESTS_PER_MINUTE
    max_elapsed_s: float = DEFAULT_MAX_ELAPSED_S
    base_delay_s: float = DEFAULT_BASE_DELAY_S
    max_delay_s: float = DEFAULT_MAX_DELAY_S


class LLMClient:
    """Rate-limited, retrying, budget-tracked NIM client. See module docstring for the contract."""

    def __init__(
        self,
        transport: Transport,
        ledger: BudgetLedger,
        *,
        api_base: str,
        api_key: str,
        config: LLMClientConfig | None = None,
        limiter: TokenBucketLimiter | None = None,
        record_before_use: RecordBeforeUse | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._transport = transport
        self._ledger = ledger
        self._api_base = api_base
        self._api_key = api_key
        self._config = config or LLMClientConfig()
        self._limiter = limiter or TokenBucketLimiter(
            self._config.requests_per_minute, clock=clock, sleep=sleep
        )
        self._record_before_use = record_before_use
        self._clock = clock
        self._sleep = sleep
        self._rand = rand

    async def complete(self, request: LLMRequest, *, phase: str | None = None) -> LLMResponse:
        phase_name = current_phase(phase)
        start = self._clock()
        attempt = 0
        while True:
            # Reserved before every attempt, not just the first: a call that
            # would exceed the cap never reaches the network, retry or not,
            # and the reservation is atomic so concurrent callers cannot
            # overshoot it together.
            call_id = self._ledger.reserve(
                phase=phase_name, model=request.model, purpose=request.purpose
            )
            await self._limiter.acquire()
            call_start = self._clock()
            failure: TransportError | None = None
            response = None
            try:
                response = await self._transport.complete(
                    request, api_base=self._api_base, api_key=self._api_key
                )
            except TransportError as exc:
                failure = exc
            if failure is None and response is not None:
                # The ledger row is written before the hook runs: the call has
                # been made and paid for whether or not recording succeeds.
                self._finish(
                    call_id, "ok", response.tokens_in, response.tokens_out, call_start
                )
                if self._record_before_use is not None:
                    await self._invoke_hook(request, response)
                return response
            assert failure is not None
            # Every attempt is registered, success or failure, so the ledger
            # reflects real network calls made (each one counts against the
            # provider's rate limit and our own budget).
            delay = self._delay_before_retry(
                failure, call_id, call_start, start, attempt
            )
            if delay is None:
                raise terminal_error(failure)
            attempt += 1
            await self._sleep(delay)

    def _delay_before_retry(
        self,
        exc: TransportError,
        call_id: int,
        call_start: float,
        start: float,
        attempt: int,
    ) -> float | None:
        """Close out the failed attempt; return the retry delay, or None to give up.

        Returning None instead of raising keeps the `raise` at the call
        site, outside the `except` block, so the provider's unredacted
        exception is not re-linked as `__context__`.
        """
        is_retryable = exc.status_code is None or exc.status_code in RETRYABLE_STATUS_CODES
        elapsed = self._clock() - start
        if not is_retryable:
            self._finish(call_id, "error", 0, 0, call_start)
            return None
        if elapsed >= self._config.max_elapsed_s:
            self._finish(call_id, "exhausted", 0, 0, call_start)
            return None
        self._finish(call_id, "retrying", 0, 0, call_start)
        if exc.retry_after is not None:
            return exc.retry_after
        return compute_backoff_s(
            attempt,
            base_delay_s=self._config.base_delay_s,
            max_delay_s=self._config.max_delay_s,
            rand=self._rand,
        )

    async def _invoke_hook(self, request: LLMRequest, response: LLMResponse) -> None:
        """Run `record_before_use`; a failure there must not be mistaken for success.

        The ledger row is already written, so a paid call is never missing
        from the accounting. But a response whose durable recording failed
        must not be handed to a caller that would act on it — P1 relies on
        record-before-use — so the failure is surfaced as `RecordingError`.
        """
        assert self._record_before_use is not None
        try:
            await self._record_before_use(request, response)
        except Exception as exc:  # noqa: BLE001 - re-raised as RecordingError below
            failure = RecordingError(redact(f"{type(exc).__name__}: {exc}"))
            failure.__cause__ = None
            failure.__context__ = None
            failure.__suppress_context__ = True
            raise failure from None

    def _finish(
        self,
        call_id: int,
        status: str,
        tokens_in: int,
        tokens_out: int,
        call_start: float,
    ) -> None:
        self._ledger.finish(
            call_id,
            status=status,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=(self._clock() - call_start) * 1000,
        )
