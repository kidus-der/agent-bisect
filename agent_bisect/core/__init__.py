"""Core primitives: tape recording, storage, snapshotting, replay, and the LLM/budget plumbing.

HARD BOUNDARY: modules under `agent_bisect.core` must never import from
`agent_bisect.attribution`, `agent_bisect.bench`, or `agent_bisect.gate`.
This is enforced by an import-linter contract in `pyproject.toml` and by
`tests/test_import_boundaries.py`.

Planned modules: tape, store, snapshot, replay, runner, llm, budget.
"""
