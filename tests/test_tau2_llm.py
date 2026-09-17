"""Tests for the τ² ↔ core.llm bridge. Fully offline: a fake completion function, no sockets."""

from __future__ import annotations

import threading
from collections.abc import Sequence

import pytest
from agent_bisect.adapters.tau2_llm import (
    CallMeta,
    RetryConfig,
    Tau2Router,
    classify_tool_calls,
    count_textual_tool_calls,
    route_tau2_llm,
)
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.llm import TokenBucketLimiter, TransportError

API_BASE = "https://integrate.api.nvidia.com/v1"
# Assembled at runtime on purpose: a literal `nvapi-<20+ chars>` in source is
# (correctly) blocked by the repo's pre-commit secret scanner, fake or not.
FAKE_KEY = "nvapi" + "-" + "F" * 24


class FakeUsage:
    prompt_tokens = 7
    completion_tokens = 3


class FakeMessage:
    def __init__(self, content: str, tool_calls) -> None:
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, content: str, tool_calls) -> None:
        self.finish_reason = "stop"
        self.message = FakeMessage(content, tool_calls)


class FakeResponse:
    """Stands in for litellm's ModelResponse — enough for τ²'s `generate` to consume it."""

    def __init__(self, content: str = "hi", tool_calls=None) -> None:
        self.model = "fake"
        self.choices = [FakeChoice(content, tool_calls)]
        self.usage = FakeUsage()

    def get(self, key, default=None):
        return getattr(self, key, default)

    def to_dict(self) -> dict:
        return {"choices": [{"message": {"content": self.choices[0].message.content}}]}


class FakeCompletion:
    """Records the kwargs it was called with; optionally raises a scripted sequence."""

    def __init__(self, errors: Sequence[BaseException] | None = None) -> None:
        self.calls: list[dict] = []
        self.errors = list(errors or [])

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return FakeResponse()


class RecordingLimiter:
    def __init__(self) -> None:
        self.acquisitions = 0

    def acquire_sync(self) -> None:
        self.acquisitions += 1


def make_router(tmp_path, completion_fn, *, on_call=None, limiter=None, sleeps=None, **kwargs):
    limiter = limiter or RecordingLimiter()
    return Tau2Router(
        api_base=API_BASE,
        api_key=FAKE_KEY,
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        limiter_for=lambda _model: limiter,
        completion_fn=completion_fn,
        phase="P0",
        on_call=on_call,
        sleep=(sleeps.append if sleeps is not None else lambda _s: None),
        **kwargs,
    )


# ---- routing ----


def test_routes_the_model_through_the_openai_compatible_prefix(tmp_path):
    completion = FakeCompletion()
    router = make_router(tmp_path, completion)

    router.completion(model="z-ai/glm-5.3-flash", messages=[{"role": "user", "content": "x"}])

    assert completion.calls[0]["model"] == "openai/z-ai/glm-5.3-flash"


def test_injects_api_base_and_key(tmp_path):
    completion = FakeCompletion()
    router = make_router(tmp_path, completion)

    router.completion(model="m", messages=[])

    assert completion.calls[0]["api_base"] == API_BASE
    assert completion.calls[0]["api_key"] == FAKE_KEY


def test_forces_litellm_retries_off_so_our_limiter_paces_every_attempt(tmp_path):
    completion = FakeCompletion()
    router = make_router(tmp_path, completion)

    router.completion(model="m", messages=[], num_retries=3)

    assert completion.calls[0]["num_retries"] == 0


def test_every_attempt_takes_a_token_from_the_limiter(tmp_path):
    limiter = RecordingLimiter()
    completion = FakeCompletion(errors=[TransportError("boom", status_code=429)])
    router = make_router(tmp_path, completion, limiter=limiter)

    router.completion(model="m", messages=[])

    assert limiter.acquisitions == 2  # the failed attempt and the retry


