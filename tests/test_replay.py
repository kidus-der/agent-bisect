"""Tests for agent_bisect.core.replay: the shared tape cursor, TapeLLM,
TapeTools, the divergence report, and the Intervention protocol.

Everything here is domain-free: `core/` never imports tau2, so these
exercise the engine against hand-built `Step` rows and a dict-backed blob
loader.
"""

from __future__ import annotations

from typing import Any

import pytest
from agent_bisect.core.replay import (
    LIVE,
    DivergenceError,
    NoOpIntervention,
    TapeCursor,
    TapeExhaustedError,
    TapeLLM,
    TapeTools,
    short_request_diff,
)
from agent_bisect.core.tape import Step, canonical_request_hash


class _Blobs:
    """A dict-backed stand-in for `BlobStore.get_json`."""

    def __init__(self) -> None:
        self._by_digest: dict[str, Any] = {}

    def put(self, digest: str, payload: Any) -> str:
        self._by_digest[digest] = payload
        return digest

    def get_json(self, digest: str) -> Any:
        return self._by_digest[digest]


def _request(content: str = "hello", **extra: Any) -> dict[str, Any]:
    return {
        "model": "agent-model",
        "messages": [{"role": "user", "content": content}],
        "tools": [{"name": "get_user_details"}],
        "temperature": 0.0,
        **extra,
    }


def _llm_step(step_idx: int, *, actor: str = "agent", request: dict | None = None) -> Step:
    request = request if request is not None else _request()
    return Step(
        run_id="run-1",
        step_idx=step_idx,
        actor=actor,  # pyright: ignore[reportArgumentType]
        request_hash=canonical_request_hash(request),
        request_ref=f"req-{step_idx}",
        response_ref=f"resp-{step_idx}",
        state_before=f"s-{step_idx}",
        state_after=f"s-{step_idx}",
        state_hash="h" * 64,
        state_hash_before="h" * 64,
    )


def _tool_step(
    step_idx: int,
    *,
    tool_name: str = "get_user_details",
    tool_args: dict | None = None,
    state_hash: str = "after",
) -> Step:
    return Step(
        run_id="run-1",
        step_idx=step_idx,
        actor="tool",
        tool_name=tool_name,
        tool_args=tool_args if tool_args is not None else {"user_id": "mia_li_3668"},
        tool_result_ref=f"tool-{step_idx}",
        state_before=f"sb-{step_idx}",
        state_after=f"sa-{step_idx}",
        state_hash=state_hash,
        state_hash_before="before",
    )


# ---- TapeCursor ----


def test_cursor_takes_steps_in_recorded_order():
    steps = [_llm_step(0), _tool_step(1), _llm_step(2)]
    cursor = TapeCursor(steps)

    assert [cursor.take({"agent"}).step_idx, cursor.take({"tool"}).step_idx] == [0, 1]
    assert cursor.position == 2


def test_cursor_reports_an_actor_mismatch_as_divergence():
    cursor = TapeCursor([_llm_step(0), _tool_step(1)])
    cursor.take({"agent"})

    with pytest.raises(DivergenceError) as excinfo:
        cursor.take({"agent", "user"})

    assert excinfo.value.step_idx == 1
    assert "tool" in str(excinfo.value)


def test_cursor_raises_when_the_tape_runs_out():
    cursor = TapeCursor([_llm_step(0)])
    cursor.take({"agent"})

    with pytest.raises(TapeExhaustedError) as excinfo:
        cursor.take({"agent"})

    assert excinfo.value.step_idx == 1


def test_tape_exhausted_is_a_divergence_error():
    assert issubclass(TapeExhaustedError, DivergenceError)


def test_cursor_knows_when_every_step_has_been_consumed():
    cursor = TapeCursor([_llm_step(0)])

    assert not cursor.at_end
    cursor.take({"agent"})
    assert cursor.at_end
    assert cursor.remaining == 0


# ---- TapeLLM ----


def test_tape_llm_serves_the_recorded_response_for_a_matching_request():
    blobs = _Blobs()
    blobs.put("resp-0", {"choices": [{"message": {"content": "recorded"}}]})
    llm = TapeLLM(TapeCursor([_llm_step(0)]), blobs.get_json)

    response = llm.serve(_request())

    assert response == {"choices": [{"message": {"content": "recorded"}}]}
    assert llm.calls_served == 1


