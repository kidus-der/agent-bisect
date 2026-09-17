"""Re-run variation, measured from the journal and the tape.

Forks carry no per-re-run seed, so P5's intervals rest entirely on the
provider varying at temperature 0. These pin what "varied" means.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent_bisect.bench.journal import Journal
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import RunManifest, Step, TapeReader, TapeWriter
from scripts.p3_rerun_variation import (
    spread_of,
    stability_spread,
    summary,
    trajectory,
)


def _run(tape: TapeWriter, run_id: str, tools: list[str]) -> None:
    tape.start_run(RunManifest(
        run_id=run_id, domain="airline", task_id="0", agent_model="a", user_model="u",
        tau2_commit="x", created_at=datetime.now(UTC),
    ))
    for index, name in enumerate(tools):
        tape.append_step(Step(
            run_id=run_id, step_idx=index, actor="tool", tool_name=name,
            tool_args={"n": index}, state_before="a" * 64, state_after="b" * 64,
            state_hash="c" * 64,
        ))


def test_two_runs_that_called_the_same_tools_have_the_same_shape(tmp_path):
    tape, reader = TapeWriter(tmp_path), TapeReader(tmp_path)
    _run(tape, "one", ["get_user_details", "book_reservation"])
    _run(tape, "two", ["get_user_details", "book_reservation"])
    _run(tape, "three", ["get_user_details", "cancel_reservation"])

    assert trajectory(reader, "one") == trajectory(reader, "two")
    assert trajectory(reader, "one") != trajectory(reader, "three")
    assert trajectory(reader, "absent") is None


def test_a_group_of_identical_re_runs_is_reported_as_one_draw_repeated(tmp_path):
    tape, reader = TapeWriter(tmp_path), TapeReader(tmp_path)
    for run_id in ("a1", "a2", "b1"):
        _run(tape, run_id, ["get_user_details"])
    _run(tape, "b2", ["get_user_details", "book_reservation"])

    spread = spread_of(reader, [["a1", "a2"], ["b1", "b2"]])

    assert spread.groups == 2
    assert spread.identical == 1
    assert spread.identical_share == 0.5


def test_a_group_with_nothing_to_compare_is_not_counted(tmp_path):
    tape, reader = TapeWriter(tmp_path), TapeReader(tmp_path)
    _run(tape, "only", ["get_user_details"])

    assert spread_of(reader, [["only"], ["absent", "gone"]]).groups == 0


def test_the_stability_spread_counts_passes_out_of_four(tmp_path):
    journal = Journal(tmp_path)
    journal.write("stability", "r1", {"passes": 4, "run_ids": list("abcd"), "stable": True})
    journal.write("stability", "r2", {"passes": 3, "run_ids": list("efgh"), "stable": True})
    journal.write("stability", "r3", {"passes": 1, "run_ids": list("ijkl"), "stable": False})

    spread = stability_spread(journal)

    assert spread["base_runs"] == 3
    assert spread["stable"] == 2
    assert spread["passes_out_of_four"] == {"4/4": 1, "3/4": 1, "1/4": 1}


def test_the_summary_reports_both_kinds_of_group(tmp_path):
    BlobStore(tmp_path / "runs")
    TapeWriter(tmp_path / "runs")
    journal = Journal(tmp_path / "p3")
    journal.write("stability", "r1", {"passes": 4, "run_ids": ["x"], "stable": True})
    journal.write("candidate", "c1", {"status": "kept", "rerun_run_ids": ["y", "z"]})

    report = summary(tmp_path / "p3", tmp_path / "runs")

    assert report["stability"]["base_runs"] == 1
    assert "identical_share" in report["faulted_trajectories"]
