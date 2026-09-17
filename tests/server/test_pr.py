"""PR-checks page: list + detail, regression vs no-op mix, rendered comment."""

from __future__ import annotations


def test_pr_checks_list_has_six(client):
    body = client.get("/api/pr-checks").json()["data"]
    assert len(body) == 6


def test_pr_checks_has_three_regressions(client):
    body = client.get("/api/pr-checks").json()["data"]
    assert sum(1 for c in body if c["is_regression"]) == 3


def test_pr_check_detail_has_comment_markdown(client):
    check_id = client.get("/api/pr-checks").json()["data"][0]["check_id"]
    body = client.get(f"/api/pr-checks/{check_id}").json()["data"]
    assert "Bisect" in body["comment_markdown"]
    assert len(body["scenarios"]) > 0


def test_pr_check_detail_unknown_is_404(client):
    response = client.get("/api/pr-checks/does-not-exist")
    assert response.status_code == 404


def test_regression_check_has_decisive_step(client):
    checks = client.get("/api/pr-checks").json()["data"]
    regression_id = next(c["check_id"] for c in checks if c["is_regression"])
    body = client.get(f"/api/pr-checks/{regression_id}").json()["data"]
    assert body["decisive_step_head"] is not None
