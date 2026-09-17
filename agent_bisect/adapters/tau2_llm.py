"""Route every τ²-bench LLM call through our limiter, retries, ledger and recording hook.

τ²-bench calls LiteLLM itself: `tau2.utils.llm_utils.generate()` builds the
request and hands it to the module-level `completion` symbol it imported
from litellm. Both participants go through that one function — the agent
(`tau2.agent.llm_agent`) and the user simulator
(`tau2.user.user_simulator`) — so rebinding `llm_utils.completion` is the
single choke point for all of τ²'s traffic.

`route_tau2_llm(...)` is a context manager that installs two reversible
patches and removes both on exit, including when the body raises:

1. `llm_utils.completion` → `Tau2Router.completion`, which takes a token
   from the process-wide limiter, checks the budget, injects `api_base`
   and `api_key`, forces litellm's own `num_retries` to 0 (so *our*
   backoff paces every attempt), retries 429/5xx with full-jitter backoff
   honouring `Retry-After`, writes one ledger row per attempt, and calls
   the `on_call(request, response, meta)` hook **before** returning —
   record-before-use, which P1 relies on.
2. each participant module's `generate` → a thin wrapper that tags the
   call's purpose ("agent" / "user") in a `ContextVar` the router reads.
   τ² runs tasks in worker threads, and a `ContextVar` set inside the
   calling thread is read back in that same thread.

The key is never placed in τ²'s `llm_args`, so it cannot reach τ²'s
results JSON or its LLM debug logs; it is injected per call inside the
router, and every error string is passed through `core.config.redact`.

Nothing here opens a socket in tests: `completion_fn` is injected.
"""

from __future__ import annotations

import functools
import json
import logging
import random
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from agent_bisect.core.budget import BudgetLedger, current_phase
from agent_bisect.core.config import Settings, get_settings
from agent_bisect.core.limits import get_shared_limiter
from agent_bisect.core.llm import (
    RETRYABLE_STATUS_CODES,
    TransportError,
    compute_backoff_s,
    terminal_error,
    transport_error_from,
)

DEFAULT_MAX_ELAPSED_S = 300.0
DEFAULT_BASE_DELAY_S = 1.0
DEFAULT_MAX_DELAY_S = 30.0
DEFAULT_PURPOSE = "tau2"
TEXTUAL_SCAN_WINDOW = 200
#: Never copied into the recorded request handed to the on_call hook.
SECRET_KWARGS = frozenset({"api_key", "api_base", "azure_ad_token", "aws_secret_access_key"})

#: τ² module path -> the ledger purpose its `generate` calls belong to.
PARTICIPANT_PURPOSE = {
    "tau2.agent.llm_agent": "agent",
    "tau2.user.user_simulator": "user",
}

_purpose: ContextVar[str] = ContextVar("bisect_tau2_purpose", default=DEFAULT_PURPOSE)
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    max_elapsed_s: float = DEFAULT_MAX_ELAPSED_S
    base_delay_s: float = DEFAULT_BASE_DELAY_S
    max_delay_s: float = DEFAULT_MAX_DELAY_S


@dataclass(frozen=True)
class CallMeta:
    """What the recording hook learns about a completed call."""

    purpose: str
    phase: str
    model: str
    attempts: int
    latency_ms: float


OnCall = Callable[[dict, Any, CallMeta], None]


def _as_transport_error(exc: BaseException) -> TransportError:
    """Normalise to a TransportError that keeps nothing unredacted reachable."""
    if isinstance(exc, TransportError):
        return exc
    return transport_error_from(exc)


