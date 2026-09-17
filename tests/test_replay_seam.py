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
