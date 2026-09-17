"""Tests for the probe collector, its aggregation, and the three selection rules of 0004 §4."""

from __future__ import annotations

import pytest
from agent_bisect.adapters.tau2_llm import CallMeta
from agent_bisect.adapters.tau2_probe import (
    ProbeCollector,
    TaskProbeResult,
    choose_agent,
    choose_judge,
    summarise_probe,
    user_sim_is_usable,
)

KNOWN = {"get_reservation_details", "book_reservation"}


def _validate(name: str, arguments: dict) -> bool:
    return name in KNOWN and "reservation_id" in arguments


def _meta(purpose: str, latency_ms: float = 100.0, attempts: int = 1) -> CallMeta:
    return CallMeta(
        purpose=purpose, phase="P0", model="m", attempts=attempts, latency_ms=latency_ms
    )


class Msg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class Resp:
    def __init__(self, content="", tool_calls=None):
        self.choices = [type("C", (), {"message": Msg(content, tool_calls)})()]


def _tool_call(name: str, arguments: str):
    return {"function": {"name": name, "arguments": arguments}}


# ---- collector ----


def test_counts_agent_calls_and_leaves_user_calls_out_of_the_tool_ratio():
    collector = ProbeCollector(KNOWN, _validate)

    collector.record({}, Resp(tool_calls=[_tool_call("get_reservation_details",
                                                     '{"reservation_id": "A1"}')]), _meta("agent"))
    collector.record({}, Resp(content="I need a refund"), _meta("user"))

    assert collector.n_agent_calls == 1
    assert collector.n_user_calls == 1
    assert (collector.n_tool_calls, collector.n_invalid_tool_calls) == (1, 0)


def test_accumulates_invalid_reasons_across_calls():
    collector = ProbeCollector(KNOWN, _validate)

    collector.record({}, Resp(tool_calls=[_tool_call("teleport", "{}")]), _meta("agent"))
    collector.record({}, Resp(tool_calls=[_tool_call("book_reservation", "{oops")]), _meta("agent"))

    assert collector.n_invalid_tool_calls == 2
    assert collector.invalid_reasons == ("unknown_tool:teleport", "bad_json:book_reservation")


def test_counts_attempts_not_successful_calls_as_calls_used():
    """A retried 429 cost two requests; the budget must see both."""
    collector = ProbeCollector(KNOWN, _validate)

    collector.record({}, Resp(content="hi"), _meta("agent", attempts=3))

    assert collector.calls_used == 3


def test_tracks_empty_user_messages_for_the_user_sim_rule():
    collector = ProbeCollector(KNOWN, _validate)

    collector.record({}, Resp(content="   "), _meta("user"))
    collector.record({}, Resp(content="hello"), _meta("user"))

    assert collector.n_empty_user_messages == 1


def test_mean_agent_latency_ignores_user_calls():
    collector = ProbeCollector(KNOWN, _validate)

    collector.record({}, Resp(content="a"), _meta("agent", latency_ms=100.0))
    collector.record({}, Resp(content="b"), _meta("agent", latency_ms=300.0))
    collector.record({}, Resp(content="c"), _meta("user", latency_ms=9000.0))

    assert collector.mean_agent_latency_ms == pytest.approx(200.0)


def test_a_malformed_response_counts_as_an_invalid_call():
    collector = ProbeCollector(KNOWN, _validate)

    collector.record({}, object(), _meta("agent"))

    assert (collector.n_tool_calls, collector.n_invalid_tool_calls) == (1, 1)
    assert collector.invalid_reasons == ("unparseable_response",)


# ---- aggregation ----


def _result(task_id: str, *, passed: bool, tool_calls=4, invalid=0, steps=8, calls=10):
    return TaskProbeResult(
        model="m",
        task_id=task_id,
        reward=1.0 if passed else 0.0,
        passed=passed,
        n_steps=steps,
        n_agent_calls=calls,
        n_user_calls=calls,
        n_agent_tool_calls=tool_calls,
        n_invalid_tool_calls=invalid,
        invalid_reasons=(),
        termination_reason="agent_stop",
        calls_used=calls,
        wall_time_s=1.0,
        seed=1,
        mean_agent_latency_ms=120.0,
    )


def test_pass_rate_divides_by_the_task_count_that_was_asked_for():
    results = [_result(str(i), passed=i < 11) for i in range(20)]

    summary = summarise_probe("m", results, n_tasks=20)

    assert (summary.n_passed, summary.pass_rate) == (11, 0.55)


def test_valid_tool_call_rate_pools_over_all_tasks():
    results = [
        _result("0", passed=True, tool_calls=10, invalid=0),
        _result("1", passed=False, tool_calls=10, invalid=1),
    ]

    summary = summarise_probe("m", results, n_tasks=2)

    assert summary.valid_tool_call_rate == pytest.approx(0.95)


def test_valid_tool_call_rate_is_none_when_no_tool_call_was_ever_emitted():
    results = [_result("0", passed=False, tool_calls=0)]

    assert summarise_probe("m", results, n_tasks=1).valid_tool_call_rate is None


def test_summary_reports_a_wilson_interval_around_the_pass_rate():
    results = [_result(str(i), passed=i < 11) for i in range(20)]

    summary = summarise_probe("m", results, n_tasks=20)

    assert summary.ci_low < 0.55 < summary.ci_high
    assert summary.ci_low >= 0.0 and summary.ci_high <= 1.0


def test_summary_counts_termination_reasons():
    a = _result("0", passed=True)
    b = TaskProbeResult(**{**a.__dict__, "task_id": "1", "termination_reason": "max_steps"})

    counts = summarise_probe("m", [a, b], n_tasks=2).termination_counts

    assert counts == {"agent_stop": 1, "max_steps": 1}


