"""Judge calls are recorded before use and never paid for twice."""

from __future__ import annotations

import pytest
from agent_bisect.attribution.judge_store import (
    JudgeCallStore,
    LedgeredJudgeBackend,
    call_key,
)
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.llm import LLMClient, LLMRequest, LLMResponse

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


class FakeTransport:
    """Answers with a canned string and counts how often it was asked."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def complete(self, request: LLMRequest, *, api_base: str, api_key: str) -> LLMResponse:
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else "{}"
        return LLMResponse(content=reply, tokens_in=10, tokens_out=5)


def _backend(tmp_path, replies: list[str]) -> tuple[LedgeredJudgeBackend, FakeTransport]:
    transport = FakeTransport(replies)
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")
    store = JudgeCallStore(tmp_path / "runs")

    def make_client(record_before_use):
        return LLMClient(
            transport,
            ledger,
            api_base="https://example.invalid/v1",
            api_key="unused",
            record_before_use=record_before_use,
        )

    return LedgeredJudgeBackend(make_client=make_client, store=store, model=MODEL), transport


# ---- call_key ----


def test_the_same_prompt_and_model_give_the_same_key():
    # Arrange / Act
    first = call_key(model=MODEL, system="s", user="u")
    second = call_key(model=MODEL, system="s", user="u")

    # Assert
    assert first == second


def test_a_different_prompt_gives_a_different_key():
    # Arrange / Act
    first = call_key(model=MODEL, system="s", user="u")
    second = call_key(model=MODEL, system="s", user="u2")

    # Assert
    assert first != second


def test_a_different_model_gives_a_different_key():
    # Arrange / Act / Assert
    assert call_key(model=MODEL, system="s", user="u") != call_key(
        model="other", system="s", user="u"
    )


# ---- store ----


def test_an_unknown_key_looks_up_as_none(tmp_path):
    # Arrange
    store = JudgeCallStore(tmp_path / "runs")

    # Act / Assert
    assert store.lookup("nope") is None


def test_a_recorded_call_is_readable_back(tmp_path):
    # Arrange
    store = JudgeCallStore(tmp_path / "runs")

    # Act
    store.record(
        key="k1",
        item_id="item-1",
        protocol="all_at_once",
        model=MODEL,
        request={"messages": []},
        response_text='{"decisive_step": 3}',
    )

    # Assert
    assert store.lookup("k1") == '{"decisive_step": 3}'


def test_recording_the_same_key_twice_keeps_the_first_answer(tmp_path):
    # Arrange
    store = JudgeCallStore(tmp_path / "runs")
    store.record(
        key="k1", item_id="i", protocol="all_at_once", model=MODEL,
        request={}, response_text="first",
    )

    # Act
    store.record(
        key="k1", item_id="i", protocol="all_at_once", model=MODEL,
        request={}, response_text="second",
    )

    # Assert
    assert store.lookup("k1") == "first"


def test_a_stored_call_survives_a_new_store_over_the_same_directory(tmp_path):
    # Arrange
    JudgeCallStore(tmp_path / "runs").record(
        key="k1", item_id="i", protocol="all_at_once", model=MODEL,
        request={}, response_text="kept",
    )

    # Act
    reopened = JudgeCallStore(tmp_path / "runs")

    # Assert
    assert reopened.lookup("k1") == "kept"


# ---- backend ----


def test_asking_the_backend_calls_the_model_once(tmp_path):
    # Arrange
    backend, transport = _backend(tmp_path, ["answer"])

    # Act
    result = backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Assert
    assert result.content == "answer"
    assert transport.calls == 1


def test_asking_the_same_question_again_is_served_from_the_store(tmp_path):
    # Arrange
    backend, transport = _backend(tmp_path, ["answer"])
    backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Act
    again = backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Assert
    assert again.content == "answer"
    assert again.paid is False
    assert transport.calls == 1, "a judged item must never be paid for twice"


def test_a_resumed_process_reuses_the_answer_the_previous_one_paid_for(tmp_path):
    # Arrange
    first, transport = _backend(tmp_path, ["answer"])
    first.ask(system="s", user="u", item_id="i", protocol="all_at_once")
    resumed, resumed_transport = _backend(tmp_path, ["different"])

    # Act
    result = resumed.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Assert
    assert result.content == "answer"
    assert resumed_transport.calls == 0


def test_the_answer_is_recorded_before_the_caller_can_act_on_it(tmp_path):
    # Arrange
    backend, _ = _backend(tmp_path, ["answer"])

    # Act
    backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Assert: the store already held it by the time `ask` returned
    key = call_key(model=MODEL, system="s", user="u")
    assert backend.store.lookup(key) == "answer"


def test_every_judge_call_is_ledgered_under_the_judge_purpose(tmp_path):
    # Arrange
    backend, _ = _backend(tmp_path, ["answer"])
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")

    # Act
    backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Assert
    assert ledger.total_calls() == 1
    with ledger._connect() as conn:  # noqa: SLF001 - the ledger has no purpose reader
        purposes = [row[0] for row in conn.execute("SELECT purpose FROM calls")]
    assert purposes == ["judge"]


def test_a_cached_answer_costs_no_ledger_row(tmp_path):
    # Arrange
    backend, _ = _backend(tmp_path, ["answer"])
    backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")

    # Act
    backend.ask(system="s", user="u", item_id="i", protocol="all_at_once")

    # Assert
    assert ledger.total_calls() == 1


def test_the_backend_refuses_an_empty_prompt(tmp_path):
    # Arrange
    backend, _ = _backend(tmp_path, ["answer"])

    # Act / Assert
    with pytest.raises(ValueError, match="empty"):
        backend.ask(system="s", user="", item_id="i", protocol="all_at_once")
