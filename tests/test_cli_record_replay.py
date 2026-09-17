"""Tests for the `bisect record` and `bisect replay` commands.

They live in their own modules until `cli.py` is free to register them
(two lines each), so these drive them through a `typer.Typer` of their
own -- exactly as `cli.py` will.
"""

from __future__ import annotations

import json

import pytest
import typer
from agent_bisect.adapters.tau2_scenarios import AGENT_MODEL, AIRLINE_READS, USER_MODEL
from agent_bisect.cli_record import record
from agent_bisect.cli_replay import DIVERGENCE_EXIT_CODE, UNKNOWN_RUN_EXIT_CODE, replay
from tests.tau2_offline import Store, quiet_tau2, ref, reward_of
from tests.tau2_offline import record as record_scenario
from typer.testing import CliRunner

pytestmark = pytest.mark.usefixtures("_no_real_key")


@pytest.fixture(autouse=True, scope="module")
def _quiet():
    quiet_tau2()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _app(command) -> typer.Typer:
    app = typer.Typer()
    app.command()(command)
    return app


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "runs")


# ---- bisect record ----


def test_record_refuses_without_a_key(runner, tmp_path, monkeypatch):
    """Nothing about a recording session is attempted without credentials."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    result = runner.invoke(
        _app(record),
        ["--agent-model", AGENT_MODEL, "--user-model", USER_MODEL, "--runs-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert "NVIDIA_API_KEY" in result.output


def test_record_help_documents_the_documented_invocation(runner):
    result = runner.invoke(_app(record), ["--help"])

    assert result.exit_code == 0
    assert "--domain" in result.output
    assert "--tasks" in result.output
    assert "--trials" in result.output


# ---- bisect replay ----


def test_replay_reports_an_identical_run(runner, store):
    record_scenario(AIRLINE_READS, store, run_id="r1")

    result = runner.invoke(_app(replay), ["r1", "--runs-dir", str(store.root)])

    assert result.exit_code == 0, result.output
    assert "replayed identically" in result.output


def test_replay_json_reports_the_counts(runner, store):
    recorded, _ = record_scenario(AIRLINE_READS, store, run_id="r1")

    result = runner.invoke(_app(replay), ["r1", "--runs-dir", str(store.root), "--json"])

    payload = _json_on_stdout(result)
    assert payload["identical"] is True
    assert payload["steps"] == recorded.steps
    assert payload["live_llm_calls"] == 0
    assert payload["reward"] == reward_of(recorded)


def test_replay_exits_4_on_an_unknown_run(runner, store):
    result = runner.invoke(_app(replay), ["nope", "--runs-dir", str(store.root)])

    assert result.exit_code == UNKNOWN_RUN_EXIT_CODE
    assert "no run" in result.output


def test_replay_exits_3_and_names_the_step_on_divergence(runner, store):
    record_scenario(AIRLINE_READS, store, run_id="r1")
    _tamper(store, "r1")

    result = runner.invoke(_app(replay), ["r1", "--runs-dir", str(store.root)])

    assert result.exit_code == DIVERGENCE_EXIT_CODE
    assert "diverged at step" in result.output


def test_replay_json_reports_a_divergence_as_data(runner, store):
    record_scenario(AIRLINE_READS, store, run_id="r1")
    _tamper(store, "r1")

    result = runner.invoke(_app(replay), ["r1", "--runs-dir", str(store.root), "--json"])

    payload = _json_on_stdout(result)
    assert payload["identical"] is False
    assert payload["actor"] == "agent"
    assert payload["diff"]


def _json_on_stdout(result) -> dict:
    """The command's own JSON, which must be the first thing on stdout.

    Click's runner merges stderr into the same buffer, so the library
    chatter `own_stdout` pushes to stderr still lands here -- after the
    JSON, never inside it.
    """
    payload, _end = json.JSONDecoder().raw_decode(result.stdout)
    return payload


def _tamper(store: Store, run_id: str) -> None:
    """Change one recorded agent request so the replay must diverge."""
    import sqlite3

    from agent_bisect.core.tape import canonical_request_hash

    target = next(step for step in store.reader.get_steps(run_id) if step.actor == "agent")
    request = store.blobs.get_json(ref(target.request_ref))
    messages = [dict(message) for message in request["messages"]]
    messages[0]["content"] = (messages[0]["content"] or "") + " tampered"
    mutated = {**request, "messages": messages}
    updated = target.model_copy(
        update={
            "request_ref": store.blobs.put_json(mutated),
            "request_hash": canonical_request_hash(mutated),
        }
    )
    connection = sqlite3.connect(store.root / "index.sqlite")
    with connection:
        connection.execute(
            "UPDATE steps SET step_json = ? WHERE run_id = ? AND step_idx = ?",
            (updated.model_dump_json(), run_id, target.step_idx),
        )
    connection.close()
