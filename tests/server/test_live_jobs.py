"""Property test: the seeded live simulator must never emit a job whose
state disagrees with its progress/timestamps/error, across many seeds and
points in time -- this is what the hand-computed `(minute * 7 + i * 13) %
100` progress independent of state used to violate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_bisect.server.live_sim import LiveSimulator
from hypothesis import given, settings
from hypothesis import strategies as st

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    minutes_offset=st.integers(min_value=0, max_value=100_000),
)
@settings(max_examples=200)
def test_simulated_jobs_always_satisfy_their_own_invariants(seed, minutes_offset):
    simulator = LiveSimulator(seed)
    now = _EPOCH + timedelta(minutes=minutes_offset)

    # `JobStatus`'s own validator already rejects an impossible combination
    # at construction time -- if the simulator ever produces one, this
    # raises pydantic.ValidationError and the test fails right here.
    snapshot = simulator.snapshot(now)

    assert len(snapshot.jobs) > 0
    for job in snapshot.jobs:
        # Redundant with the schema validator, deliberately: this test
        # should keep catching the bug even if the validator is ever
        # loosened or bypassed.
        if job.state == "queued":
            assert job.progress == 0.0
            assert job.started_at is None
        elif job.state == "running":
            assert 0.0 < job.progress < 1.0
            assert job.started_at is not None
        elif job.state == "done":
            assert job.progress == 1.0
            assert job.finished_at is not None
        elif job.state == "failed":
            assert job.error is not None
