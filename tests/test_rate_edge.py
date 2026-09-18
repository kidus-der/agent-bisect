"""Finding each model's real rate ceiling without going over it.

P0 only bracketed the limits: the agent model was clean at 120 rpm and
429'd at 160, the user simulator 429'd below 120. The limiter was then set
to the conservative end of each bracket (108 / 60), which leaves most of
the account's capacity unused.

This walks the rate up while the provider is quiet and backs it down the
moment it is not — additive increase, multiplicative decrease, over the
ledger's own record of what happened. A 429 is a signal, never a failure:
the retry policy is unchanged and still absorbs them.
"""

from __future__ import annotations

import json
import time

import pytest
from agent_bisect.core.budget import BudgetLedger, CallRecord
from agent_bisect.core.rate_edge import (
    AdaptiveLimiter,
    EdgePolicy,
    RateEdge,
    write_back_edges,
)

AGENT = "nvidia/nemotron-3-super-120b-a12b"
USER = "nvidia/nemotron-3.5-lightning-30b-a3b"


def ledger_with(tmp_path, rows: list[tuple[str, str]], *, ts: float | None = None):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")
    when = ts if ts is not None else time.time()
    for model, status in rows:
        ledger.record(CallRecord(ts=when, phase="P3", model=model, purpose="agent",
                                 status=status, tokens_in=0, tokens_out=0, latency_ms=9000.0))
    return ledger


def _window(ledger, edge, rows):
    """One minute of calls, then one control step over them."""
    now = time.time()
    for model, status in rows:
        ledger.record(CallRecord(ts=now, phase="P3", model=model, purpose="agent",
                                 status=status, tokens_in=0, tokens_out=0,
                                 latency_ms=9000.0))
    edge.step()


def edge_for(tmp_path, ledger, **policy):
    return RateEdge(
        ledger=ledger,
        floors={AGENT: 108.0, USER: 60.0},
        ceilings={AGENT: 180.0, USER: 120.0},
        log_dir=tmp_path / "limits",
        policy=EdgePolicy(**policy),
    )


# ---- the bucket can be retuned ----


def test_an_adaptive_limiter_changes_rate_without_changing_identity():
    limiter = AdaptiveLimiter(60.0)

    limiter.retune(120.0)

    assert limiter.requests_per_minute == 120.0
    limiter.acquire_sync()


def test_a_limiter_refuses_a_rate_that_is_not_positive():
    with pytest.raises(ValueError, match="positive"):
        AdaptiveLimiter(60.0).retune(0.0)


# ---- additive increase ----


def test_three_clean_windows_earn_more_rate(tmp_path):
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 40)
    edge = edge_for(tmp_path, ledger, clean_windows_before_increase=3, increase_rpm=4.0)

    for _ in range(3):
        edge.step()

    assert edge.edges()[AGENT] == 112.0


def test_rate_never_climbs_past_the_ceiling(tmp_path):
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 40)
    edge = edge_for(tmp_path, ledger, clean_windows_before_increase=1, increase_rpm=100.0)

    for _ in range(5):
        edge.step()

    assert edge.edges()[AGENT] == 180.0


# ---- multiplicative decrease ----


def test_a_window_with_two_rate_limits_backs_the_rate_off(tmp_path):
    """The decrease is visible only above the floor: the configured rate
    is what P0 measured as clean, so nothing ever goes under it."""
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")
    edge = edge_for(tmp_path, ledger, clean_windows_before_increase=1,
                    increase_rpm=40.0, decrease_factor=0.8)
    _window(ledger, edge, [(AGENT, "ok")] * 20)
    climbed = edge.edges()[AGENT]

    _window(ledger, edge, [(AGENT, "ok")] * 20 + [(AGENT, "rate_limited")] * 2)

    assert climbed == 148.0
    assert edge.edges()[AGENT] == pytest.approx(148.0 * 0.8)


def test_one_rate_limit_is_noise_not_a_storm(tmp_path):
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 20 + [(AGENT, "rate_limited")])
    edge = edge_for(tmp_path, ledger)

    edge.step()

    assert edge.edges()[AGENT] == 108.0


