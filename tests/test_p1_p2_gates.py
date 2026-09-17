"""Tests for the P1 and P2 gate scripts.

The gates run against a real recording store, so these build one with the
scripted scenarios and then drive the gate logic over it -- including the
failure paths, because a gate that cannot fail is not a gate.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

import pytest
from agent_bisect.adapters.tau2_batch import items_for, record_batch, with_task
from agent_bisect.adapters.tau2_scenarios import AIRLINE_READS
from tests.tau2_offline import Store, quiet_tau2, ref, scripted_session, spec_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gates import p1 as p1_gate  # noqa: E402
from scripts.gates import p2 as p2_gate  # noqa: E402

pytestmark = pytest.mark.usefixtures("_no_real_key")

#: Two runs is enough to exercise every code path; the real gate needs 20.
RECORDED = 2


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


@pytest.fixture
def recorded(tmp_path) -> Store:
    """A store holding `RECORDED` real scripted runs."""
    store = Store(tmp_path / "runs")
    with scripted_session(AIRLINE_READS, store.root):
        record_batch(
            items_for("airline", [str(index) for index in range(RECORDED)]),
            spec_for=lambda item: with_task(spec_for(AIRLINE_READS), item),
            store=store.blobs,
            tape=store.tape,
            reader=store.reader,
            root=store.root,
        )
    return store


class _Criterion(Protocol):
    """What both gates' Criterion dataclasses have in common."""

    name: str
    passed: bool
    detail: str
    data: dict[str, Any]


def _by_name(criteria: Iterable[_Criterion]) -> dict[str, _Criterion]:
    return {criterion.name: criterion for criterion in criteria}


# ---- P1 ----


def test_p1_passes_on_a_clean_store(recorded):
    criteria = p1_gate.run_gate(recorded.root, RECORDED, [])

    assert all(criterion.passed for criterion in criteria), [c.detail for c in criteria]


def test_p1_counts_recorded_runs_and_fails_when_short(recorded):
    criteria = _by_name(p1_gate.run_gate(recorded.root, RECORDED + 1, []))

    assert criteria["runs"].passed is False
    assert criteria["runs"].data["runs"] == RECORDED


def test_p1_checks_every_step_of_every_run(recorded):
    criteria = _by_name(p1_gate.run_gate(recorded.root, RECORDED, []))

    expected = sum(
        len(recorded.reader.get_steps(f"airline-{index}-t0")) for index in range(RECORDED)
    )
    assert criteria["state"].data["checked"] == expected
    assert criteria["state"].data["reproduced"] == expected


def test_p1_fails_when_a_recorded_state_hash_does_not_restore(recorded):
    """The criterion is 100%, so one tampered step must fail the gate."""
    step = recorded.reader.get_steps("airline-0-t0")[0]
    _replace_step(recorded, step.model_copy(update={"state_hash": "not-the-real-hash"}))

    criteria = _by_name(p1_gate.run_gate(recorded.root, RECORDED, []))

    assert criteria["state"].passed is False
    assert criteria["state"].data["reproduced"] < criteria["state"].data["checked"]


def test_p1_fails_a_run_not_pinned_to_a_tau2_commit(recorded):
    manifest = recorded.reader.get_manifest("airline-0-t0")
    unpinned = manifest.model_copy(update={"tau2_commit": p1_gate.UNKNOWN_COMMIT})
    connection = sqlite3.connect(recorded.root / "index.sqlite")
    with connection:
        connection.execute(
            "UPDATE runs SET manifest_json = ? WHERE run_id = ?",
            (unpinned.model_dump_json(), "airline-0-t0"),
        )
    connection.close()

    criteria = _by_name(p1_gate.run_gate(recorded.root, RECORDED, []))

    assert criteria["runs"].passed is False
    assert "airline-0-t0" in criteria["runs"].data["unpinned"]


def test_p1_redaction_scan_reads_inside_compressed_blobs(recorded):
    """A key inside a zstd frame is still a key."""
    key = "nvapi" + "-" + "D" * 64
    blob = recorded.root / "blobs" / "ff" / "ff"
    blob.mkdir(parents=True, exist_ok=True)
    import zstandard

    (blob / "planted.zst").write_bytes(zstandard.ZstdCompressor().compress(key.encode()))

    hits = p1_gate.scan_for_key_material(recorded.root)

    assert any("planted" in hit for hit in hits)


def test_p1_redaction_scan_reads_logs_and_checkpoints(recorded):
    key = "nvapi" + "-" + "E" * 64
    (recorded.root / "logs").mkdir(parents=True, exist_ok=True)
    (recorded.root / "logs" / "record.log").write_text(f"connecting with {key}")

    criteria = _by_name(
        p1_gate.run_gate(recorded.root, RECORDED, [recorded.root / "logs"])
    )

    assert criteria["redaction"].passed is False


