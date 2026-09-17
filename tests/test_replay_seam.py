"""Tests for the replay seam's thread safety.

`tau2.utils.llm_utils.completion` is a module attribute, so the naive way
to serve a tape -- rebind it -- is process-global: two forks in two
threads overwrite each other, and the second one's `finally` restores the
first's replayer as the global. From then on one fork's tape answers the
other's requests. The recorder already avoided this with a `ContextVar`;
these pin that the replay seam does too, because P3 runs 16 forks per
item and P5 samples N arms.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

import pytest
from agent_bisect.adapters.tau2_replay import _completion_patched, _dispatcher_installed


@pytest.fixture
def llm_utils():
    import tau2.utils.llm_utils as module

    original = module.completion
    yield module
    module.completion = original


def _fallback(**kwargs):
    return ("fallback", kwargs.get("model"))


def _serving(name: str):
    def completion(**kwargs):
        return (name, kwargs.get("model"))

    return completion


# ---- the dispatcher ----


def test_the_dispatcher_replaces_the_module_attribute_once(llm_utils):
    llm_utils.completion = _fallback

    with _dispatcher_installed():
        assert llm_utils.completion is not _fallback


def test_the_original_is_restored_when_the_last_holder_leaves(llm_utils):
    llm_utils.completion = _fallback

    with _dispatcher_installed(), _dispatcher_installed():
        pass

    assert llm_utils.completion is _fallback


def test_a_nested_install_does_not_restore_early(llm_utils):
    """Refcounted: the first thread in installs, the last one out restores."""
    llm_utils.completion = _fallback

    with _dispatcher_installed():
        with _dispatcher_installed():
            pass
        assert llm_utils.completion is not _fallback

    assert llm_utils.completion is _fallback


def test_with_nothing_bound_the_dispatcher_falls_through(llm_utils):
    """Outside any replay the call belongs to whatever was underneath --
    in production the router, so the live suffix keeps its limiter,
    ledger and retries."""
    llm_utils.completion = _fallback

    with _dispatcher_installed():
        assert llm_utils.completion(model="m") == ("fallback", "m")


def test_a_bound_completion_takes_precedence(llm_utils):
    llm_utils.completion = _fallback

    with _dispatcher_installed(), _completion_patched(_serving("tape")):
        assert llm_utils.completion(model="m") == ("tape", "m")


def test_the_binding_is_undone_on_leaving(llm_utils):
    llm_utils.completion = _fallback

    with _dispatcher_installed():
        with _completion_patched(_serving("tape")):
            pass
        assert llm_utils.completion(model="m") == ("fallback", "m")


# ---- the reason it exists ----


def test_each_thread_is_served_by_its_own_replayer(llm_utils):
    """The bug this file exists for: with a rebound module attribute,
    whichever thread patched last answered for every thread."""
    llm_utils.completion = _fallback
    barrier = __import__("threading").Barrier(4)

    def run(name: str) -> tuple:
        with _completion_patched(_serving(name)):
            # Every thread is inside its own binding at the same moment,
            # which is exactly when a module-global patch loses.
            barrier.wait(timeout=10)
            return llm_utils.completion(model=name)

    with _dispatcher_installed(), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, ["a", "b", "c", "d"]))

    assert results == [("a", "a"), ("b", "b"), ("c", "c"), ("d", "d")]


def test_one_threads_binding_does_not_leak_to_another(llm_utils):
    llm_utils.completion = _fallback

    def unbound(_ignored: int) -> tuple:
        return llm_utils.completion(model="unbound")

    with _dispatcher_installed(), _completion_patched(_serving("main")):
        with ThreadPoolExecutor(max_workers=2) as pool:
            elsewhere = list(pool.map(unbound, [0, 1]))
        here = llm_utils.completion(model="main")

    assert elsewhere == [("fallback", "unbound"), ("fallback", "unbound")]
    assert here == ("main", "main")


def test_concurrent_installs_restore_the_original_exactly_once(llm_utils):
    llm_utils.completion = _fallback
    barrier = __import__("threading").Barrier(8)

    def enter_and_leave(_ignored: int) -> None:
        with _dispatcher_installed():
            barrier.wait(timeout=10)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(enter_and_leave, range(8)))

    assert llm_utils.completion is _fallback


# ---- who owns the replayer's sense of where it is ----


class _Sink:
    """A sink that is told about steps, like a recorder."""

    def __init__(self) -> None:
        self.next_step_idx = 0

    def begin_step(self) -> None:
        return None

    def on_llm_call(self, *_args, **_kwargs) -> None:
        self.next_step_idx += 1

    def on_tool_call(self, *_args, **_kwargs) -> None:
        self.next_step_idx += 1


class _AlwaysLive:
    name: ClassVar[str] = "always-live"

    def apply(self, step, payload):
        from agent_bisect.core.replay import LIVE

        return LIVE


def _replayer(steps, store, sink, live):
    from agent_bisect.adapters.tau2_replay import Tau2Replayer

    return Tau2Replayer(
        environment=object(),
        steps=steps,
        store=store,
        sink=sink,
        fork_step=0,
        intervention=_AlwaysLive(),
        live_completion=live,
    )


def _two_recorded_steps(tmp_path):
    """Two LLM steps whose requests differ, as a real run's would."""
    from agent_bisect.core.store import BlobStore
    from agent_bisect.core.tape import Step, canonical_request_hash

    blobs = BlobStore(tmp_path)
    steps = []
    for index, actor in enumerate(["user", "agent"]):
        request = {"model": f"{actor}-model", "messages": [{"role": "user", "content": actor}]}
        steps.append(
            Step(
                run_id="r1",
                step_idx=index,
                actor=actor,  # pyright: ignore[reportArgumentType]
                request_hash=canonical_request_hash(request),
                request_ref=blobs.put_json(request),
                response_ref=blobs.put_json({"choices": [{"message": {"content": actor}}]}),
                state_before="a" * 64,
                state_after="a" * 64,
                state_hash="h" * 64,
                state_hash_before="h" * 64,
            )
        )
    return steps, blobs


def test_the_tape_stops_governing_once_a_step_has_gone_live(tmp_path):
    """The replayer must know it has passed the fork step on its own.

    Reading the sink's counter makes that depend on the live completion
    having told the sink -- true when it is the router, false for any
    other one -- and when it is false the tape keeps governing a run that
    has already gone live, hash-checking requests against a recording that
    no longer applies.
    """
    steps, blobs = _two_recorded_steps(tmp_path)
    sink = _SilentSink()
    replayer = _replayer(steps, blobs, sink, lambda **kwargs: ("live", kwargs.get("model")))

    first = replayer.completion(model="user-model", messages=[{"role": "user", "content": "user"}])
    second = replayer.completion(model="agent-model", messages=[{"role": "x", "content": "y"}])

    assert first == ("live", "user-model")
    assert second == ("live", "agent-model"), "the tape was still governing after going live"


class _SilentSink(_Sink):
    """A sink nobody tells about a live call -- any live completion that
    is not the router."""

    def on_llm_call(self, *_args, from_tape: bool = True, **_kwargs) -> None:
        if from_tape:
            self.next_step_idx += 1