class Tau2Router:
    """The replacement for `llm_utils.completion`. One instance per routed context."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        ledger: BudgetLedger,
        limiter_for: Callable[[str], Any],
        completion_fn: Callable[..., Any],
        phase: str,
        on_call: OnCall | None = None,
        config: RetryConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._ledger = ledger
        self.limiter_for = limiter_for
        self._completion_fn = completion_fn
        self._phase = phase
        self._on_call = on_call
        self._config = config or RetryConfig()
        self._clock = clock
        self._sleep = sleep
        self._rand = rand

    def completion(self, *, model: str, messages: Any, **kwargs: Any) -> Any:
        """Rate-limited, retrying, ledgered stand-in for `litellm.completion`."""
        purpose = _purpose.get()
        # Defence in depth: whatever the caller passed, the recorded request
        # never carries credentials into the hook (and so into P1's tape).
        safe_kwargs = {k: v for k, v in kwargs.items() if k not in SECRET_KWARGS}
        request = {"model": model, "messages": messages, "purpose": purpose, **safe_kwargs}
        # litellm's own retries would bypass our limiter and our ledger.
        payload = {
            **kwargs,
            "model": f"openai/{model}",
            "messages": messages,
            "api_base": self._api_base,
            "api_key": self._api_key,
            "num_retries": 0,
        }
        start = self._clock()
        response, attempts = self._attempt_until_done(model, purpose, payload, start)
        if self._on_call is not None:
            self._on_call(request, response, CallMeta(
                purpose=purpose,
                phase=self._phase,
                model=model,
                attempts=attempts,
                latency_ms=(self._clock() - start) * 1000,
            ))
        return response

    def _attempt_until_done(
        self, model: str, purpose: str, payload: dict, start: float
    ) -> tuple[Any, int]:
        attempt = 0
        while True:
            call_id = self._ledger.reserve(phase=self._phase, model=model, purpose=purpose)
            self.limiter_for(model).acquire_sync()
            call_start = self._clock()
            failure: TransportError | None = None
            response = None
            try:
                response = self._completion_fn(**payload)
            except Exception as exc:  # noqa: BLE001 - normalised below
                # Deliberately Exception, not BaseException: a KeyboardInterrupt
                # has no status_code, so it would be classified as retryable and
                # slept on until the elapsed budget ran out. Ctrl+C must stop a
                # probe, not be swallowed by the backoff.
                failure = _as_transport_error(exc)
            if failure is None:
                self._finish(call_id, "ok", call_start)
                return response, attempt + 1
            delay = self._delay_before_retry(failure, call_id, call_start, start, attempt)
            if delay is None:
                # Raised OUTSIDE the except block: `raise` inside one re-links
                # __context__ to the provider exception, whose text is
                # unredacted. See core.llm.transport_error_from.
                raise terminal_error(failure)
            attempt += 1
            self._sleep(delay)

    def _delay_before_retry(
        self,
        exc: TransportError,
        call_id: int,
        call_start: float,
        start: float,
        attempt: int,
    ) -> float | None:
        """Record the failed attempt; return the retry delay, or None to give up.

        Returning None rather than raising keeps the `raise` at the call
        site, outside the `except` block, so the provider exception is not
        re-linked as `__context__`.
        """
        retryable = exc.status_code is None or exc.status_code in RETRYABLE_STATUS_CODES
        if not retryable:
            self._finish(call_id, "error", call_start)
            return None
        if self._clock() - start >= self._config.max_elapsed_s:
            self._finish(call_id, "exhausted", call_start)
            return None
        self._finish(call_id, "retrying", call_start)
        # Without this the ledger shows a "retrying" row with no reason, and a
        # run that is quietly burning a third of its calls on retries looks
        # identical to one that is merely slow. The message is already redacted
        # by TransportError.
        _log.warning(
            "retrying call %d after status=%s attempt=%d: %s",
            call_id, exc.status_code, attempt + 1, exc,
        )
        if exc.retry_after is not None:
            return exc.retry_after
        return compute_backoff_s(
            attempt,
            base_delay_s=self._config.base_delay_s,
            max_delay_s=self._config.max_delay_s,
            rand=self._rand,
        )

    def _finish(self, call_id: int, status: str, call_start: float) -> None:
        self._ledger.finish(
            call_id, status=status, latency_ms=(self._clock() - call_start) * 1000
        )


def _tag_purpose(original: Callable[..., Any], purpose: str) -> Callable[..., Any]:
    """Wrap a participant's `generate` so the router can tell who is calling."""

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = _purpose.set(purpose)
        try:
            return original(*args, **kwargs)
        finally:
            _purpose.reset(token)

    return wrapper


