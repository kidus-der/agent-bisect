"""Serves the built dashboard (`agent_bisect/server/static/`) with an SPA fallback.

Registered last in `app.create_app`, after every `/api/*` router, so it
never shadows an API route. If the static directory doesn't exist yet (the
web app hasn't been built into it), no routes are registered at all -- the
server just runs API-only, which is the state P6a ships in.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

STATIC_ROOT = Path(__file__).parent / "static"


def _safe_resolve(root: Path, requested: str) -> Path | None:
    """Resolves `requested` under `root`, or `None` if it would escape `root`.

    Guards against path traversal (`../`, absolute paths, symlink escapes)
    by checking the *resolved* path is still inside the *resolved* root.
    """
    candidate = (root / requested.lstrip("/")).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def register_static(app: FastAPI, root: Path = STATIC_ROOT) -> None:
    """Mount the SPA fallback route if `root` exists; a no-op otherwise."""
    if not root.exists() or not root.is_dir():
        return
    resolved_root = root.resolve()
    index_path = resolved_root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = _safe_resolve(resolved_root, full_path)
        if candidate is None:
            raise HTTPException(status_code=404, detail="not found")
        if candidate.is_file():
            return FileResponse(candidate)
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="dashboard not built")
        return FileResponse(index_path)
