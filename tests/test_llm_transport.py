"""Tests for LiteLLMTransport: the `openai/<model>` route, response mapping, error normalization.

`litellm.acompletion` is monkeypatched — no real network call happens.
"""

from __future__ import annotations

import pytest
from agent_bisect.core.llm import LiteLLMTransport, LLMRequest, TransportError


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Usage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeLiteLLMResponse:
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.choices = [_Choice(content)]
        self.usage = _Usage(prompt_tokens, completion_tokens)

    def model_dump(self) -> dict:
        return {"content": self.choices[0].message.content}


def _request(
    *,
    model: str = "some-model",
    messages: tuple[dict[str, str], ...] = ({"role": "user", "content": "hi"},),
) -> LLMRequest:
    return LLMRequest(model=model, messages=messages)


@pytest.mark.asyncio
async def test_complete_uses_openai_prefixed_model(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _FakeLiteLLMResponse("hello", 5, 2)

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    transport = LiteLLMTransport()
    response = await transport.complete(
        _request(model="moonshotai/kimi-k2.6"),
        api_base="https://integrate.api.nvidia.com/v1",
        api_key="nvapi-test",
    )

    assert captured["model"] == "openai/moonshotai/kimi-k2.6"
    assert captured["api_base"] == "https://integrate.api.nvidia.com/v1"
    assert response.content == "hello"
    assert response.tokens_in == 5
    assert response.tokens_out == 2


@pytest.mark.asyncio
async def test_complete_wraps_failures_as_transport_error_and_redacts(monkeypatch):
    key = "nvapi-" + "c" * 40

    async def fake_acompletion(**kwargs):
        raise RuntimeError(f"upstream rejected key {key}")

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    transport = LiteLLMTransport()

    with pytest.raises(TransportError) as excinfo:
        await transport.complete(_request(), api_base="https://x.invalid/v1", api_key=key)

    assert key not in str(excinfo.value)


@pytest.mark.asyncio
async def test_complete_preserves_status_code_from_exception(monkeypatch):
    class _RateLimitError(RuntimeError):
        status_code = 429

    async def fake_acompletion(**kwargs):
        raise _RateLimitError("too many requests")

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    transport = LiteLLMTransport()

    with pytest.raises(TransportError) as excinfo:
        await transport.complete(_request(), api_base="https://x.invalid/v1", api_key="nvapi-test")

    assert excinfo.value.status_code == 429
