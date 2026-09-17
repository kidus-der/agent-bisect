"""Exports the dashboard API's OpenAPI schema to `agent_bisect/server/openapi.json`.

Run with `uv run python scripts/export_openapi.py`. The web team generates
TypeScript types from the committed output; re-run and re-commit whenever a
route or schema in `agent_bisect/server/` changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_bisect.server.app import create_app
from agent_bisect.server.settings import ServerSettings

OUT_PATH = Path("agent_bisect/server/openapi.json")


def main() -> None:
    app = create_app(ServerSettings(data_source="fixture"))
    schema = app.openapi()
    OUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
