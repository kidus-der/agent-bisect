"""Probe checkpointing: a finished task is never redone, an infra failure is always retried.

Protocol `docs/decisions/0004-p0-probe-protocol.md` §3: infra failures
(429/5xx/timeouts after retries, crashes of our code) are resumed or
re-run and are **never** counted as task failures. That only holds if a
failed attempt does not leave behind a checkpoint that the next run reads
back as a completed task.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# `scripts/` is a script directory, not an installed package, so it only joins
# sys.path at runtime (above) -- a static checker cannot resolve it from here.
from agent_bisect.adapters.tau2_probe import TaskProbeResult  # noqa: E402

from probe_models import (  # type: ignore[reportMissingImports]  # noqa: E402
    checkpoint_path,
    load_checkpoint,
    save_checkpoint,
)

MODEL = "nvidia/nemotron-3-super-120b-a12b"


@pytest.fixture(autouse=True)
def _probe_dir(tmp_path, monkeypatch):
    import probe_models  # type: ignore[reportMissingImports]  # noqa: PLC0415

    monkeypatch.setattr(probe_models, "PROBE_DIR", tmp_path)
    return tmp_path


def _result(task_id: str = "0", *, error: str | None = None) -> TaskProbeResult:
    return TaskProbeResult(
        model=MODEL,
        task_id=task_id,
        reward=None if error else 1.0,
        passed=error is None,
        n_steps=0 if error else 12,
        n_agent_calls=0 if error else 8,
        n_user_calls=0 if error else 4,
        n_agent_tool_calls=0 if error else 6,
        n_invalid_tool_calls=0,
        invalid_reasons=(),
        termination_reason="infrastructure_error" if error else "agent_stop",
        calls_used=3 if error else 12,
        wall_time_s=1.0,
        seed=1,
        error=error,
    )


def test_a_finished_task_is_read_back_and_never_redone(_probe_dir):
    save_checkpoint(_result("0"), '{"messages": []}')

    loaded = load_checkpoint(MODEL, "0")

    assert loaded is not None
    assert loaded.passed is True


def test_an_infra_failure_leaves_no_completion_checkpoint(_probe_dir):
    """Otherwise the next run skips the task instead of retrying it."""
    save_checkpoint(_result("1", error="TransportError: 503"), None)

    assert load_checkpoint(MODEL, "1") is None


def test_an_infra_failure_is_still_written_down_for_diagnosis(_probe_dir):
    save_checkpoint(_result("1", error="TransportError: 503"), None)

    errors = list((_probe_dir / MODEL.replace("/", "__")).glob("*.error.json"))

    assert len(errors) == 1
    assert "503" in errors[0].read_text()


def test_a_later_success_replaces_the_recorded_error(_probe_dir):
    save_checkpoint(_result("2", error="TransportError: 503"), None)
    save_checkpoint(_result("2"), '{"messages": []}')

    loaded = load_checkpoint(MODEL, "2")

    assert loaded is not None and loaded.passed is True
    assert not list((_probe_dir / MODEL.replace("/", "__")).glob("*.error.json"))


def test_the_simulation_json_sits_beside_its_checkpoint(_probe_dir):
    save_checkpoint(_result("3"), '{"messages": [1]}')

    sibling = checkpoint_path(MODEL, "3").with_suffix(".simulation.json")

    assert sibling.exists()


def test_a_checkpoint_is_never_mistaken_for_its_simulation_sibling(_probe_dir):
    save_checkpoint(_result("4"), '{"messages": [1]}')

    assert load_checkpoint(MODEL, "4") is not None
    assert load_checkpoint(MODEL, "4.simulation") is None


def test_an_unreadable_checkpoint_is_ignored_rather_than_crashing(_probe_dir):
    path = checkpoint_path(MODEL, "5")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")

    assert load_checkpoint(MODEL, "5") is None