def test_tape_llm_serves_agent_and_user_and_evaluator_steps():
    blobs = _Blobs()
    for idx in range(3):
        blobs.put(f"resp-{idx}", {"i": idx})
    steps = [
        _llm_step(0, actor="agent"),
        _llm_step(1, actor="user"),
        _llm_step(2, actor="evaluator"),
    ]
    llm = TapeLLM(TapeCursor(steps), blobs.get_json)

    assert [llm.serve(_request())["i"] for _ in range(3)] == [0, 1, 2]


def _llm_with_recorded_request(request: dict[str, Any]) -> TapeLLM:
    """A one-step TapeLLM whose recorded request blob is readable, so the
    divergence report can be built from it."""
    blobs = _Blobs()
    blobs.put("req-0", request)
    blobs.put("resp-0", {"ok": True})
    return TapeLLM(TapeCursor([_llm_step(0, request=request)]), blobs.get_json)


def test_tape_llm_raises_divergence_on_a_one_character_message_change():
    llm = _llm_with_recorded_request(_request())

    with pytest.raises(DivergenceError) as excinfo:
        llm.serve(_request(content="hellp"))

    error = excinfo.value
    assert error.step_idx == 0
    assert error.actor == "agent"
    assert error.expected != error.got
    assert "messages" in error.diff


def test_tape_llm_raises_divergence_on_a_changed_tool_schema():
    llm = _llm_with_recorded_request(_request())

    with pytest.raises(DivergenceError) as excinfo:
        llm.serve(_request(tools=[{"name": "get_user_details", "extra": 1}]))

    assert "tools" in excinfo.value.diff


def test_tape_llm_raises_divergence_on_a_changed_sampling_param():
    llm = _llm_with_recorded_request(_request())

    with pytest.raises(DivergenceError) as excinfo:
        llm.serve(_request(temperature=1.0))

    assert "temperature" in excinfo.value.diff


def test_tape_llm_still_reports_divergence_when_the_request_blob_is_unreadable():
    blobs = _Blobs()
    blobs.put("resp-0", {"ok": True})
    llm = TapeLLM(TapeCursor([_llm_step(0)]), blobs.get_json)

    with pytest.raises(DivergenceError) as excinfo:
        llm.serve(_request(content="changed"))

    assert excinfo.value.step_idx == 0
    assert "unavailable" in excinfo.value.diff


def test_tape_llm_ignores_volatile_fields():
    """api_base/timeout/metadata are not part of what was sampled."""
    blobs = _Blobs()
    blobs.put("resp-0", {"ok": True})
    llm = TapeLLM(TapeCursor([_llm_step(0)]), blobs.get_json)

    served = llm.serve(
        _request(api_base="https://elsewhere.example", timeout=99, metadata={"trace": "x"})
    )

    assert served == {"ok": True}


def test_tape_llm_never_falls_back_to_a_live_call():
    """There is no escape hatch: the only outcome of a mismatch is the error."""
    blobs = _Blobs()
    llm = TapeLLM(TapeCursor([]), blobs.get_json)

    with pytest.raises(TapeExhaustedError):
        llm.serve(_request())

    assert llm.calls_served == 0


# ---- TapeTools ----


def test_tape_tools_takes_the_matching_tool_step():
    blobs = _Blobs()
    blobs.put("tool-0", {"content": "recorded result"})
    tools = TapeTools(TapeCursor([_tool_step(0)]), blobs.get_json)

    step = tools.take("get_user_details", {"user_id": "mia_li_3668"})

    assert tools.recorded_result(step) == {"content": "recorded result"}


def test_tape_tools_raises_divergence_on_a_different_tool_name():
    tools = TapeTools(TapeCursor([_tool_step(0)]), _Blobs().get_json)

    with pytest.raises(DivergenceError) as excinfo:
        tools.take("book_reservation", {"user_id": "mia_li_3668"})

    assert "tool_name" in excinfo.value.diff


def test_tape_tools_raises_divergence_on_different_tool_args():
    tools = TapeTools(TapeCursor([_tool_step(0)]), _Blobs().get_json)

    with pytest.raises(DivergenceError) as excinfo:
        tools.take("get_user_details", {"user_id": "someone_else"})

    assert "tool_args" in excinfo.value.diff


