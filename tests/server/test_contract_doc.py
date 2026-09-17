"""`docs/design/api-contract.md`'s generated example blocks must never drift
from what the fixture-mode server actually serves -- this is the one file
on the project that must not carry a number the server doesn't produce.
"""

from __future__ import annotations

from agent_bisect.server.contract_doc import DOC_PATH, build_doc_text


def test_contract_doc_examples_match_the_live_fixture_server(client):
    original = DOC_PATH.read_text()
    regenerated = build_doc_text(client, original)
    assert regenerated == original, (
        "docs/design/api-contract.md's generated example blocks are stale -- "
        "run `uv run python scripts/export_contract_examples.py` and commit the result"
    )
