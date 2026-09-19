"""Strict parsing of the judge's JSON, with every rejection named."""

from __future__ import annotations

import json

import pytest
from agent_bisect.attribution.judge_parse import (
    JudgeParseError,
    extract_json_object,
    parse_all_at_once,
    parse_step_by_step,
)

VALID = frozenset({0, 1, 2, 3, 4})


def _answer(**overrides) -> str:
    payload = {
        "decisive_step": 2,
        "actor": "tool",
        "reason": "the lookup returned the wrong reservation",
        "ranking": [
            {"step": 2, "confidence": 0.8, "reason": "wrong value"},
            {"step": 3, "confidence": 0.3, "reason": "acted on it"},
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


# ---- extract_json_object ----


def test_reads_a_bare_json_object():
    # Arrange / Act
    result = extract_json_object('{"a": 1}')

    # Assert
    assert result == {"a": 1}


def test_reads_a_fenced_json_object():
    # Arrange / Act
    result = extract_json_object('```json\n{"a": 1}\n```')

    # Assert
    assert result == {"a": 1}


def test_reads_an_object_wrapped_in_prose():
    # Arrange / Act
    result = extract_json_object('Here is my answer:\n{"a": 1}\nHope that helps.')

    # Assert
    assert result == {"a": 1}


def test_is_not_confused_by_braces_inside_a_string():
    # Arrange / Act
    result = extract_json_object('{"a": "a } brace", "b": 2}')

    # Assert
    assert result == {"a": "a } brace", "b": 2}


def test_rejects_text_with_no_object_at_all():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="no JSON object"):
        extract_json_object("I could not decide.")


def test_rejects_a_malformed_object():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError):
        extract_json_object('{"a": }')


def test_rejects_a_json_array():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="no JSON object"):
        extract_json_object("[1, 2, 3]")


# ---- parse_all_at_once ----


def test_accepts_a_well_formed_answer():
    # Arrange / Act
    answer = parse_all_at_once(_answer(), valid_steps=VALID, limit=10)

    # Assert
    assert answer.decisive_step == 2
    assert [entry.step for entry in answer.ranking] == [2, 3]
    assert [entry.rank for entry in answer.ranking] == [1, 2]


def test_rejects_a_missing_decisive_step():
    # Arrange
    payload = json.loads(_answer())
    del payload["decisive_step"]

    # Act / Assert
    with pytest.raises(JudgeParseError, match="decisive_step"):
        parse_all_at_once(json.dumps(payload), valid_steps=VALID, limit=10)


def test_rejects_a_decisive_step_that_is_not_in_the_trajectory():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="99"):
        parse_all_at_once(
            _answer(decisive_step=99, ranking=[{"step": 99, "confidence": 0.9, "reason": "x"}]),
            valid_steps=VALID,
            limit=10,
        )


def test_rejects_a_non_integer_step():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="decisive_step"):
        parse_all_at_once(_answer(decisive_step="two"), valid_steps=VALID, limit=10)


def test_rejects_an_empty_ranking():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="ranking"):
        parse_all_at_once(_answer(ranking=[]), valid_steps=VALID, limit=10)


def test_rejects_a_ranking_whose_first_entry_is_not_the_decisive_step():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="ranking\\[0\\]"):
        parse_all_at_once(
            _answer(ranking=[{"step": 3, "confidence": 0.9, "reason": "x"}]),
            valid_steps=VALID,
            limit=10,
        )


def test_rejects_a_repeated_step_in_the_ranking():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="twice"):
        parse_all_at_once(
            _answer(
                ranking=[
                    {"step": 2, "confidence": 0.9, "reason": "x"},
                    {"step": 2, "confidence": 0.5, "reason": "y"},
                ]
            ),
            valid_steps=VALID,
            limit=10,
        )


def test_rejects_a_confidence_outside_zero_to_one():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="confidence"):
        parse_all_at_once(
            _answer(ranking=[{"step": 2, "confidence": 4.0, "reason": "x"}]),
            valid_steps=VALID,
            limit=10,
        )


def test_keeps_only_the_first_limit_entries_of_a_long_ranking():
    # Arrange
    ranking = [{"step": 2, "confidence": 0.9, "reason": "x"}] + [
        {"step": step, "confidence": 0.1, "reason": "y"} for step in (0, 1, 3, 4)
    ]

    # Act
    answer = parse_all_at_once(_answer(ranking=ranking), valid_steps=VALID, limit=3)

    # Assert
    assert [entry.step for entry in answer.ranking] == [2, 0, 1]


# ---- parse_step_by_step ----


def test_accepts_a_yes_verdict():
    # Arrange / Act
    verdict = parse_step_by_step(
        '{"error_here": true, "confidence": 0.7, "reason": "wrong id"}'
    )

    # Assert
    assert verdict.error_here is True
    assert verdict.confidence == 0.7


def test_accepts_a_no_verdict():
    # Arrange / Act
    verdict = parse_step_by_step('{"error_here": false, "confidence": 0.9, "reason": "fine"}')

    # Assert
    assert verdict.error_here is False


def test_rejects_a_missing_error_here():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="error_here"):
        parse_step_by_step('{"confidence": 0.9, "reason": "fine"}')


def test_rejects_a_non_boolean_error_here():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="error_here"):
        parse_step_by_step('{"error_here": "yes", "confidence": 0.9, "reason": "x"}')


def test_rejects_a_step_confidence_outside_zero_to_one():
    # Arrange / Act / Assert
    with pytest.raises(JudgeParseError, match="confidence"):
        parse_step_by_step('{"error_here": true, "confidence": -1, "reason": "x"}')


# ---- reasoning models: the answer is at the END, after the thinking ----


def test_takes_the_last_object_when_the_thinking_contains_braces():
    # Arrange: a reasoning model narrates, brace-laden, then answers
    text = (
        'We need a JSON object like {"decisive_step": N}. Let me think.\n'
        'Step 3 looks wrong, or maybe {"step": 4}.\n'
        'Final answer:\n{"decisive_step": 4, "ranking": []}'
    )

    # Act
    result = extract_json_object(text)

    # Assert
    assert result == {"decisive_step": 4, "ranking": []}


def test_falls_back_to_an_earlier_object_when_the_last_one_is_truncated():
    # Arrange: the answer came first and the model kept talking into a cut-off
    text = '{"decisive_step": 2, "ranking": []}\nAlso consider {"step": 3'

    # Act
    result = extract_json_object(text)

    # Assert
    assert result == {"decisive_step": 2, "ranking": []}


def test_thinking_with_no_answer_at_all_is_still_rejected():
    # Arrange: what a truncated reasoning model actually produced
    text = "We have a conversation where the user wants... the decisive error step is step 4"

    # Act / Assert
    with pytest.raises(JudgeParseError, match="no JSON object"):
        extract_json_object(text)
