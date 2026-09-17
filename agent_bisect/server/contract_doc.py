"""Regenerates the `<!-- BEGIN/END GENERATED -->` example blocks in
`docs/design/api-contract.md` from the current fixture-mode server.

One source of truth for two callers: `scripts/export_contract_examples.py`
(writes the file) and `tests/server/test_contract_doc.py` (fails if the
committed doc doesn't match what this would produce right now). Every
number in this doc comes from an actual response, never a hand-typed
guess -- the same "an estimate never appears without its interval, and
never one we made up" discipline the dashboard itself follows applies to
its own documentation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

DOC_PATH = Path("docs/design/api-contract.md")

_MAX_ITEMS = 3
"""How many entries of a JSON array survive in an example -- enough to show
shape, few enough to keep the doc readable. The array's real length is
always disclosed alongside the truncation, never just "...".
"""

# (marker name, HTTP path) -- one GENERATED block per entry, rendered from
# `response.json()["data"]`. Deliberately targets the brief's own
# `brief-12-step` run for every /api/runs/{run_id}/... example, so the doc
# stays anchored to the one worked example readers already know.
_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("health", "/api/health"),
    ("meta", "/api/meta"),
    ("overview", "/api/overview"),
    ("runs-list", "/api/runs?limit=1"),
    ("run-detail", "/api/runs/brief-12-step"),
    ("step-payload", "/api/runs/brief-12-step/steps/7"),
    ("intervention-diff", "/api/runs/brief-12-step/steps/7/intervention-diff"),
    ("state-diff", "/api/runs/brief-12-step/steps/7/state-diff"),
    ("reruns", "/api/runs/brief-12-step/reruns"),
    ("benchmark", "/api/benchmark"),
    ("dataset", "/api/dataset?limit=1"),
    ("pr-checks", "/api/pr-checks"),
)


def _trim(value: Any, max_items: int = _MAX_ITEMS) -> Any:
    """The first `max_items` entries of any list, verbatim, plus a real
    count of how many more there are -- never a fabricated placeholder."""
    if isinstance(value, list):
        trimmed = [_trim(item, max_items) for item in value[:max_items]]
        if len(value) > max_items:
            trimmed.append(f"... ({len(value) - max_items} more)")
        return trimmed
    if isinstance(value, dict):
        return {key: _trim(item, max_items) for key, item in value.items()}
    return value


def _render(client: TestClient, path: str) -> str:
    body = client.get(path).json()
    return json.dumps(_trim(body["data"]), indent=2, sort_keys=True)


def _replace_block(text: str, name: str, payload: str) -> str:
    begin, end = f"<!-- BEGIN GENERATED: {name} -->", f"<!-- END GENERATED: {name} -->"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"no {begin} ... {end} block found in {DOC_PATH}")
    replacement = f"{begin}\n```json\n{payload}\n```\n{end}"
    return pattern.sub(replacement, text)


def build_doc_text(client: TestClient, original_text: str) -> str:
    """Pure: `original_text` in, regenerated text out -- no file I/O, so the
    drift test can call this without ever writing anything."""
    text = original_text
    for name, path in _ENDPOINTS:
        text = _replace_block(text, name, _render(client, path))
    return text


def regenerate_doc(client: TestClient) -> str:
    """Regenerates `DOC_PATH` on disk in place and returns the new text."""
    original = DOC_PATH.read_text()
    updated = build_doc_text(client, original)
    DOC_PATH.write_text(updated)
    return updated
