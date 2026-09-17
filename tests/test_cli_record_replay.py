"""Tests for the `bisect record` and `bisect replay` commands.

They live in their own modules until `cli.py` is free to register them
(two lines each), so these drive them through a `typer.Typer` of their
own -- exactly as `cli.py` will.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import typer
from agent_bisect.adapters.tau2_scenarios import AGENT_MODEL, AIRLINE_READS, USER_MODEL
from agent_bisect.cli_record import record
from agent_bisect.cli_replay import DIVERGENCE_EXIT_CODE, UNKNOWN_RUN_EXIT_CODE, replay
from agent_bisect.core.models import ChosenModels
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


def _scripted_record(monkeypatch, store: Store):
    """Point `bisect record` at the scripted model instead of the network.

    Only the model and the credential check are replaced; the command
    builds its own batch, its own store and its own ledger.
    """
    import agent_bisect.cli_record as cli_record
    from agent_bisect.adapters.tau2 import recording_session
    from agent_bisect.adapters.tau2_fake_llm import ScriptedLLM
    from tests.tau2_offline import UNUSED_API_BASE, UNUSED_API_KEY, no_limiter

    llm = ScriptedLLM(AIRLINE_READS.scripts)

    def scripted_session(*, ledger, phase):
        return recording_session(
            ledger=ledger,
            phase=phase,
            completion_fn=llm.completion,
            api_key=UNUSED_API_KEY,
            api_base=UNUSED_API_BASE,
            limiter_for=no_limiter,
        )

    monkeypatch.setattr(cli_record, "recording_session", scripted_session)
    monkeypatch.setattr(
        cli_record, "get_settings", lambda: SimpleNamespace(has_nvidia_key=True)
    )
    return llm


def _record_argv(store: Store, tasks: str) -> list[str]:
    return [
        "--domain", "airline",
        "--tasks", tasks,
        "--agent-model", AGENT_MODEL,
        "--user-model", USER_MODEL,
        "--runs-dir", str(store.root),
        "--ledger", str(store.root / "ledger.sqlite"),
    ]


def test_record_records_the_requested_tasks(runner, store, monkeypatch):
    llm = _scripted_record(monkeypatch, store)

    result = runner.invoke(_app(record), [*_record_argv(store, "0-1"), "--json"])

    assert result.exit_code == 0, result.stdout
    summary = _json_on_stdout(result)
    assert summary["recorded"] == 2
    assert summary["aborted_infra"] == 0
    assert summary["calls"] == llm.calls
    assert len(store.reader.get_steps("airline-0-t0")) > 0


def test_record_resumes_and_pays_for_nothing_twice(runner, store, monkeypatch):
    _scripted_record(monkeypatch, store)
    runner.invoke(_app(record), _record_argv(store, "0"))

    llm = _scripted_record(monkeypatch, store)
    result = runner.invoke(_app(record), [*_record_argv(store, "0"), "--json"])

    assert result.exit_code == 0
    assert _json_on_stdout(result)["recorded"] == 1
    assert llm.calls == 0, "a resumed run must cost nothing"


def test_record_prints_a_line_per_run_without_json(runner, store, monkeypatch):
    _scripted_record(monkeypatch, store)

    result = runner.invoke(_app(record), _record_argv(store, "0-1"))

    assert result.exit_code == 0
    assert "2 runs, 2 outstanding" in result.stdout
    assert "airline-0-t0" in result.stdout
    assert "recorded 2" in result.stdout


def test_record_defaults_to_the_models_p0_chose(runner, store, monkeypatch):
    """The brief's invocation is `bisect record --domain airline --tasks
    0-19`: no model flags, so the command must read the choice rather
    than carry a default of its own."""
    import agent_bisect.cli_record as cli_record

    _scripted_record(monkeypatch, store)
    monkeypatch.setattr(
        cli_record,
        "load_chosen_models",
        lambda: ChosenModels(
            agent=AGENT_MODEL, user_sim=USER_MODEL, judge="j", tau2_commit="c"
        ),
    )

    result = runner.invoke(
        _app(record),
        [
            "--domain", "airline", "--tasks", "0",
            "--runs-dir", str(store.root),
            "--ledger", str(store.root / "ledger.sqlite"),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert AGENT_MODEL in result.stdout
    assert store.reader.get_manifest("airline-0-t0").agent_model == AGENT_MODEL


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


# ---- the dashboard's Live page reads a status file ----


def test_record_publishes_a_done_status_the_dashboard_can_read(runner, store, monkeypatch):
    from agent_bisect.server.schemas_live import JobStatus

    _scripted_record(monkeypatch, store)

    runner.invoke(_app(record), _record_argv(store, "0-1"))

    status = json.loads((store.root / "p1" / "status.json").read_text())
    assert JobStatus.model_validate(status).state == "done"
    assert status["items_done"] == 2
    assert status["items_total"] == 2
    assert status["kind"] == "record"


def test_record_publishes_progress_while_it_runs(runner, store, monkeypatch):
    """The Live page polls the file, so it has to say "running" before the
    batch finishes, not only afterwards."""
    from agent_bisect.server.schemas_live import JobStatus

    seen: list[dict] = []
    _scripted_record(monkeypatch, store)
    _watch_status(monkeypatch, store, seen)

    runner.invoke(_app(record), _record_argv(store, "0-1"))

    running = [s for s in seen if s["state"] == "running"]
    assert running, [s["state"] for s in seen]
    assert all(0 < JobStatus.model_validate(s).progress < 1 for s in running)


def test_record_publishes_a_failed_status_when_the_batch_raises(runner, store, monkeypatch):
    import agent_bisect.cli_record as cli_record
    from agent_bisect.server.schemas_live import JobStatus

    _scripted_record(monkeypatch, store)

    def explode(*_args, **_kwargs):
        raise RuntimeError("the provider went away")

    monkeypatch.setattr(cli_record, "record_batch", explode)

    result = runner.invoke(_app(record), _record_argv(store, "0"))

    status = json.loads((store.root / "p1" / "status.json").read_text())
    assert result.exit_code != 0
    assert JobStatus.model_validate(status).state == "failed"
    assert "provider went away" in status["error"]


def test_a_failed_status_never_carries_key_material(runner, store, monkeypatch):
    import agent_bisect.cli_record as cli_record

    key = "nvapi" + "-" + "S" * 64
    _scripted_record(monkeypatch, store)
    monkeypatch.setattr(
        cli_record, "record_batch", _raiser(RuntimeError(f"upstream echoed {key}"))
    )

    runner.invoke(_app(record), _record_argv(store, "0"))

    assert key not in (store.root / "p1" / "status.json").read_text()


def _raiser(error: Exception):
    def raise_it(*_args, **_kwargs):
        raise error

    return raise_it


def _watch_status(monkeypatch, store: Store, seen: list[dict]) -> None:
    """Record every status the command writes, in order."""
    import agent_bisect.cli_record as cli_record
    from agent_bisect.core import job_status

    real = job_status.write_status

    def spy(runs_dir, status, **kwargs):
        seen.append(dict(status))
        return real(runs_dir, status, **kwargs)

    monkeypatch.setattr(cli_record, "write_status", spy)