def test_unfinished_tasks_still_count_in_the_denominator():
    """Only 3 of 20 tasks ran: the pass rate is not 3/3."""
    results = [_result(str(i), passed=True) for i in range(3)]

    summary = summarise_probe("m", results, n_tasks=20)

    assert summary.pass_rate == pytest.approx(0.15)
    assert summary.complete is False


# ---- the agent rule (0004 §4.3) ----


def _summary(model, pass_rate, valid_rate, n=20):
    return summarise_probe(
        model,
        [
            _result(
                str(i),
                passed=i < round(pass_rate * n),
                tool_calls=100,
                invalid=round((1 - valid_rate) * 100),
            )
            for i in range(n)
        ],
        n_tasks=n,
    )


def test_agent_rule_picks_the_pass_rate_closest_to_the_window_midpoint():
    candidates = [
        _summary("far", 0.40, 1.0),
        _summary("near", 0.55, 1.0),
        _summary("high", 0.70, 1.0),
    ]

    chosen, reason = choose_agent(candidates, {}, ["far", "near", "high"])

    assert chosen == "near"
    assert "closest to 0.55" in reason


def test_agent_rule_excludes_a_candidate_below_the_tool_call_floor():
    candidates = [_summary("sloppy", 0.55, 0.90), _summary("clean", 0.40, 1.0)]

    chosen, _ = choose_agent(candidates, {}, ["sloppy", "clean"])

    assert chosen == "clean"


def test_agent_rule_excludes_a_pass_rate_outside_the_window():
    candidates = [_summary("too_good", 0.90, 1.0), _summary("ok", 0.40, 1.0)]

    assert choose_agent(candidates, {}, ["too_good", "ok"])[0] == "ok"


def test_agent_rule_reports_no_candidate_rather_than_bending():
    candidates = [_summary("too_good", 0.90, 1.0), _summary("sloppy", 0.55, 0.80)]

    chosen, reason = choose_agent(candidates, {}, ["too_good", "sloppy"])

    assert chosen is None
    assert "no candidate" in reason.lower()


def test_agent_rule_breaks_a_tie_on_measured_rpm_then_list_order():
    candidates = [_summary("slow", 0.50, 1.0), _summary("fast", 0.60, 1.0)]
    # 0.50 and 0.60 are equidistant from 0.55.

    chosen, reason = choose_agent(candidates, {"slow": 100, "fast": 180}, ["slow", "fast"])

    assert chosen == "fast"
    assert "rpm" in reason


def test_agent_rule_falls_back_to_list_order_when_rpm_ties_too():
    candidates = [_summary("first", 0.50, 1.0), _summary("second", 0.60, 1.0)]

    chosen, reason = choose_agent(candidates, {"first": 180, "second": 180}, ["first", "second"])

    assert chosen == "first"
    assert "list order" in reason


# ---- the user-simulator rule (0004 §4.1) ----


def test_user_sim_is_kept_when_the_sanity_check_is_clean():
    results = [_result("0", passed=True), _result("1", passed=False)]

    usable, reason = user_sim_is_usable(results)

    assert usable is True
    assert "clean" in reason


def test_user_sim_is_rejected_when_every_task_errored():
    a = _result("0", passed=False)
    results = [
        TaskProbeResult(**{**a.__dict__, "error": "TransportError"}),
        TaskProbeResult(**{**a.__dict__, "task_id": "1", "error": "TransportError"}),
    ]

    usable, reason = user_sim_is_usable(results)

    assert usable is False
    assert "errored" in reason


def test_user_sim_is_rejected_when_it_returns_empty_messages():
    a = _result("0", passed=False)
    results = [
        TaskProbeResult(**{**a.__dict__, "n_empty_user_messages": 3}),
        TaskProbeResult(**{**a.__dict__, "task_id": "1"}),
    ]

    usable, reason = user_sim_is_usable(results)

    assert usable is False
    assert "empty" in reason


def test_user_sim_is_rejected_when_no_conversation_ever_ends():
    a = _result("0", passed=False)
    results = [
        TaskProbeResult(**{**a.__dict__, "termination_reason": "max_steps"}),
        TaskProbeResult(**{**a.__dict__, "task_id": "1", "termination_reason": "max_steps"}),
    ]

    usable, reason = user_sim_is_usable(results)

    assert usable is False
    assert "max_steps" in reason


def test_one_max_steps_task_out_of_two_is_not_enough_to_reject():
    a = _result("0", passed=False)
    results = [
        TaskProbeResult(**{**a.__dict__, "termination_reason": "max_steps"}),
        TaskProbeResult(**{**a.__dict__, "task_id": "1", "termination_reason": "agent_stop"}),
    ]

    assert user_sim_is_usable(results)[0] is True


# ---- the judge rule (0004 §4.2) ----


def test_judge_rule_takes_the_first_within_the_latency_budget():
    chosen, reason = choose_judge({"first": 45.0, "second": 12.0}, ["first", "second"])

    assert chosen == "second"
    assert "30" in reason


def test_judge_rule_prefers_list_order_when_both_are_fast_enough():
    chosen, _ = choose_judge({"first": 8.0, "second": 2.0}, ["first", "second"])

    assert chosen == "first"


def test_judge_rule_falls_back_to_the_faster_when_neither_qualifies():
    chosen, reason = choose_judge({"first": 90.0, "second": 44.0}, ["first", "second"])

    assert chosen == "second"
    assert "faster" in reason