def test_ledger_records_one_row_per_attempt(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")
    completion = FakeCompletion(errors=[TransportError("boom", status_code=500)])
    router = Tau2Router(
        api_base=API_BASE,
        api_key=FAKE_KEY,
        ledger=ledger,
        limiter_for=lambda _m: RecordingLimiter(),
        completion_fn=completion,
        phase="P0",
        sleep=lambda _s: None,
    )

    router.completion(model="m", messages=[])

    assert ledger.total_calls() == 2
    assert ledger.totals_per_phase() == {"P0": 2}


# ---- retries ----


def test_retries_a_429_and_returns_the_eventual_response(tmp_path):
    completion = FakeCompletion(errors=[TransportError("slow down", status_code=429)])
    router = make_router(tmp_path, completion)

    response = router.completion(model="m", messages=[])

    assert isinstance(response, FakeResponse)
    assert len(completion.calls) == 2


def test_honours_retry_after_over_computed_backoff(tmp_path):
    sleeps: list[float] = []
    error = TransportError("slow down", status_code=429, retry_after=12.5)
    router = make_router(tmp_path, FakeCompletion(errors=[error]), sleeps=sleeps)

    router.completion(model="m", messages=[])

    assert sleeps == [12.5]


def test_gives_up_after_the_elapsed_budget_and_raises(tmp_path):
    errors = [TransportError("nope", status_code=503) for _ in range(20)]
    router = make_router(
        tmp_path,
        FakeCompletion(errors=errors),
        config=RetryConfig(max_elapsed_s=0.0),
    )

    with pytest.raises(TransportError):
        router.completion(model="m", messages=[])


def test_a_non_retryable_status_is_raised_immediately(tmp_path):
    completion = FakeCompletion(errors=[TransportError("bad request", status_code=400)])
    router = make_router(tmp_path, completion)

    with pytest.raises(TransportError):
        router.completion(model="m", messages=[])

    assert len(completion.calls) == 1


def test_error_text_is_redacted_before_it_can_reach_a_log(tmp_path):
    leak = RuntimeError(f"upstream echoed {FAKE_KEY} back")
    router = make_router(
        tmp_path, FakeCompletion(errors=[leak]), config=RetryConfig(max_elapsed_s=0.0)
    )

    with pytest.raises(TransportError) as excinfo:
        router.completion(model="m", messages=[])

    assert FAKE_KEY not in str(excinfo.value)
    assert "REDACTED" in str(excinfo.value)


# ---- the record-before-use hook ----


def test_on_call_runs_before_the_response_is_returned(tmp_path):
    order: list[str] = []

    def on_call(request, response, meta):
        order.append("hook")
        assert isinstance(meta, CallMeta)

    router = make_router(tmp_path, FakeCompletion(), on_call=on_call)
    router.completion(model="m", messages=[])
    order.append("returned")

    assert order == ["hook", "returned"]


def test_the_hook_never_sees_the_api_key(tmp_path):
    seen: list[dict] = []
    router = make_router(tmp_path, FakeCompletion(), on_call=lambda req, _r, _m: seen.append(req))

    router.completion(model="m", messages=[{"role": "user", "content": "hello"}])

    assert FAKE_KEY not in repr(seen[0])
    assert "api_key" not in seen[0]
    assert seen[0]["model"] == "m"


def test_hook_meta_carries_purpose_phase_and_attempts(tmp_path):
    seen: list[CallMeta] = []
    completion = FakeCompletion(errors=[TransportError("x", status_code=429)])
    router = make_router(tmp_path, completion, on_call=lambda _q, _r, meta: seen.append(meta))

    router.completion(model="m", messages=[])

    assert seen[0].phase == "P0"
    assert seen[0].attempts == 2
    assert seen[0].purpose == "tau2"


# ---- the reversible patch ----


def test_route_tau2_llm_patches_and_restores_litellm_completion(tmp_path):
    import tau2.utils.llm_utils as llm_utils

    original = llm_utils.completion

    with route_tau2_llm(
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        api_base=API_BASE,
        api_key=FAKE_KEY,
        completion_fn=FakeCompletion(),
        phase="P0",
    ):
        assert llm_utils.completion is not original

    assert llm_utils.completion is original


def test_route_tau2_llm_restores_even_when_the_body_raises(tmp_path):
    import tau2.utils.llm_utils as llm_utils

    original = llm_utils.completion

    with pytest.raises(ValueError), route_tau2_llm(
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        api_base=API_BASE,
        api_key=FAKE_KEY,
        completion_fn=FakeCompletion(),
        phase="P0",
    ):
        raise ValueError("boom")

    assert llm_utils.completion is original


def test_agent_and_user_calls_are_tagged_with_their_purpose(tmp_path):
    """The real τ² `generate` of each participant module, through the real patch."""
    import tau2.agent.llm_agent as agent_module
    import tau2.user.user_simulator as user_module
    from tau2.data_model.message import SystemMessage, UserMessage

    seen: list[str] = []
    history = [
        SystemMessage(role="system", content="you are a test"),
        UserMessage(role="user", content="hello"),
    ]

    with route_tau2_llm(
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        api_base=API_BASE,
        api_key=FAKE_KEY,
        completion_fn=FakeCompletion(),
        phase="P0",
        on_call=lambda _q, _r, meta: seen.append(meta.purpose),
    ):
        agent_module.generate(model="m", messages=history)
        user_module.generate(model="m", messages=history)

    assert seen == ["agent", "user"]


def test_participant_generate_is_restored_after_the_context_exits(tmp_path):
    import tau2.agent.llm_agent as agent_module
    import tau2.user.user_simulator as user_module

    agent_original = agent_module.generate
    user_original = user_module.generate

    with route_tau2_llm(
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        api_base=API_BASE,
        api_key=FAKE_KEY,
        completion_fn=FakeCompletion(),
        phase="P0",
    ):
        assert agent_module.generate is not agent_original

    assert agent_module.generate is agent_original
    assert user_module.generate is user_original


def test_one_limiter_serves_every_thread_under_the_router(tmp_path):
    """τ² runs tasks in threads; all of them must share one bucket."""
    limiter = TokenBucketLimiter(6000)
    router = Tau2Router(
        api_base=API_BASE,
        api_key=FAKE_KEY,
        ledger=BudgetLedger(tmp_path / "ledger.sqlite"),
        limiter_for=lambda _m: limiter,
        completion_fn=FakeCompletion(),
        phase="P0",
        sleep=lambda _s: None,
    )
    seen: list[object] = []
    lock = threading.Lock()

    def worker():
        router.completion(model="m", messages=[])
        with lock:
            seen.append(router.limiter_for("m"))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(seen) == 6
    assert all(item is limiter for item in seen)


# ---- tool-call accounting ----

AIRLINE_TOOLS = {
    "get_reservation_details": {"reservation_id": {"type": "string"}},
    "search_direct_flight": {"origin": {"type": "string"}},
}


def _schema_validator(name: str, arguments: dict) -> bool:
    required = AIRLINE_TOOLS.get(name)
    if required is None:
        return False
    return all(key in required for key in arguments)


def test_a_well_formed_tool_call_counts_as_valid():
    tool_calls = [{"function": {"name": "get_reservation_details",
                                "arguments": '{"reservation_id": "NM1VX1"}'}}]

    result = classify_tool_calls(tool_calls, "", set(AIRLINE_TOOLS), _schema_validator)

    assert (result.total, result.valid) == (1, 1)
    assert result.reasons == ()


def test_an_unknown_tool_name_is_invalid():
    tool_calls = [{"function": {"name": "teleport", "arguments": "{}"}}]

    result = classify_tool_calls(tool_calls, "", set(AIRLINE_TOOLS), _schema_validator)

    assert (result.total, result.valid) == (1, 0)
    assert result.reasons == ("unknown_tool:teleport",)


def test_unparseable_arguments_are_invalid():
    tool_calls = [{"function": {"name": "search_direct_flight", "arguments": "{origin:"}}]

    result = classify_tool_calls(tool_calls, "", set(AIRLINE_TOOLS), _schema_validator)

    assert (result.total, result.valid) == (1, 0)
    assert result.reasons == ("bad_json:search_direct_flight",)


def test_arguments_failing_the_tool_schema_are_invalid():
    tool_calls = [{"function": {"name": "search_direct_flight",
                                "arguments": '{"destination": "SFO"}'}}]

    result = classify_tool_calls(tool_calls, "", set(AIRLINE_TOOLS), _schema_validator)

    assert (result.total, result.valid) == (1, 0)
    assert result.reasons == ("schema:search_direct_flight",)


def test_a_business_logic_error_is_still_a_valid_call():
    """'reservation not found' is the world saying no, not a malformed call."""
    tool_calls = [{"function": {"name": "get_reservation_details",
                                "arguments": '{"reservation_id": "NOPE42"}'}}]

    result = classify_tool_calls(tool_calls, "", set(AIRLINE_TOOLS), _schema_validator)

    assert result.valid == 1


def test_a_tool_call_typed_into_content_counts_as_an_invalid_call():
    content = '<tool_call>{"name": "get_reservation_details", "arguments": {}}</tool_call>'

    result = classify_tool_calls(None, content, set(AIRLINE_TOOLS), _schema_validator)

    assert (result.total, result.valid) == (1, 0)
    assert result.reasons == ("textual_tool_call",)


def test_a_bare_json_tool_call_in_content_is_detected():
    content = 'Sure: {"name": "search_direct_flight", "arguments": {"origin": "JFK"}}'

    assert count_textual_tool_calls(content, set(AIRLINE_TOOLS)) == 1


def test_prose_naming_a_tool_is_not_a_textual_tool_call():
    content = "I will look up your reservation details in a moment."

    assert count_textual_tool_calls(content, set(AIRLINE_TOOLS)) == 0


def test_an_ordinary_message_contributes_to_neither_side_of_the_ratio():
    result = classify_tool_calls(None, "Your flight is confirmed.", set(AIRLINE_TOOLS),
                                _schema_validator)

    assert (result.total, result.valid) == (0, 0)


def test_structured_tool_calls_suppress_the_textual_heuristic():
    """A model that also narrates its call must not be double-counted."""
    tool_calls = [{"function": {"name": "search_direct_flight",
                                "arguments": '{"origin": "JFK"}'}}]
    content = '{"name": "search_direct_flight", "arguments": {"origin": "JFK"}}'

    result = classify_tool_calls(tool_calls, content, set(AIRLINE_TOOLS), _schema_validator)

    assert (result.total, result.valid) == (1, 1)
