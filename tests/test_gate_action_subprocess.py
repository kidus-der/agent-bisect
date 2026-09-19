"""`gate.action`'s subprocess/worktree wrappers, with `subprocess.run` faked.

The real thing is exercised end to end by `scripts/gates/p7.py`'s
self-test (real worktrees, real `uv run`, real GitHub PRs) -- these tests
check the wrapper functions' own logic (which command they build, how a
non-zero exit becomes a `GateError`, what a successful run reads back) in
milliseconds, with no subprocess and no filesystem beyond `tmp_path`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from agent_bisect.gate import action


@pytest.fixture(autouse=True)
def _reset_prepared_worktrees():
    """`_prepared_worktrees` is a module-level cache; tests must not leak
    into each other through it."""
    action._prepared_worktrees.clear()
    yield
    action._prepared_worktrees.clear()


def _completed(returncode: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)


def test_prepare_worktree_runs_setup_then_sync(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    action._prepare_worktree(tmp_path)

    assert calls[0][:2] == ["bash", "scripts/setup_tau2.sh"]
    assert calls[1][:3] == ["uv", "sync", "--frozen"]


def test_prepare_worktree_is_a_no_op_the_second_time(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    action._prepare_worktree(tmp_path)
    action._prepare_worktree(tmp_path)

    assert len(calls) == 2  # not 4: the second call found the worktree already prepared


def test_prepare_worktree_raises_gate_error_when_setup_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess, "run", lambda args, **kwargs: _completed(1, "network unreachable")
    )

    with pytest.raises(action.GateError, match="setup_tau2.sh failed"):
        action._prepare_worktree(tmp_path)


def test_prepare_worktree_raises_gate_error_when_sync_fails(monkeypatch, tmp_path):
    responses = iter([_completed(0), _completed(1, "lock mismatch")])
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: next(responses))

    with pytest.raises(action.GateError, match="uv sync --frozen failed"):
        action._prepare_worktree(tmp_path)


def test_run_demo_runner_reads_back_the_summary_it_wrote(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: _completed(0))
    out = tmp_path / "out"
    out.mkdir()
    (out / "summary.json").write_text(json.dumps({"pass_rate": 0.9}))

    document = action.run_demo_runner(tmp_path, out=out, seed=1, runs=4)

    assert document == {"pass_rate": 0.9}


def test_run_demo_runner_raises_gate_error_on_a_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return _completed(1, "boom") if "demo.runner" in args else _completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(action.GateError, match="demo.runner failed"):
        action.run_demo_runner(tmp_path, out=tmp_path / "out", seed=1, runs=4)


def test_run_blame_cli_reads_back_the_failures_result(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: _completed(0))
    out = tmp_path / "out"
    out.mkdir()
    (out / "failures_result.json").write_text(json.dumps([{"blamed_step": 2}]))

    summaries = action.run_blame_cli(
        tmp_path, failures_path=tmp_path / "f.json",
        head_store=tmp_path / "head", base_store=tmp_path / "base", out=out, seed=1,
    )

    assert summaries == [{"blamed_step": 2}]


def test_run_blame_cli_raises_gate_error_on_a_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return _completed(1, "traceback") if "demo.blame_cli" in args else _completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(action.GateError, match="demo.blame_cli failed"):
        action.run_blame_cli(
            tmp_path, failures_path=tmp_path / "f.json",
            head_store=tmp_path / "head", base_store=tmp_path / "base",
            out=tmp_path / "out", seed=1,
        )


# ---- run_gate, fully mocked --------------------------------------------


def _clean_summary(name: str) -> dict:
    return {
        "scenarios": [
            {"name": name, "rule_id": "r", "runs": [
                {"run_index": i, "passed": True, "run_id": f"demo-{name}-{i}"} for i in range(4)
            ]}
        ]
    }


def test_run_gate_resolves_a_relative_out_before_using_it(monkeypatch, tmp_path):
    """The bug that broke every one of layer (b)'s first real PRs: a
    relative --out resolved against the subprocess's cwd, not this
    process's, so summary.json was written somewhere run_gate never read."""
    seen_paths: list[Path] = []

    def fake_worktree_at(repo, ref, *, label):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            yield tmp_path / label

        return cm()

    def fake_run_demo_runner(worktree, *, out, seed, runs):
        seen_paths.append(out)
        assert out.is_absolute(), f"{out} was handed to the subprocess layer as a relative path"
        return _clean_summary("a")

    monkeypatch.setattr(action, "worktree_at", fake_worktree_at)
    monkeypatch.setattr(action, "run_demo_runner", fake_run_demo_runner)
    monkeypatch.chdir(tmp_path)

    config = action.GateConfig(
        repo=tmp_path, base="main", head="feature", out=Path("relative/out"), runs=4,
    )
    code, document = action.run_gate(config)

    assert code == action.CLEAN_EXIT
    assert all(path.is_absolute() for path in seen_paths)
    assert document["is_regression"] is False


def test_run_gate_triggers_blame_only_on_regression(monkeypatch, tmp_path):
    blame_called = []

    def fake_worktree_at(repo, ref, *, label):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            yield tmp_path / label

        return cm()

    def fake_run_demo_runner(worktree, *, out, seed, runs):
        return _clean_summary("a") if "base" in str(worktree) else {
            "scenarios": [
                {"name": "a", "rule_id": "r", "runs": [
                    {"run_index": i, "passed": False, "run_id": f"demo-a-{i}"} for i in range(4)
                ]}
            ]
        }

    def fake_run_blame_cli(*args, **kwargs):
        blame_called.append(True)
        return [{"blamed_step": None, "total_calls": 0}]

    monkeypatch.setattr(action, "worktree_at", fake_worktree_at)
    monkeypatch.setattr(action, "run_demo_runner", fake_run_demo_runner)
    monkeypatch.setattr(action, "run_blame_cli", fake_run_blame_cli)
    monkeypatch.setattr(action, "diff_lines", lambda *a, **k: [])

    config = action.GateConfig(
        repo=tmp_path, base="main", head="feature", out=tmp_path / "out", runs=4,
    )
    code, document = action.run_gate(config)

    assert code == action.REGRESSION_EXIT
    assert document["is_regression"] is True
    assert blame_called == [True]
