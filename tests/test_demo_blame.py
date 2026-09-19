"""`demo.blame`'s pure logic: the first-divergence heuristic, cost-free.

`blame_new_failure` itself (the confirmation half) is exercised end to end
by `scripts/gates/p7.py`'s self-test against a real tau2 orchestrator --
these tests cover only what can be checked against fake steps and a fake
blob store, with no recording at all.
"""

from __future__ import annotations

from typing import Any

from agent_bisect.core.tape import Actor
from demo.blame import (
    FIRST_DIVERGENCE_PROTOCOL,
    _decoded_content,
    _fingerprint,
    first_divergence_steps,
    first_divergence_verdict,
)


class FakeBlobStore:
    """A `BlobStore` stand-in: refs are dict keys, no filesystem at all."""

    def __init__(self, blobs: dict[str, object]) -> None:
        self._blobs = blobs

    def get_json(self, digest: str) -> object:
        return self._blobs[digest]


def _step(
    *,
    idx: int,
    actor: Actor,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    tool_result_ref: str | None = None,
    response_ref: str | None = None,
):
    from agent_bisect.core.tape import Step

    return Step(
        run_id="run",
        step_idx=idx,
        actor=actor,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result_ref=tool_result_ref,
        response_ref=response_ref,
        state_before="s0",
        state_after="s0",
        state_hash="h0",
    )


def test_decoded_content_extracts_message_content_and_tool_calls():
    store = FakeBlobStore(
        {"r1": {"choices": [{"message": {"content": "hi", "tool_calls": None}}]}}
    )

    text = _decoded_content(store, "r1")

    assert "hi" in text


def test_decoded_content_of_a_plain_payload_is_its_own_json():
    store = FakeBlobStore({"r1": {"task_id": "task_2", "status": "completed"}})

    text = _decoded_content(store, "r1")

    assert "task_2" in text


def test_decoded_content_of_a_missing_ref_is_empty():
    store = FakeBlobStore({})

    assert _decoded_content(store, None) == ""


def test_fingerprint_of_a_tool_step_uses_the_tool_result_ref():
    store = FakeBlobStore({"result-ref": {"content": "ok"}})
    step = _step(
        idx=0, actor="tool", tool_name="get_users", tool_args={}, tool_result_ref="result-ref"
    )

    actor, tool_name, tool_args, content = _fingerprint(store, step)

    assert (actor, tool_name, tool_args) == ("tool", "get_users", {})
    assert "ok" in content


def test_fingerprint_of_an_agent_step_uses_the_response_ref():
    store = FakeBlobStore({"resp-ref": {"choices": [{"message": {"content": "hello"}}]}})
    step = _step(idx=0, actor="agent", response_ref="resp-ref")

    _, _, _, content = _fingerprint(store, step)

    assert "hello" in content


def test_identical_trajectories_have_no_divergence():
    store = FakeBlobStore({"r": {"content": "same"}})
    steps = [
        _step(idx=0, actor="tool", tool_name="get_users", tool_args={}, tool_result_ref="r"),
        _step(idx=1, actor="agent", response_ref="r"),
    ]

    divergent = first_divergence_steps(
        head_store=store, base_store=store, base_steps=steps, head_steps=steps
    )

    assert divergent == ()


def test_a_differing_tool_result_is_the_divergence():
    base_store = FakeBlobStore({"r": {"content": "true"}})
    head_store = FakeBlobStore({"r": {"content": "faulted"}})
    step_kwargs: dict[str, Any] = {
        "idx": 0, "actor": "tool", "tool_name": "get_users",
        "tool_args": {}, "tool_result_ref": "r",
    }
    base_steps = [_step(**step_kwargs)]
    head_steps = [_step(**step_kwargs)]

    divergent = first_divergence_steps(
        head_store=head_store, base_store=base_store, base_steps=base_steps, head_steps=head_steps
    )

    assert divergent == (0,)


