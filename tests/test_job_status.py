"""`runs/<phase>/status.json`: what a long job tells the dashboard.

The Live page reads one status file per phase directory
(`docs/design/api-contract.md`, "Real mode's `runs/<phase>/status.json`
convention"), and `server.schemas_live.JobStatus` refuses a file whose
state disagrees with its progress or timestamps. This helper is what
every long job writes through, so the refusal never happens in
production: the invariants are enforced where the file is built.
"""

from __future__ import annotations

import json

import pytest
from agent_bisect.core.job_status import (
    JobStatusError,
    done,
    failed,
    progress_for,
    queued,
    running,
    status_path,
    write_status,
)


def test_the_path_is_the_documented_one(tmp_path):
    assert status_path(tmp_path, "P3") == tmp_path / "p3" / "status.json"
    assert status_path(tmp_path, "p3") == tmp_path / "p3" / "status.json"


# ---- the four states ----


def test_a_queued_job_has_not_started():
    status = queued(kind="inject", phase="P3", items_total=120)

    assert status["state"] == "queued"
    assert status["progress"] == 0.0
    assert status["started_at"] is None


def test_a_running_job_is_strictly_between_nothing_and_everything():
    """`JobStatus` rejects a running job at 0.0 or 1.0, so a job that has
    just started, or has done all its items but not finished, must still
    report a progress the dashboard will accept."""
    just_started = running(kind="inject", phase="P3", items_done=0, items_total=120)
    nearly_done = running(kind="inject", phase="P3", items_done=120, items_total=120)

    assert 0.0 < just_started["progress"] < 1.0
    assert 0.0 < nearly_done["progress"] < 1.0


def test_a_done_job_is_complete_and_finished():
    status = done(kind="inject", phase="P3", items_done=120, items_total=120)

    assert status["progress"] == 1.0
    assert status["finished_at"] is not None
    assert status["error"] is None


def test_a_failed_job_says_why():
    status = failed(kind="inject", phase="P3", error="budget exhausted")

    assert status["state"] == "failed"
    assert status["error"] == "budget exhausted"


def test_a_failure_without_a_reason_is_refused():
    with pytest.raises(JobStatusError, match="reason"):
        failed(kind="inject", phase="P3", error="")


# ---- progress ----


@pytest.mark.parametrize(
    ("items_done", "items_total", "expected"),
    [(0, 10, 0.0), (5, 10, 0.5), (10, 10, 1.0), (11, 10, 1.0), (0, 0, 0.0)],
)
def test_progress_is_the_share_of_items_done(items_done, items_total, expected):
    assert progress_for(items_done, items_total) == expected


# ---- the file ----


def test_the_file_is_written_atomically_and_reads_back(tmp_path):
    path = write_status(tmp_path, running(kind="inject", phase="P3", items_done=3,
                                          items_total=10, calls_spent=412))

    written = json.loads(path.read_text())
    assert written["kind"] == "inject"
    assert written["calls_spent"] == 412
    assert not list(path.parent.glob(".tmp-*"))


def test_writing_again_replaces_the_previous_status(tmp_path):
    write_status(tmp_path, running(kind="inject", phase="P3", items_done=1, items_total=10))

    path = write_status(tmp_path, done(kind="inject", phase="P3", items_done=10,
                                       items_total=10))

    assert json.loads(path.read_text())["state"] == "done"


def test_the_written_status_is_one_the_dashboard_accepts(tmp_path):
    """The point of the helper: a file it wrote never trips `JobStatus`."""
    from agent_bisect.server.schemas_live import JobStatus

    for status in (
        queued(kind="inject", phase="P3", items_total=120),
        running(kind="inject", phase="P3", items_done=0, items_total=120),
        running(kind="inject", phase="P3", items_done=120, items_total=120),
        done(kind="inject", phase="P3", items_done=120, items_total=120),
        failed(kind="inject", phase="P3", error="budget exhausted"),
    ):
        JobStatus(job_id="p3", **status)


def test_an_unknown_state_is_refused():
    with pytest.raises(JobStatusError, match="state"):
        write_status_payload = {"kind": "inject", "state": "paused", "progress": 0.5}
        from agent_bisect.core.job_status import validated

        validated(write_status_payload)


def test_a_running_job_at_exactly_one_is_refused_if_built_by_hand():
    from agent_bisect.core.job_status import validated

    with pytest.raises(JobStatusError, match="progress"):
        validated({"kind": "inject", "state": "running", "progress": 1.0})


def test_a_done_job_without_a_finish_time_is_refused_if_built_by_hand():
    from agent_bisect.core.job_status import validated

    with pytest.raises(JobStatusError, match="finished_at"):
        validated({"kind": "inject", "state": "done", "progress": 1.0})
