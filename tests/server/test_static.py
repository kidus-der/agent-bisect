"""Static file serving: SPA fallback, path traversal safety, no-static-yet mode."""

from __future__ import annotations

from pathlib import Path

from agent_bisect.server.static import register_static
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_static_app(root: Path) -> TestClient:
    app = FastAPI()
    register_static(app, root=root)
    return TestClient(app)


def test_no_static_dir_registers_no_fallback_route(tmp_path):
    client = _build_static_app(tmp_path / "does-not-exist")
    # No routes at all registered under this bare app.
    response = client.get("/anything")
    assert response.status_code == 404


def test_serves_a_real_file(tmp_path):
    (tmp_path / "index.html").write_text("<html>dashboard</html>")
    (tmp_path / "app.js").write_text("console.log('hi')")
    client = _build_static_app(tmp_path)

    response = client.get("/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_unknown_path_falls_back_to_index(tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>")
    client = _build_static_app(tmp_path)

    response = client.get("/runs/some-run-id")
    assert response.status_code == 200
    assert "spa" in response.text


def test_path_traversal_is_rejected(tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>")
    secret_dir = tmp_path.parent / "secret"
    secret_dir.mkdir(exist_ok=True)
    (secret_dir / "leak.txt").write_text("should never be served")
    client = _build_static_app(tmp_path)

    response = client.get("/..%2Fsecret%2Fleak.txt")
    assert response.status_code in (200, 404)
    # Either it 404s outright, or (Starlette's own path normalization having
    # collapsed the segment first) it falls back to the SPA index -- either
    # way the secret file's contents must never appear in the response.
    assert "should never be served" not in response.text