def test_tape_tools_accepts_a_faithful_re_execution():
    blobs = _Blobs()
    blobs.put("tool-0", {"content": "recorded result"})
    tools = TapeTools(TapeCursor([_tool_step(0)]), blobs.get_json)
    step = tools.take("get_user_details", {"user_id": "mia_li_3668"})

    tools.check_reexecution(step, {"content": "recorded result"}, "after")


def test_tape_tools_raises_when_a_re_executed_tool_returns_something_else():
    blobs = _Blobs()
    blobs.put("tool-0", {"content": "recorded result"})
    tools = TapeTools(TapeCursor([_tool_step(0)]), blobs.get_json)
    step = tools.take("get_user_details", {"user_id": "mia_li_3668"})

    with pytest.raises(DivergenceError) as excinfo:
        tools.check_reexecution(step, {"content": "drifted"}, "after")

    assert "tool_result" in excinfo.value.diff


def test_tape_tools_raises_when_a_re_executed_tool_leaves_a_different_state():
    blobs = _Blobs()
    blobs.put("tool-0", {"content": "recorded result"})
    tools = TapeTools(TapeCursor([_tool_step(0)]), blobs.get_json)
    step = tools.take("get_user_details", {"user_id": "mia_li_3668"})

    with pytest.raises(DivergenceError) as excinfo:
        tools.check_reexecution(step, {"content": "recorded result"}, "elsewhere")

    assert "state_hash" in excinfo.value.diff


def test_tape_tools_exposes_the_recorded_state_to_restore():
    blobs = _Blobs()
    blobs.put("sa-0", {"db": "after"})
    tools = TapeTools(TapeCursor([_tool_step(0)]), blobs.get_json)
    step = tools.take("get_user_details", {"user_id": "mia_li_3668"})

    assert tools.recorded_state_after(step) == {"db": "after"}


# ---- interventions ----


def test_noop_intervention_returns_the_payload_unchanged():
    payload = {"choices": [{"message": {"content": "recorded"}}]}
    step = _llm_step(0)

    assert NoOpIntervention().apply(step, payload) is payload


def test_noop_intervention_is_named():
    assert NoOpIntervention().name == "noop"


def test_live_sentinel_is_distinguishable_from_any_payload():
    assert LIVE is not None
    assert LIVE != {"choices": []}
    assert repr(LIVE) == "LIVE"


# ---- the divergence report ----


def test_short_request_diff_names_the_differing_message():
    diff = short_request_diff(
        {"model": "m", "messages": [{"role": "user", "content": "abc"}]},
        {"model": "m", "messages": [{"role": "user", "content": "abd"}]},
    )

    assert "messages[0]" in diff


def test_short_request_diff_names_a_changed_model():
    diff = short_request_diff({"model": "a", "messages": []}, {"model": "b", "messages": []})

    assert "model" in diff


def test_short_request_diff_reports_a_length_change():
    diff = short_request_diff(
        {"model": "m", "messages": [{"role": "user", "content": "a"}]},
        {"model": "m", "messages": []},
    )

    assert "messages" in diff and "1" in diff


def test_short_request_diff_redacts_key_material():
    key = "nvapi" + "-" + "Z" * 64
    diff = short_request_diff(
        {"model": "m", "messages": [{"role": "user", "content": "a"}]},
        {"model": "m", "messages": [{"role": "user", "content": f"Bearer {key}"}]},
    )

    assert key not in diff


def test_short_request_diff_truncates_long_values():
    diff = short_request_diff(
        {"model": "m", "messages": [{"role": "user", "content": "a" * 5000}]},
        {"model": "m", "messages": [{"role": "user", "content": "b" * 5000}]},
    )

    assert len(diff) < 1000


def test_short_request_diff_handles_a_missing_recorded_request():
    """The recorded request blob may be unreadable; the error must still report."""
    diff = short_request_diff(None, {"model": "m", "messages": []})

    assert "unavailable" in diff


def test_divergence_error_message_names_the_step_and_actor():
    error = DivergenceError(step_idx=7, actor="agent", expected="aaa", got="bbb", diff="d")

    assert "step 7" in str(error)
    assert "agent" in str(error)
