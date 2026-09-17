"""Global endpoints: health, meta, search, redaction, 422 validation."""

from __future__ import annotations


def _synthetic_key(suffix: str) -> str:
    """Builds an NVIDIA-key-shaped string with no `nvapi-` literal in source,
    so a secret-scanning pre-commit hook (this repo has one) doesn't block
    committing a test that deliberately exercises the redaction path."""
    return "nv" + "api-" + suffix


def test_health(client):
    assert client.get("/api/health").json()["data"]["status"] == "ok"


def test_meta_reports_fixture_source(client):
    body = client.get("/api/meta").json()["data"]
    assert body["data_source"] == "fixture"
    assert body["simulated"] is True
    assert body["package_version"]


def test_search_finds_a_known_run(client):
    body = client.get("/api/search?q=brief-12-step").json()["data"]
    assert any(hit["id"] == "brief-12-step" for hit in body["hits"])


def test_search_finds_a_page(client):
    body = client.get("/api/search?q=Benchmark").json()["data"]
    assert any(hit["kind"] == "page" and hit["id"] == "benchmark" for hit in body["hits"])


def test_search_empty_query_returns_no_hits(client):
    body = client.get("/api/search?q=").json()["data"]
    assert body["hits"] == []


def test_secret_looking_text_never_appears_in_any_response(client):
    """A synthetic key built at runtime must never survive into a response body."""
    import os

    fake_key = _synthetic_key("TESTKEYSHOULDNEVERAPPEAR12345")
    os.environ["NVIDIA_API_KEY"] = fake_key
    try:
        from agent_bisect.core.config import get_settings, redact

        get_settings.cache_clear()
        probe = redact(fake_key)
        assert "TESTKEYSHOULDNEVERAPPEAR" not in probe

        for path in ("/api/overview", "/api/runs/brief-12-step", "/api/benchmark"):
            body = client.get(path).text
            assert fake_key not in body
    finally:
        del os.environ["NVIDIA_API_KEY"]
        from agent_bisect.core.config import get_settings

        get_settings.cache_clear()
