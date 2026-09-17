"""Every JSON endpoint returns the shared envelope shape."""

from __future__ import annotations

import pytest

_ENDPOINTS = (
    "/api/health",
    "/api/meta",
    "/api/overview",
    "/api/runs",
    "/api/benchmark",
    "/api/dataset",
    "/api/live/snapshot",
    "/api/pr-checks",
    "/api/search?q=airline",
)


@pytest.mark.parametrize("path", _ENDPOINTS)
def test_envelope_shape(client, path):
    response = client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"success", "data", "error", "meta"}
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"] is not None
    meta = body["meta"]
    assert meta["simulated"] is True
    assert meta["data_source"] == "fixture"


def test_fixture_responses_are_always_marked_simulated(client):
    body = client.get("/api/runs/brief-12-step").json()
    assert body["meta"]["simulated"] is True


def test_security_headers_present(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_cors_allows_only_dev_origin(client):
    allowed = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"

    denied = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers
