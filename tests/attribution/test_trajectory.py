"""Turning a recorded run into the judge's view of it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agent_bisect.attribution.trajectory import (
    MISSING_PAYLOAD,
    build_judge_input,
    tool_steps_of,
)
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import RunManifest, Step, TapeReader, TapeWriter


class Tape:
    def __init__(self, root):
        self.blobs = BlobStore(root)
        self.writer = TapeWriter(root)
        self.reader = TapeReader(root)


def _manifest(run_id: str = "run-1") -> RunManifest:
    return RunManifest(
        run_id=run_id,
        domain="airline",
        task_id="0",
        agent_model="m",
        user_model="u",
        tau2_commit="abc",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )


def _llm_payload(content: str | None, tool_calls=None) -> dict:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"index": 0, "finish_reason": "stop", "message": message}]}


def _built(tmp_path, steps_spec) -> tuple[Tape, object]:
    tape = Tape(tmp_path / "runs")
    tape.writer.start_run(_manifest())
    blank = tape.blobs.put_json({})
    for idx, (actor, payload, tool_name) in enumerate(steps_spec):
        ref = tape.blobs.put_json(payload) if payload is not None else None
        tape.writer.append_step(
            Step(
                run_id="run-1",
                step_idx=idx,
                actor=actor,
                tool_name=tool_name,
                tool_args={"id": "ABC"} if tool_name else None,
                response_ref=ref if actor != "tool" else None,
                tool_result_ref=ref if actor == "tool" else None,
                state_before=blank,
                state_after=blank,
                state_hash="h",
            )
        )
    return tape, None


def test_reads_the_agent_text_of_an_llm_step(tmp_path):
    # Arrange
    tape, _ = _built(tmp_path, [("agent", _llm_payload("let me look that up"), None)])

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert "let me look that up" in judge_input.steps[0].content


def test_shows_the_tool_calls_an_agent_turn_issued(tmp_path):
    # Arrange
    payload = _llm_payload(
        None,
        [{"id": "c1", "type": "function",
          "function": {"name": "get_reservation", "arguments": '{"id": "ABC"}'}}],
    )
    tape, _ = _built(tmp_path, [("agent", payload, None)])

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert "get_reservation" in judge_input.steps[0].content


def test_reads_the_result_of_a_tool_step(tmp_path):
    # Arrange
    tape, _ = _built(
        tmp_path,
        [("tool", {"role": "tool", "content": "reservation ZFA04Y", "error": False},
          "get_reservation")],
    )

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert "reservation ZFA04Y" in judge_input.steps[0].content
    assert judge_input.steps[0].tool_name == "get_reservation"


def test_marks_a_tool_step_that_returned_an_error(tmp_path):
    # Arrange
    tape, _ = _built(
        tmp_path,
        [("tool", {"role": "tool", "content": "not found", "error": True}, "get_reservation")],
    )

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert "error" in judge_input.steps[0].content.lower()


def test_the_evaluator_step_is_left_out_of_the_judges_view(tmp_path):
    # Arrange: the evaluator's verdict is grading information the agent never had
    tape, _ = _built(
        tmp_path,
        [
            ("agent", _llm_payload("hello"), None),
            ("evaluator", _llm_payload('{"results": [false]}'), None),
        ],
    )

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert [step.step_idx for step in judge_input.steps] == [0]


def test_step_indices_are_the_tapes_own(tmp_path):
    # Arrange
    tape, _ = _built(
        tmp_path,
        [
            ("agent", _llm_payload("a"), None),
            ("evaluator", _llm_payload("e"), None),
            ("tool", {"role": "tool", "content": "t"}, "get_reservation"),
        ],
    )

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert: step 2 keeps index 2 although step 1 was dropped from the view
    assert [step.step_idx for step in judge_input.steps] == [0, 2]


def test_a_step_with_no_recorded_payload_says_so_instead_of_crashing(tmp_path):
    # Arrange
    tape, _ = _built(tmp_path, [("agent", None, None)])

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert judge_input.steps[0].content == MISSING_PAYLOAD


def test_a_run_with_no_candidate_step_is_refused(tmp_path):
    # Arrange
    tape, _ = _built(tmp_path, [("evaluator", _llm_payload("e"), None)])

    # Act / Assert
    with pytest.raises(ValueError, match="no candidate"):
        build_judge_input(
            "run-1", reader=tape.reader, store=tape.blobs,
            item_id="i", task_description="t", policy="p",
        )


def test_tool_steps_of_names_only_the_tool_steps(tmp_path):
    # Arrange
    tape, _ = _built(
        tmp_path,
        [
            ("agent", _llm_payload("a"), None),
            ("tool", {"role": "tool", "content": "t"}, "get_reservation"),
            ("user", _llm_payload("u"), None),
        ],
    )

    # Act
    steps = tool_steps_of(tape.reader.get_steps("run-1"))

    # Assert
    assert steps == (1,)


# ---- gaps in the recording are facts, not crashes ----


def test_an_unreadable_payload_blob_renders_as_missing(tmp_path):
    # Arrange: a step pointing at a blob that is not there
    tape, _ = _built(tmp_path, [("agent", _llm_payload("hello"), None)])

    class Broken:
        def get_json(self, ref):
            raise OSError("blob gone")

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=Broken(),  # type: ignore[arg-type]
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert judge_input.steps[0].content == MISSING_PAYLOAD


def test_a_response_with_no_choices_renders_as_missing(tmp_path):
    # Arrange
    tape, _ = _built(tmp_path, [("agent", {"choices": []}, None)])

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert judge_input.steps[0].content == MISSING_PAYLOAD


def test_a_tool_result_with_no_content_field_is_rendered_whole(tmp_path):
    # Arrange
    tape, _ = _built(tmp_path, [("tool", {"role": "tool", "data": [1, 2]}, "get_x")])

    # Act
    judge_input = build_judge_input(
        "run-1", reader=tape.reader, store=tape.blobs,
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert "data" in judge_input.steps[0].content


def test_an_unreadable_manifest_leaves_the_domain_blank_rather_than_failing(tmp_path):
    # Arrange
    tape, _ = _built(tmp_path, [("agent", _llm_payload("hi"), None)])

    class NoManifest:
        def get_steps(self, run_id):
            return tape.reader.get_steps(run_id)

        def get_manifest(self, run_id):
            raise RuntimeError("index unreadable")

    # Act
    judge_input = build_judge_input(
        "run-1", reader=NoManifest(), store=tape.blobs,  # type: ignore[arg-type]
        item_id="i", task_description="t", policy="p",
    )

    # Assert
    assert judge_input.domain == ""