def _patch_participants(modules: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    originals = {name: module.generate for name, module in modules.items()}
    for name, module in modules.items():
        module.generate = _tag_purpose(originals[name], PARTICIPANT_PURPOSE[name])
    return originals


def _import_participants() -> dict[str, Any]:
    import importlib

    from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir

    ensure_tau2_data_dir()
    return {name: importlib.import_module(name) for name in PARTICIPANT_PURPOSE}


@contextmanager
def route_tau2_llm(
    *,
    ledger: BudgetLedger,
    api_base: str | None = None,
    api_key: str | None = None,
    settings: Settings | None = None,
    phase: str | None = None,
    on_call: OnCall | None = None,
    completion_fn: Callable[..., Any] | None = None,
    limiter_for: Callable[[str], Any] | None = None,
    config: RetryConfig | None = None,
) -> Iterator[Tau2Router]:
    """Route every τ² LLM call through `Tau2Router` for the duration of the block."""
    resolved = settings or (get_settings() if api_key is None or api_base is None else None)
    if api_key is None:
        if resolved is None or resolved.nvidia_api_key is None:
            raise RuntimeError("NVIDIA_API_KEY not set; cannot route τ² LLM calls.")
        api_key = resolved.nvidia_api_key.get_secret_value()
    if api_base is None:
        assert resolved is not None
        api_base = resolved.nvidia_base_url

    if completion_fn is None:
        import litellm

        completion_fn = litellm.completion

    import tau2.utils.llm_utils as llm_utils

    modules = _import_participants()
    router = Tau2Router(
        api_base=api_base,
        api_key=api_key,
        ledger=ledger,
        limiter_for=limiter_for or get_shared_limiter,
        completion_fn=completion_fn,
        phase=current_phase(phase),
        on_call=on_call,
        config=config,
    )
    original_completion = llm_utils.completion
    original_generates = _patch_participants(modules)
    llm_utils.completion = router.completion
    try:
        yield router
    finally:
        llm_utils.completion = original_completion
        for name, original in original_generates.items():
            modules[name].generate = original


# ---------------------------------------------------------------------------
# Tool-call accounting (the "valid tool call rate" of 0004 §2)
# ---------------------------------------------------------------------------

_ENVELOPE_PATTERNS = (
    re.compile(r"<tool_call\b", re.IGNORECASE),
    re.compile(r"<\|tool[_▁]?call[^|]*\|>", re.IGNORECASE),
    re.compile(r"<function[ =]", re.IGNORECASE),
    re.compile(r"```tool_(?:code|call)", re.IGNORECASE),
)
_NAME_PATTERN = re.compile(r'"name"\s*:\s*"([A-Za-z0-9_.-]+)"')
_ARGUMENT_KEYS = ('"arguments"', '"parameters"')

ToolValidator = Callable[[str, dict], bool]


@dataclass(frozen=True)
class ToolCallStats:
    """Per-response tool-call tally. `total` is the ratio's denominator."""

    total: int = 0
    valid: int = 0
    reasons: tuple[str, ...] = field(default_factory=tuple)


def count_textual_tool_calls(content: str, known_names: set[str]) -> int:
    """Tool calls typed into `content` instead of the structured field.

    Counts a chat-template envelope (`<tool_call>`, `<|tool_call|>`,
    `<function=…>`, a ```tool_code fence) if present; otherwise a bare JSON
    object naming a real domain tool alongside an arguments key.
    """
    if not content:
        return 0
    envelopes = sum(len(pattern.findall(content)) for pattern in _ENVELOPE_PATTERNS)
    if envelopes:
        return envelopes
    count = 0
    for match in _NAME_PATTERN.finditer(content):
        if match.group(1) not in known_names:
            continue
        window = content[match.start() - TEXTUAL_SCAN_WINDOW : match.end() + TEXTUAL_SCAN_WINDOW]
        if any(key in window for key in _ARGUMENT_KEYS):
            count += 1
    return count


def _call_fields(call: Any) -> tuple[str | None, Any]:
    function = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
    if function is None:
        return None, None
    if isinstance(function, dict):
        return function.get("name"), function.get("arguments")
    return getattr(function, "name", None), getattr(function, "arguments", None)


def _classify_one(
    call: Any, known_names: set[str], validate: ToolValidator
) -> str | None:
    """None when the call is valid, else the reason it is not."""
    name, raw_arguments = _call_fields(call)
    if not name:
        return "no_tool_name"
    if name not in known_names:
        return f"unknown_tool:{name}"
    if isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        try:
            arguments = json.loads(raw_arguments or "{}")
        except (TypeError, ValueError):
            return f"bad_json:{name}"
        if not isinstance(arguments, dict):
            return f"bad_json:{name}"
    return None if validate(name, arguments) else f"schema:{name}"


def classify_tool_calls(
    tool_calls: Any,
    content: str | None,
    known_names: set[str],
    validate: ToolValidator,
) -> ToolCallStats:
    """Tally one agent response against 0004 §2's valid-tool-call definition."""
    if tool_calls:
        reasons = tuple(
            reason
            for reason in (_classify_one(call, known_names, validate) for call in tool_calls)
            if reason is not None
        )
        return ToolCallStats(
            total=len(tool_calls), valid=len(tool_calls) - len(reasons), reasons=reasons
        )
    textual = count_textual_tool_calls(content or "", known_names)
    return ToolCallStats(total=textual, valid=0, reasons=("textual_tool_call",) * textual)


def tool_checker_for(environment: Any) -> tuple[set[str], ToolValidator]:
    """Domain agent tool names plus a validator over each tool's own pydantic schema."""
    tools = {tool.name: tool for tool in environment.get_tools()}

    def validate(name: str, arguments: dict) -> bool:
        tool = tools.get(name)
        if tool is None:
            return False
        try:
            tool.params.model_validate(arguments)
        except Exception:  # noqa: BLE001 - any validation failure means "invalid call"
            return False
        return True

    return set(tools), validate
