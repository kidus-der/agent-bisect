"""`demo.harness`: the demo suite must never touch the network.

`demo/agent.py`'s `demo_completion` never calls litellm's own network path
(the scripted response is fabricated directly), but litellm itself still
tries to *refresh its model cost map* from GitHub on import/first use
regardless of which provider is asked for -- `pytest-socket` blocks that,
logs a warning, and falls back, but the demo suite should never attempt it
at all: a PR-check worktree may have no network, and the attempt costs a
DNS round trip nothing here needs.
"""

from __future__ import annotations

import os

from demo.harness import ensure_litellm_offline


def test_ensure_litellm_offline_sets_the_env_var(monkeypatch):
    monkeypatch.delenv("LITELLM_LOCAL_MODEL_COST_MAP", raising=False)

    ensure_litellm_offline()

    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"


def test_ensure_litellm_offline_never_overrides_an_explicit_choice(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "False")

    ensure_litellm_offline()

    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "False"


def test_importing_the_harness_module_sets_it():
    """The module itself calls `ensure_litellm_offline()` at import time,
    so anything that imports `demo.harness` -- `demo.runner`,
    `demo.blame_cli`, every test here -- gets it for free."""
    import demo.harness  # noqa: F401 - the import's side effect is the point

    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") is not None
