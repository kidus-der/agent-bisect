"""Truth resolution is serialised, because the forks of one item overlap."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from agent_bisect.adapters.tau2_fork import serialized_truth
from agent_bisect.core.tape import Step


def _step(step_idx: int) -> Step:
    return Step(
        run_id="r", step_idx=step_idx, actor="tool", tool_name="t",
        state_before="s", state_after="s", state_hash="h",
    )


class SharedEnvironment:
    """Stands in for `Tau2TruthResolver`: one environment, restored per call."""

    def __init__(self) -> None:
        self.state = -1
        self.overlaps = 0
        self.inside = 0
        self.lock = threading.Lock()

    def __call__(self, step: Step):
        with self.lock:
            self.inside += 1
            if self.inside > 1:
                self.overlaps += 1
        self.state = step.step_idx          # "restore"
        time.sleep(0.005)
        observed = self.state               # "execute against it"
        with self.lock:
            self.inside -= 1
        return {"content": observed}


def _resolve_many(truth, steps):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(truth, steps))


def test_unserialised_resolution_really_does_race():
    """The hazard is real, not hypothetical -- this is what we are preventing."""
    # Arrange
    environment = SharedEnvironment()
    steps = [_step(i) for i in range(8)]

    # Act
    results = _resolve_many(environment, steps)

    # Assert
    crossed = [
        r["content"] for r, s in zip(results, steps, strict=True)
        if r["content"] != s.step_idx
    ]
    assert environment.overlaps > 0
    assert crossed, "concurrent calls should have read each other's world"


def test_serialised_resolution_never_overlaps():
    # Arrange
    environment = SharedEnvironment()
    steps = [_step(i) for i in range(8)]

    # Act
    _resolve_many(serialized_truth(environment), steps)

    # Assert
    assert environment.overlaps == 0


def test_every_serialised_call_sees_its_own_step():
    # Arrange
    environment = SharedEnvironment()
    steps = [_step(i) for i in range(8)]

    # Act
    results = _resolve_many(serialized_truth(environment), steps)

    # Assert
    assert [r["content"] for r in results] == [s.step_idx for s in steps]


def test_the_wrapper_passes_the_answer_through_unchanged():
    # Arrange / Act
    truth = serialized_truth(lambda step: {"content": f"step-{step.step_idx}"})

    # Assert
    assert truth(_step(4)) == {"content": "step-4"}


# ---- a fork survives a flaky endpoint; a divergence does not ----


class _Recorder:
    """Enough of a tape for Tau2ForkExecutor's resume check."""

    def get_outcome(self, run_id):
        from agent_bisect.core.tape import UnknownRunError

        raise UnknownRunError(run_id)

    def get_manifest(self, run_id):
        from agent_bisect.core.tape import UnknownRunError

        raise UnknownRunError(run_id)


def _request():
    from agent_bisect.attribution.search import RerunRequest
    from agent_bisect.core.replay import NoOpIntervention

    return RerunRequest(
        parent_run_id="p", run_id="p-c4-abc", fork_step=4, arm="control",
        intervention=NoOpIntervention(), seed=1, prefix_tools="snapshot",
        unsafe_positional=False,
    )


def _executor(monkeypatch, failures, error):
    from agent_bisect.adapters import tau2_fork
    from agent_bisect.attribution.search import RerunOutcome

    monkeypatch.setattr(tau2_fork, "RETRY_BACKOFF_S", 0.0)
    executor = tau2_fork.Tau2ForkExecutor(
        store=None, reader=_Recorder(), tape=None, live_completion=lambda **k: None
    )
    calls = {"n": 0}

    def run_once(request, seed):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise error
        return RerunOutcome(passed=True, n_steps=3, calls=7)

    monkeypatch.setattr(executor, "_run_once", run_once)
    return executor, calls


def test_a_fork_survives_a_transient_transport_failure(monkeypatch):
    from agent_bisect.core.llm import TransportError

    executor, calls = _executor(monkeypatch, 2, TransportError("504"))

    outcome = executor.run(_request())

    assert outcome.passed is True
    assert calls["n"] == 3
    assert executor.infra_retries == 2


def test_a_fork_gives_up_after_the_attempt_limit(monkeypatch):
    import pytest as _pytest
    from agent_bisect.adapters import tau2_fork
    from agent_bisect.core.llm import TransportError

    executor, calls = _executor(monkeypatch, 99, TransportError("504"))

    with _pytest.raises(TransportError):
        executor.run(_request())
    assert calls["n"] == tau2_fork.INFRA_RETRIES


def test_a_divergence_is_never_retried(monkeypatch):
    import pytest as _pytest
    from agent_bisect.core.replay import DivergenceError

    error = DivergenceError(step_idx=1, actor="agent", expected="a", got="b", diff="d")
    executor, calls = _executor(monkeypatch, 99, error)

    with _pytest.raises(DivergenceError):
        executor.run(_request())
    assert calls["n"] == 1, "a divergence is a finding, not a wobble"
