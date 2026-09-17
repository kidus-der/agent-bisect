"""The five intervention types, plus the label-free `TruthfulToolResult`.

Nothing here touches tau2: an intervention is a pure function from
(recorded step, recorded payload) to the payload that should be used
instead, so it is tested on plain dicts. The end-to-end wiring against
tau2's real orchestrator lives in `tests/test_tau2_interventions.py`.
"""

from __future__ import annotations

import pytest
from agent_bisect.attribution.interventions import (
    EditPrompt,
    ForceAction,
    MisappliedInterventionError,
    PromptPatch,
    ReplaceToolResult,
    Resample,
    SwapModel,
    TruthfulToolResult,
    UnresolvedInterventionError,
    from_ref,
    shaped_completion,
)
from agent_bisect.core.replay import LIVE, Intervention
from agent_bisect.core.tape import Step

FORK_STEP = 3


def step_of(actor: str, *, step_idx: int = FORK_STEP, **fields) -> Step:
    return Step(
        run_id="r1",
        step_idx=step_idx,
        actor=actor,  # pyright: ignore[reportArgumentType]
        state_before="a" * 64,
        state_after="b" * 64,
        state_hash="c" * 64,
        **fields,
    )


def tool_payload(content: str = '{"seats": 3}', **fields) -> dict:
    return {
        "id": "call-1",
        "role": "tool",
        "requestor": "assistant",
        "content": content,
        "error": False,
        "turn_idx": 2,
        "timestamp": "2026-09-17T00:00:00",
        **fields,
    }


def llm_payload(content: str | None = "recorded reply") -> dict:
    return {
        "id": "resp-1",
        "created": 1_758_000_000,
        "model": "fake/agent-model",
        "choices": [
            {"index": 0, "finish_reason": "stop",
             "message": {"role": "assistant", "content": content}}
        ],
    }


ALL = (
    ReplaceToolResult(step=FORK_STEP, new_result=tool_payload('{"seats": 0}')),
    ForceAction(step=FORK_STEP, message="do it now"),
    Resample(step=FORK_STEP),
    EditPrompt(from_step=FORK_STEP, new_system_prompt="you are terse"),
    SwapModel(from_step=FORK_STEP, model="other/model"),
    TruthfulToolResult(step=FORK_STEP),
)


# ---- the protocol, the hash and the ref blob ----


@pytest.mark.parametrize("intervention", ALL, ids=lambda i: i.name)
def test_every_intervention_satisfies_the_core_protocol(intervention):
    assert isinstance(intervention, Intervention)
    assert intervention.name
    assert intervention.describe()


@pytest.mark.parametrize("intervention", ALL, ids=lambda i: i.name)
def test_the_hash_is_stable_across_instances(intervention):
    twin = from_ref(intervention.to_ref())

    assert twin.intervention_hash == intervention.intervention_hash
    assert twin.to_ref() == intervention.to_ref()


def test_different_interventions_hash_differently():
    hashes = {intervention.intervention_hash for intervention in ALL}

    assert len(hashes) == len(ALL)


def test_the_hash_ignores_nothing_that_changes_behaviour():
    one = ReplaceToolResult(step=FORK_STEP, new_result=tool_payload('{"seats": 0}'))
    other = ReplaceToolResult(step=FORK_STEP, new_result=tool_payload('{"seats": 1}'))

    assert one.intervention_hash != other.intervention_hash


def test_an_unknown_ref_is_refused():
    with pytest.raises(ValueError, match="unknown intervention"):
        from_ref({"name": "teleport", "fields": {}})


# ---- ReplaceToolResult ----


def test_replace_tool_result_changes_what_the_agent_sees():
    intervention = ReplaceToolResult(step=FORK_STEP, new_result=tool_payload('{"seats": 0}'))

    applied = intervention.apply(step_of("tool"), tool_payload())

    assert applied["content"] == '{"seats": 0}'


def test_replace_tool_result_keeps_the_live_call_identity():
    """The replacement is what the tool *said*, never which call it answered:
    a `ToolMessage` whose id stopped matching its `ToolCall` is not a
    counterfactual, it is a broken conversation."""
    intervention = ReplaceToolResult(
        step=FORK_STEP, new_result=tool_payload('{"seats": 0}', id="stale", turn_idx=99)
    )

    applied = intervention.apply(step_of("tool"), tool_payload(id="live-call"))

    assert applied["id"] == "live-call"
    assert applied["turn_idx"] == 2


def test_replace_tool_result_refuses_a_step_that_is_not_a_tool_step():
    intervention = ReplaceToolResult(step=FORK_STEP, new_result=tool_payload())

    with pytest.raises(MisappliedInterventionError, match="tool"):
        intervention.apply(step_of("agent"), llm_payload())


def test_an_intervention_refuses_a_step_that_is_not_its_own():
    intervention = ReplaceToolResult(step=FORK_STEP, new_result=tool_payload())

    with pytest.raises(MisappliedInterventionError, match="step"):
        intervention.apply(step_of("tool", step_idx=FORK_STEP + 1), tool_payload())


# ---- ForceAction ----


def test_force_action_replaces_the_agents_message():
    intervention = ForceAction(step=FORK_STEP, message="say this instead")

    applied = intervention.apply(step_of("agent"), llm_payload())

    assert applied["choices"][0]["message"]["content"] == "say this instead"
    assert applied["id"] == "resp-1"


