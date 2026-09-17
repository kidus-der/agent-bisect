"""Regenerates docs/design/api-contract.md's GENERATED example blocks from
the current fixture-mode server.

Run after any change that could shift a fixture-derived number (a schema
change, a generator fix like the judge shortlist_m correction, a reseed):

    uv run python scripts/export_contract_examples.py

`tests/server/test_contract_doc.py` fails if the committed doc ever
drifts from this output again.
"""

from __future__ import annotations

from agent_bisect.server.app import create_app
from agent_bisect.server.contract_doc import DOC_PATH, regenerate_doc
from agent_bisect.server.settings import ServerSettings
from fastapi.testclient import TestClient


def main() -> None:
    app = create_app(ServerSettings(data_source="fixture"))
    client = TestClient(app)
    regenerate_doc(client)
    print(f"regenerated {DOC_PATH}")


if __name__ == "__main__":
    main()
