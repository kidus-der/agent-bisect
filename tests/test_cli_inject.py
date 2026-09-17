"""`bisect inject`: the three commands, without a model.

`collect` needs a key and the API, so what is checked here is everything
around it — the refusals, the funnel report, and the one irreversible
act, freezing.
"""

from __future__ import annotations

import json

import pytest
from agent_bisect.bench.journal import Journal
from agent_bisect.cli_inject import (
    FROZEN_EXIT_CODE,
    MISSING_KEY_EXIT_CODE,
    NOTHING_TO_FREEZE_EXIT_CODE,
    app,
)
from typer.testing import CliRunner

runner = CliRunner()

MODELS_TOML = """
tau2_commit = "abc123"
agent = "a/model"
user_sim = "u/model"
judge = "j/model"
"""


def item(index: int, *, task: str = "0", fault: str = "wrong_value") -> dict:
    return {
        "item_id": f"airline-{task}-k{index}-{fault}",
        "domain": "airline",
        "task_id": task,
        "base_run_id": f"airline-{task}-t0",
        "base_pass_rate": 1.0,
        "run_id": f"airline-{task}-k{index}-{fault}-s0",
        "faulted_pass_rate": 0.0,
        "planted_step": index,
        "position_bucket": "early",
        "fault_type": fault,
        "mutation": {"fault_type": fault, "path": ["status"], "path_str": "status",
                     "old": "confirmed", "new": "pending", "detail": "changed"},
        "oracle": {"tool_result_ref": "d" * 64, "step_idx": index},
        "intervention": {"name": "replace_tool_result", "hash": "e" * 64,
                         "describe": "replaced", "fields": {"step": index}},
        "seeds": [1, 2, 3, 4],
        "n_reruns": 4,
    }


@pytest.fixture
def collected(isolated_env):
    """A work directory holding a finished collection's journal."""
    (isolated_env / "config").mkdir()
    (isolated_env / "config" / "models.toml").write_text(MODELS_TOML)
    journal = Journal(isolated_env / "runs" / "p3")
    for index, task in enumerate(["0", "0", "1", "2", "3", "4"]):
        journal.write(
            "candidate",
            f"airline-{task}-t0-k{index}",
            {"status": "kept", "reason_code": "kept",
             "item": item(index, task=task, fault="wrong_value" if index % 2 else "tool_error")},
        )
    journal.write("candidate", "airline-9-t0-k1",
                  {"status": "rejected", "reason_code": "not_flipped", "reason": "did not flip"})
    journal.write("stability", "airline-0-t0", {"stable": True, "rate": 1.0})
    journal.write("base", "airline-0-t0", {"run_id": "airline-0-t0", "passed": True})
    return isolated_env


def test_collect_refuses_without_a_key(isolated_env):
    result = runner.invoke(app, ["collect", "--tasks", "0"])

    assert result.exit_code == MISSING_KEY_EXIT_CODE
    assert "NVIDIA_API_KEY" in result.output


def test_status_reports_the_funnel_and_the_strata(collected):
    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    summary = json.loads(result.output)
    assert summary["kept"] == 6
    assert summary["by_fault_type"] == {"tool_error": 3, "wrong_value": 3}
    assert summary["by_domain"] == {"airline": 6}


def test_status_on_an_empty_work_directory_says_nothing_is_kept(isolated_env):
    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["kept"] == 0


def test_freeze_writes_a_manifest_and_its_hash(collected):
    result = runner.invoke(app, ["freeze", "--json"])

    assert result.exit_code == 0
    summary = json.loads(result.output)
    manifest = json.loads((collected / summary["manifest"]).read_text())
    assert manifest["frozen"] is True
    assert len(manifest["items"]) == 6
    assert manifest["models"]["agent"] == "a/model"
    assert len(summary["sha256"]) == 64


def test_freeze_refuses_to_overwrite_a_frozen_manifest(collected):
    runner.invoke(app, ["freeze", "--json"])

    second = runner.invoke(app, ["freeze", "--json"])

    assert second.exit_code == FROZEN_EXIT_CODE
    assert "frozen" in second.output


def test_freeze_refuses_when_nothing_was_kept(isolated_env):
    (isolated_env / "config").mkdir()
    (isolated_env / "config" / "models.toml").write_text(MODELS_TOML)

    result = runner.invoke(app, ["freeze"])

    assert result.exit_code == NOTHING_TO_FREEZE_EXIT_CODE
    assert "nothing to freeze" in result.output


def test_the_frozen_manifest_carries_the_funnel(collected):
    runner.invoke(app, ["freeze", "--json"])

    manifest = json.loads((collected / "data" / "manifest.json").read_text())

    assert manifest["counts"]["candidate_kept"] == 6
    assert manifest["counts"]["candidate_not_flipped"] == 1
    assert manifest["counts"]["base_runs"] == 1
