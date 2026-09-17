"""Tests for agent_bisect.adapters.tau2_fake_llm: the scripted, deterministic
stand-in for a real model, plugged in at the same seam as the real one.
"""

from __future__ import annotations

import pytest
from agent_bisect.adapters.tau2_fake_llm import (
    ScriptedLLM,
    ScriptedToolCall,
    ScriptedTurn,
    ScriptExhaustedError,
    UnscriptedModelError,
)

AGENT = "fake/agent"
USER = "fake/user"


def test_serves_the_scripted_turns_in_order():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="one"), ScriptedTurn(content="two")]})

    first = llm.completion(model=AGENT, messages=[])
    second = llm.completion(model=AGENT, messages=[])

    assert first.choices[0].message.content == "one"
    assert second.choices[0].message.content == "two"


def test_dispatches_on_the_model_name():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="a")], USER: [ScriptedTurn(content="u")]})

    assert llm.completion(model=USER, messages=[]).choices[0].message.content == "u"
    assert llm.completion(model=AGENT, messages=[]).choices[0].message.content == "a"


def test_counts_calls_in_total_and_per_model():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="a")], USER: [ScriptedTurn(content="u")]})

    llm.completion(model=AGENT, messages=[])
    llm.completion(model=USER, messages=[])

    assert llm.calls == 2
    assert llm.calls_by_model == {AGENT: 1, USER: 1}


def test_emits_structured_tool_calls():
    turn = ScriptedTurn(
        tool_calls=(ScriptedToolCall(id="c1", name="get_user_details", arguments={"user_id": "u"}),)
    )
    llm = ScriptedLLM({AGENT: [turn]})

    message = llm.completion(model=AGENT, messages=[]).choices[0].message

    assert message.content is None
    assert [(tc.id, tc.function.name) for tc in message.tool_calls] == [("c1", "get_user_details")]


def test_emits_several_tool_calls_in_one_turn():
    turn = ScriptedTurn(
        tool_calls=(
            ScriptedToolCall(id="c1", name="list_all_airports", arguments={}),
            ScriptedToolCall(id="c2", name="get_user_details", arguments={"user_id": "u"}),
        )
    )
    llm = ScriptedLLM({AGENT: [turn]})

    message = llm.completion(model=AGENT, messages=[]).choices[0].message

    assert len(message.tool_calls) == 2


def test_tool_arguments_are_json_encoded_as_a_provider_would():
    turn = ScriptedTurn(
        tool_calls=(ScriptedToolCall(id="c1", name="calculate", arguments={"expression": "2 + 2"}),)
    )
    llm = ScriptedLLM({AGENT: [turn]})

    arguments = llm.completion(model=AGENT, messages=[]).choices[0].message.tool_calls[0]

    assert arguments.function.arguments == '{"expression": "2 + 2"}'


def test_responses_are_byte_identical_across_instances():
    """Two runs of the same script must produce the same response payload,
    ids and all, or a recorded fork could never be compared with its parent."""
    turn = ScriptedTurn(content="hello")

    first = ScriptedLLM({AGENT: [turn]}).completion(model=AGENT, messages=[]).to_dict()
    second = ScriptedLLM({AGENT: [turn]}).completion(model=AGENT, messages=[]).to_dict()

    assert first == second


def test_raises_when_the_script_runs_out():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="only")]})
    llm.completion(model=AGENT, messages=[])

    with pytest.raises(ScriptExhaustedError, match=AGENT):
        llm.completion(model=AGENT, messages=[])


def test_raises_on_a_model_it_has_no_script_for():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="a")]})

    with pytest.raises(UnscriptedModelError, match="gpt-4.1"):
        llm.completion(model="gpt-4.1", messages=[])


def test_strips_the_litellm_provider_prefix_before_dispatching():
    """The router sends `openai/<model>`; the script is keyed on the bare name."""
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="a")]})

    assert llm.completion(model=f"openai/{AGENT}", messages=[]).choices[0].message.content == "a"


def test_records_the_requests_it_was_given():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="a")]})

    llm.completion(model=AGENT, messages=[{"role": "user", "content": "q"}], temperature=0.0)

    assert llm.requests[0]["messages"] == [{"role": "user", "content": "q"}]
    assert llm.requests[0]["temperature"] == 0.0


def test_reports_usage_so_tau2_can_cost_the_call():
    llm = ScriptedLLM({AGENT: [ScriptedTurn(content="a")]})

    usage = llm.completion(model=AGENT, messages=[]).get("usage")

    assert usage.prompt_tokens > 0
