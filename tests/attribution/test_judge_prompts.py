"""The judge's view of a trajectory: deterministic truncation that never drops a step."""

from __future__ import annotations

import pytest
from agent_bisect.attribution.judge_prompts import (
    ELISION_TEMPLATE,
    MIN_CHARS_PER_STEP,
    TruncationPolicy,
    build_all_at_once_prompt,
    build_step_by_step_prompt,
    render_trajectory,
    truncate,
)
from agent_bisect.attribution.judge_view import JudgeInput, JudgeStepView


def _view(step_idx: int, actor: str = "tool", content: str = "ok") -> JudgeStepView:
    return JudgeStepView(
        step_idx=step_idx,
        actor=actor,  # type: ignore[arg-type]
        tool_name="get_reservation" if actor == "tool" else None,
        tool_args={"id": "ABC123"} if actor == "tool" else None,
        content=content,
    )


def _input(steps: tuple[JudgeStepView, ...]) -> JudgeInput:
    return JudgeInput(
        item_id="item-1",
        run_id="run-1",
        domain="airline",
        task_description="Change the passenger's flight.",
        policy="Never cancel without confirmation.",
        steps=steps,
    )


# ---- truncate ----


def test_leaves_a_short_payload_exactly_as_it_is():
    # Arrange
    policy = TruncationPolicy(max_chars_per_step=100)

    # Act
    result = truncate("a short tool result", policy)

    # Assert
    assert result == "a short tool result"


def test_keeps_the_head_and_the_tail_of_a_long_payload():
    # Arrange
    policy = TruncationPolicy(max_chars_per_step=40, head_fraction=0.5)
    text = "H" * 500 + "T" * 500

    # Act
    result = truncate(text, policy)

    # Assert
    assert result.startswith("H" * 20)
    assert result.endswith("T" * 20)


def test_says_how_many_characters_it_removed():
    # Arrange
    policy = TruncationPolicy(max_chars_per_step=40)
    text = "x" * 1000

    # Act
    result = truncate(text, policy)

    # Assert
    assert ELISION_TEMPLATE.format(elided=960) in result


def test_truncation_is_deterministic_for_the_same_input():
    # Arrange
    policy = TruncationPolicy(max_chars_per_step=64)
    text = "payload " * 200

    # Act
    first, second = truncate(text, policy), truncate(text, policy)

    # Assert
    assert first == second


def test_redacts_a_key_shaped_string_before_the_judge_ever_sees_it():
    # Arrange: assembled at runtime so the literal never sits in the repo,
    # where the pre-commit secret scanner would (correctly) reject it.
    policy = TruncationPolicy(max_chars_per_step=500)
    key_shaped = "nv" + "api-" + "0123456789abcdef" * 3

    # Act
    result = truncate(f"token {key_shaped}", policy)

    # Assert
    assert key_shaped not in result


# ---- render_trajectory ----


def test_renders_every_step_with_its_tape_step_index():
    # Arrange
    steps = tuple(_view(idx) for idx in (0, 1, 2, 7))

    # Act
    rendered = render_trajectory(steps, TruncationPolicy())

    # Assert
    for idx in (0, 1, 2, 7):
        assert f"[step {idx}]" in rendered


def test_never_drops_a_step_however_small_the_total_budget():
    # Arrange: 40 fat steps against a budget far below their combined size
    steps = tuple(_view(idx, content="payload " * 400) for idx in range(40))
    policy = TruncationPolicy(max_chars_per_step=4000, max_total_chars=1000)

    # Act
    rendered = render_trajectory(steps, policy)

    # Assert
    for idx in range(40):
        assert f"[step {idx}]" in rendered


def test_shrinks_the_per_step_budget_uniformly_to_fit_the_total():
    # Arrange
    steps = tuple(_view(idx, content="payload " * 400) for idx in range(20))
    generous = TruncationPolicy(max_chars_per_step=4000, max_total_chars=1_000_000)
    tight = TruncationPolicy(max_chars_per_step=4000, max_total_chars=8_000)

    # Act
    long_render = render_trajectory(steps, generous)
    short_render = render_trajectory(steps, tight)

    # Assert
    assert len(short_render) < len(long_render)


def test_stops_shrinking_at_the_floor_rather_than_dropping_content():
    # Arrange: an impossible budget -- 200 steps into 100 characters
    steps = tuple(_view(idx, content="payload " * 100) for idx in range(200))
    policy = TruncationPolicy(max_chars_per_step=4000, max_total_chars=100)

    # Act
    rendered = render_trajectory(steps, policy)

    # Assert
    assert len(rendered) > 200 * MIN_CHARS_PER_STEP
    assert "[step 199]" in rendered


def test_names_the_actor_and_the_tool_of_each_step():
    # Arrange
    steps = (_view(0, actor="agent", content="I will look it up"), _view(1, actor="tool"))

    # Act
    rendered = render_trajectory(steps, TruncationPolicy())

    # Assert
    assert "agent" in rendered
    assert "get_reservation" in rendered


# ---- prompts ----


def test_all_at_once_prompt_carries_the_task_the_policy_and_every_step():
    # Arrange
    judge_input = _input(tuple(_view(idx) for idx in range(4)))

    # Act
    system, user = build_all_at_once_prompt(judge_input, TruncationPolicy())

    # Assert
    assert "Change the passenger's flight." in user
    assert "Never cancel without confirmation." in user
    assert all(f"[step {idx}]" in user for idx in range(4))
    assert "JSON" in system


def test_all_at_once_prompt_never_mentions_a_label_or_a_ground_truth():
    # Arrange
    judge_input = _input(tuple(_view(idx) for idx in range(3)))

    # Act
    system, user = build_all_at_once_prompt(judge_input, TruncationPolicy())

    # Assert
    forbidden = ("planted", "ground truth", "oracle", "label", "injected")
    assert not any(word in (system + user).lower() for word in forbidden)


def test_step_by_step_prompt_shows_the_prefix_and_asks_about_one_step():
    # Arrange
    judge_input = _input(tuple(_view(idx) for idx in range(6)))

    # Act
    _, user = build_step_by_step_prompt(judge_input, step_idx=3, policy=TruncationPolicy())

    # Assert
    assert "[step 3]" in user
    assert "[step 4]" not in user, "the judge must not see steps it has not reached yet"


def test_step_by_step_prompt_rejects_a_step_outside_the_trajectory():
    # Arrange
    judge_input = _input(tuple(_view(idx) for idx in range(3)))

    # Act / Assert
    with pytest.raises(ValueError, match="step 9"):
        build_step_by_step_prompt(judge_input, step_idx=9, policy=TruncationPolicy())


def test_the_two_prompts_are_byte_stable_across_calls():
    # Arrange
    judge_input = _input(tuple(_view(idx) for idx in range(5)))

    # Act
    first = build_all_at_once_prompt(judge_input, TruncationPolicy())
    second = build_all_at_once_prompt(judge_input, TruncationPolicy())

    # Assert
    assert first == second