def test_divergence_is_capped_at_top_m():
    base_store = FakeBlobStore({f"r{i}": {"content": "base"} for i in range(5)})
    head_store = FakeBlobStore({f"r{i}": {"content": "head"} for i in range(5)})
    base_steps = [
        _step(idx=i, actor="tool", tool_name="t", tool_args={}, tool_result_ref=f"r{i}")
        for i in range(5)
    ]
    head_steps = [
        _step(idx=i, actor="tool", tool_name="t", tool_args={}, tool_result_ref=f"r{i}")
        for i in range(5)
    ]

    divergent = first_divergence_steps(
        head_store=head_store, base_store=base_store,
        base_steps=base_steps, head_steps=head_steps, top_m=2,
    )

    assert divergent == (0, 1)


def test_an_evaluator_step_is_never_reported_as_divergent():
    base_store = FakeBlobStore({"r": {"content": "true"}})
    head_store = FakeBlobStore({"r": {"content": "faulted"}})
    base_steps = [_step(idx=0, actor="evaluator", response_ref="r")]
    head_steps = [_step(idx=0, actor="evaluator", response_ref="r")]

    divergent = first_divergence_steps(
        head_store=head_store, base_store=base_store, base_steps=base_steps, head_steps=head_steps
    )

    assert divergent == ()


def test_head_running_longer_than_base_reports_the_extra_step():
    store = FakeBlobStore({"r": {"content": "same"}})
    base_steps = [_step(idx=0, actor="tool", tool_name="t", tool_args={}, tool_result_ref="r")]
    head_steps = [
        _step(idx=0, actor="tool", tool_name="t", tool_args={}, tool_result_ref="r"),
        _step(
            idx=1, actor="tool", tool_name="transfer_to_human_agents",
            tool_args={}, tool_result_ref="r",
        ),
    ]

    divergent = first_divergence_steps(
        head_store=store, base_store=store, base_steps=base_steps, head_steps=head_steps
    )

    assert divergent == (1,)


def test_verdict_is_parse_failed_when_nothing_diverges():
    store = FakeBlobStore({"r": {"content": "same"}})
    steps = [_step(idx=0, actor="tool", tool_name="t", tool_args={}, tool_result_ref="r")]

    verdict = first_divergence_verdict(
        item_id="item-1", head_store=store, base_store=store, base_steps=steps, head_steps=steps
    )

    assert verdict.parse_failed is True
    assert verdict.decisive_step is None
    assert verdict.ranking == ()


def test_verdict_names_the_first_divergence_as_decisive():
    base_store = FakeBlobStore({"r": {"content": "true"}})
    head_store = FakeBlobStore({"r": {"content": "faulted"}})
    steps = [_step(idx=0, actor="tool", tool_name="get_users", tool_args={}, tool_result_ref="r")]

    verdict = first_divergence_verdict(
        item_id="item-1", head_store=head_store, base_store=base_store,
        base_steps=steps, head_steps=steps,
    )

    assert verdict.decisive_step == 0
    assert verdict.protocol == FIRST_DIVERGENCE_PROTOCOL
    assert verdict.parse_failed is False
    assert verdict.shortlist(3) == (0,)


def test_a_step_index_mismatch_at_the_same_position_is_skipped_not_compared():
    """Defensive: base and head are walked by position (`zip`), and a
    step whose own index disagrees with its counterpart's is never
    fingerprinted -- comparing steps that are not actually the same step
    would not be a divergence finding, it would be noise."""
    store = FakeBlobStore({"r": {"content": "same"}})
    base_steps = [_step(idx=0, actor="tool", tool_name="t", tool_args={}, tool_result_ref="r")]
    head_steps = [_step(idx=1, actor="tool", tool_name="t", tool_args={}, tool_result_ref="r")]

    divergent = first_divergence_steps(
        head_store=store, base_store=store, base_steps=base_steps, head_steps=head_steps
    )

    assert divergent == ()