def test_rate_never_falls_below_the_configured_floor(tmp_path):
    ledger = ledger_with(tmp_path, [(AGENT, "rate_limited")] * 20)
    edge = edge_for(tmp_path, ledger)

    for _ in range(10):
        edge.step()

    assert edge.edges()[AGENT] == 108.0


def test_a_storm_resets_the_clean_streak(tmp_path):
    """Two clean windows earn a rise; a storm in between means the count
    starts again, so the rate does not climb on the strength of quiet
    minutes either side of a bad one."""
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")
    edge = edge_for(tmp_path, ledger, clean_windows_before_increase=2, increase_rpm=4.0)

    _window(ledger, edge, [(AGENT, "ok")] * 10)
    _window(ledger, edge, [(AGENT, "ok")] * 10 + [(AGENT, "rate_limited")] * 2)
    _window(ledger, edge, [(AGENT, "ok")] * 10)

    assert edge.edges()[AGENT] == 108.0


# ---- what it records ----


def test_every_window_is_logged_for_the_record(tmp_path):
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 12 + [(AGENT, "rate_limited")] * 3)
    edge = edge_for(tmp_path, ledger)

    edge.step()

    written = [
        json.loads(line)
        for line in (tmp_path / "limits" / f"{AGENT.replace('/', '_')}.jsonl")
        .read_text()
        .splitlines()
    ]
    assert written[-1]["http_429"] == 3
    assert written[-1]["ok"] == 12
    assert written[-1]["target_rpm"] == 108.0


def test_the_discovered_edges_are_written_back_to_the_config(tmp_path):
    path = tmp_path / "limits.toml"
    path.write_text('[limiter]\nrequests_per_minute = 108\nscope = "model"\n')

    write_back_edges(path, {AGENT: 144.0, USER: 96.0})

    text = path.read_text()
    assert "[limiter.measured_rpm_edge]" in text
    assert '"nvidia/nemotron-3-super-120b-a12b" = 144.0' in text
    assert 'requests_per_minute = 108' in text


def test_writing_back_twice_replaces_rather_than_appends(tmp_path):
    path = tmp_path / "limits.toml"
    path.write_text('[limiter]\nscope = "model"\n')

    write_back_edges(path, {AGENT: 120.0})
    write_back_edges(path, {AGENT: 160.0})

    assert path.read_text().count("[limiter.measured_rpm_edge]") == 1
    assert "160.0" in path.read_text()


# ---- keeping the limiter, not latency, the binding constraint ----


def test_thread_count_follows_rate_and_latency(tmp_path):
    """Little's law with a quarter of headroom: at 108 rpm and 9 s per
    call, about 20 calls have to be in flight for the bucket to be the
    thing that binds."""
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 30)
    edge = edge_for(tmp_path, ledger)
    edge.step()

    assert 18 <= edge.recommended_threads() <= 22


def test_thread_count_is_capped(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite")
    now = time.time()
    for _ in range(30):
        ledger.record(CallRecord(ts=now, phase="P3", model=AGENT, purpose="agent",
                                 status="ok", tokens_in=0, tokens_out=0,
                                 latency_ms=120_000.0))
    edge = edge_for(tmp_path, ledger)
    edge.step()

    assert edge.recommended_threads() == EdgePolicy().max_threads


def test_the_binding_model_is_named(tmp_path):
    """The agent makes about three calls for every one the user simulator
    makes, so the user simulator binds when its edge is below a third of
    the agent's — worth saying out loud rather than leaving to be
    inferred from a stalled rate."""
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 20)
    edge = edge_for(tmp_path, ledger)
    edge._rates[USER] = 20.0  # noqa: SLF001 - the condition under test

    assert edge.binding_model() == USER


def test_no_model_binds_when_the_ratio_is_comfortable(tmp_path):
    ledger = ledger_with(tmp_path, [(AGENT, "ok")] * 20)

    assert edge_for(tmp_path, ledger).binding_model() is None