def test_force_action_can_force_a_tool_call():
    intervention = ForceAction(
        step=FORK_STEP,
        tool_call={"id": "forced-1", "name": "get_user_details", "arguments": {"user_id": "u"}},
    )

    message = intervention.apply(step_of("agent"), llm_payload())["choices"][0]["message"]

    assert message["content"] is None
    assert message["tool_calls"][0]["function"]["name"] == "get_user_details"
    assert message["tool_calls"][0]["function"]["arguments"] == '{"user_id": "u"}'


def test_force_action_needs_exactly_one_of_message_or_tool_call():
    with pytest.raises(ValueError, match="exactly one"):
        ForceAction(step=FORK_STEP)
    with pytest.raises(ValueError, match="exactly one"):
        ForceAction(step=FORK_STEP, message="a", tool_call={"id": "1", "name": "t"})


def test_force_action_refuses_a_tool_step():
    with pytest.raises(MisappliedInterventionError, match="agent"):
        ForceAction(step=FORK_STEP, message="x").apply(step_of("tool"), tool_payload())


# ---- Resample ----


def test_resample_changes_nothing_and_asks_for_a_fresh_sample():
    assert Resample(step=FORK_STEP).apply(step_of("agent"), llm_payload()) is LIVE
    assert Resample(step=FORK_STEP).apply(step_of("tool"), tool_payload()) is LIVE


# ---- EditPrompt and SwapModel: they shape the live requests after k ----


def test_edit_prompt_resamples_its_own_step():
    """A prompt that changes from k onward changes step k's own answer too,
    so the recorded response at k cannot be reused."""
    assert EditPrompt(from_step=FORK_STEP, new_system_prompt="terse").apply(
        step_of("agent"), llm_payload()
    ) is LIVE


def test_edit_prompt_replaces_the_system_message():
    intervention = EditPrompt(from_step=FORK_STEP, new_system_prompt="you are terse")

    shaped = intervention.shape_request(
        {"model": "m", "messages": [{"role": "system", "content": "long policy"},
                                    {"role": "user", "content": "hi"}]}
    )

    assert shaped["messages"][0]["content"] == "you are terse"
    assert shaped["messages"][1] == {"role": "user", "content": "hi"}


def test_edit_prompt_can_patch_a_fragment_instead():
    intervention = EditPrompt(
        from_step=FORK_STEP, patch=PromptPatch(find="never refund", replace="always refund")
    )

    shaped = intervention.shape_request(
        {"model": "m", "messages": [{"role": "system", "content": "you never refund a ticket"}]}
    )

    assert shaped["messages"][0]["content"] == "you always refund a ticket"


def test_edit_prompt_refuses_a_patch_that_matches_nothing():
    intervention = EditPrompt(from_step=FORK_STEP, patch=PromptPatch(find="absent", replace="x"))

    with pytest.raises(ValueError, match="matched no system prompt"):
        intervention.shape_request(
            {"model": "m", "messages": [{"role": "system", "content": "policy"}]}
        )


def test_edit_prompt_leaves_other_participants_alone_when_scoped():
    intervention = EditPrompt(
        from_step=FORK_STEP, new_system_prompt="terse", model="fake/agent-model"
    )
    request = {"model": "fake/user-model",
               "messages": [{"role": "system", "content": "you are a customer"}]}

    assert intervention.shape_request(request) == request


def test_edit_prompt_needs_exactly_one_of_prompt_or_patch():
    with pytest.raises(ValueError, match="exactly one"):
        EditPrompt(from_step=FORK_STEP)


def test_swap_model_swaps_the_model_of_every_live_request():
    intervention = SwapModel(from_step=FORK_STEP, model="other/model")

    shaped = intervention.shape_request({"model": "fake/agent-model", "messages": []})

    assert shaped["model"] == "other/model"


def test_swap_model_can_be_scoped_to_one_participant():
    intervention = SwapModel(
        from_step=FORK_STEP, model="other/model", replaces="fake/agent-model"
    )

    assert intervention.shape_request({"model": "fake/user-model"})["model"] == "fake/user-model"
    assert intervention.shape_request({"model": "fake/agent-model"})["model"] == "other/model"


def test_shaped_completion_wraps_only_a_shaping_intervention():
    seen: list[dict] = []

    def completion(**kwargs):
        seen.append(kwargs)
        return "ok"

    shaped_completion(SwapModel(from_step=0, model="new/model"), completion)(
        model="old/model", messages=[]
    )
    shaped_completion(Resample(step=0), completion)(model="old/model", messages=[])

    assert [call["model"] for call in seen] == ["new/model", "old/model"]


# ---- TruthfulToolResult ----


def test_truthful_tool_result_shows_the_re_executed_answer():
    truth = tool_payload('{"seats": 3}')
    intervention = TruthfulToolResult(step=FORK_STEP).with_truth(lambda _step: truth)

    applied = intervention.apply(step_of("tool"), tool_payload('{"seats": 0}'))

    assert applied["content"] == '{"seats": 3}'
    assert applied["id"] == "call-1"


def test_truthful_tool_result_without_a_resolver_refuses_to_guess():
    with pytest.raises(UnresolvedInterventionError, match="truth"):
        TruthfulToolResult(step=FORK_STEP).apply(step_of("tool"), tool_payload())


def test_truthful_tool_results_hash_does_not_depend_on_the_resolver():
    plain = TruthfulToolResult(step=FORK_STEP)

    assert plain.with_truth(lambda _step: {}).intervention_hash == plain.intervention_hash