def test_p1_writes_a_report_and_exits_non_zero_on_failure(recorded, capsys):
    exit_code = p1_gate.main(
        ["--runs-dir", str(recorded.root), "--required-runs", str(RECORDED + 5), "--also-scan"]
    )

    assert exit_code == 1
    report = json.loads((recorded.root / "p1" / "gate.json").read_text())
    assert report["gate"] == "P1"
    assert report["passed"] is False
    assert "FAILED" in capsys.readouterr().out


def test_p1_exits_zero_and_reports_pass(recorded, capsys):
    exit_code = p1_gate.main(
        ["--runs-dir", str(recorded.root), "--required-runs", str(RECORDED), "--also-scan"]
    )

    assert exit_code == 0
    assert json.loads((recorded.root / "p1" / "gate.json").read_text())["passed"] is True
    assert "PASS" in capsys.readouterr().out


# ---- P2 ----


def test_p2_passes_on_a_clean_store(recorded):
    criteria = p2_gate.run_gate(recorded.root, RECORDED)

    assert all(criterion.passed for criterion in criteria), [c.detail for c in criteria]


def test_p2_replays_every_recorded_run(recorded):
    criteria = _by_name(p2_gate.run_gate(recorded.root, RECORDED))

    assert criteria["replay"].data == {
        "identical": RECORDED,
        "runs": RECORDED,
        "required": RECORDED,
        "failures": [],
    }


def test_p2_proves_a_mutated_request_is_caught(recorded):
    criteria = _by_name(p2_gate.run_gate(recorded.root, RECORDED))

    assert criteria["divergence"].passed is True
    assert criteria["divergence"].data["reported_step"] >= 0


def test_p2_leaves_the_store_it_mutated_untouched(recorded):
    """The divergence check works on a scratch copy, so the real recording
    is still replayable afterwards."""
    before = [
        step.request_hash for step in recorded.reader.get_steps("airline-0-t0")
    ]

    p2_gate.run_gate(recorded.root, RECORDED)

    after = [step.request_hash for step in recorded.reader.get_steps("airline-0-t0")]
    assert after == before


def test_p2_fails_when_a_run_no_longer_replays(recorded):
    step = next(s for s in recorded.reader.get_steps("airline-0-t0") if s.actor == "tool")
    drifted = {**recorded.blobs.get_json(ref(step.tool_result_ref)), "content": "drifted"}
    _replace_step(
        recorded, step.model_copy(update={"tool_result_ref": recorded.blobs.put_json(drifted)})
    )

    criteria = _by_name(p2_gate.run_gate(recorded.root, RECORDED))

    assert criteria["replay"].passed is False
    assert criteria["replay"].data["identical"] < RECORDED


def test_p2_fails_when_there_is_nothing_recorded(tmp_path):
    criteria = _by_name(p2_gate.run_gate(tmp_path / "empty", RECORDED))

    assert criteria["replay"].passed is False
    assert criteria["divergence"].passed is False


def test_p2_blocks_the_network_while_replaying():
    """The gate's own guard, not the suite's.

    pytest-socket already blocks every socket here, so it is lifted for
    the length of this test -- otherwise the assertion would pass whether
    or not the gate guards anything.
    """
    import socket

    import pytest_socket

    pytest_socket.enable_socket()
    try:
        with pytest.raises(p2_gate.NetworkBlockedError), p2_gate.network_blocked():
            socket.socket()
    finally:
        pytest_socket.disable_socket(allow_unix_socket=True)


def test_p2_restores_the_socket_factory_afterwards():
    import socket

    original = socket.socket
    with p2_gate.network_blocked():
        pass

    assert socket.socket is original


def test_p2_writes_a_report_and_exits_non_zero_on_failure(recorded, capsys):
    exit_code = p2_gate.main(["--runs-dir", str(recorded.root), "--required-runs", "99"])

    assert exit_code == 1
    report = json.loads((recorded.root / "p2" / "gate.json").read_text())
    assert report["gate"] == "P2"
    assert "FAILED" in capsys.readouterr().out


def test_p2_exits_zero_and_reports_pass(recorded, capsys):
    exit_code = p2_gate.main(["--runs-dir", str(recorded.root), "--required-runs", str(RECORDED)])

    assert exit_code == 0
    assert json.loads((recorded.root / "p2" / "gate.json").read_text())["passed"] is True
    assert "PASS" in capsys.readouterr().out


def _replace_step(store: Store, step) -> None:
    connection = sqlite3.connect(store.root / "index.sqlite")
    with connection:
        connection.execute(
            "UPDATE steps SET step_json = ? WHERE run_id = ? AND step_idx = ?",
            (step.model_dump_json(), step.run_id, step.step_idx),
        )
    connection.close()
