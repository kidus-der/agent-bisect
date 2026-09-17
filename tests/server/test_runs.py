"""Run list / run detail endpoints: filters, sort, pagination, 404s, step detail."""

from __future__ import annotations


def test_list_runs_default_page(client):
    body = client.get("/api/runs?limit=10").json()
    assert body["meta"]["limit"] == 10
    assert body["meta"]["total"] >= 260
    assert len(body["data"]["runs"]) == 10


def test_list_runs_filters_by_domain(client):
    body = client.get("/api/runs?domain=airline&limit=200").json()
    assert all(r["domain"] == "airline" for r in body["data"]["runs"])


def test_list_runs_filters_by_outcome(client):
    body = client.get("/api/runs?outcome=fail&limit=200").json()
    assert all(r["outcome"] == "fail" for r in body["data"]["runs"])


def test_list_runs_sort_descending(client):
    body = client.get("/api/runs?sort=-n_steps&limit=5").json()
    sizes = [r["n_steps"] for r in body["data"]["runs"]]
    assert sizes == sorted(sizes, reverse=True)


def test_list_runs_pagination_is_stable(client):
    page1 = client.get("/api/runs?limit=20&page=1").json()["data"]["runs"]
    page2 = client.get("/api/runs?limit=20&page=2").json()["data"]["runs"]
    ids1 = {r["run_id"] for r in page1}
    ids2 = {r["run_id"] for r in page2}
    assert ids1.isdisjoint(ids2)


def test_limit_over_max_is_rejected(client):
    assert client.get("/api/runs?limit=500").status_code == 422


def test_unknown_run_is_404(client):
    response = client.get("/api/runs/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"


def test_run_id_with_path_traversal_characters_is_rejected(client):
    response = client.get("/api/runs/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (404, 422)


def test_brief_run_detail_matches_worked_example(client):
    body = client.get("/api/runs/brief-12-step").json()["data"]
    assert body["planted_step"] == 7
    assert len(body["steps"]) == 12
    assert body["estimate"]["blamed_step"] == 7


def test_brief_run_step_payload_shows_nm1vx1(client):
    body = client.get("/api/runs/brief-12-step/steps/7").json()["data"]
    assert body["tool_result"]["reservation_id"] == "NM1VX1"


def test_brief_run_intervention_diff_shows_replacement(client):
    body = client.get("/api/runs/brief-12-step/steps/7/intervention-diff").json()["data"]
    assert body["original_tool_result"]["reservation_id"] == "NM1VX1"
    assert body["replaced_tool_result"]["reservation_id"] == "ZFA04Y"


def test_step_payload_unknown_step_is_404(client):
    response = client.get("/api/runs/brief-12-step/steps/999")
    assert response.status_code == 404


def test_zero_tested_steps_run_has_no_blame(client):
    body = client.get("/api/runs/run-edge-zero-tested").json()["data"]
    assert body["estimate"] is None


def test_zero_tested_steps_run_blame_stripe_is_all_untested(client):
    runs = client.get("/api/runs?domain=airline&limit=200").json()["data"]["runs"]
    summary = next(r for r in runs if r["run_id"] == "run-edge-zero-tested")
    assert all(
        cell["tested"] is False and cell["effect"] is None for cell in summary["blame_stripe"]
    )


def test_no_clear_run_has_no_blamed_step(client):
    body = client.get("/api/runs/run-edge-no-clear").json()["data"]
    assert body["estimate"]["blamed_step"] is None


def test_sixty_step_run_has_sixty_steps(client):
    body = client.get("/api/runs/run-edge-60-step").json()["data"]
    assert len(body["steps"]) == 60


def test_unicode_step_payload_round_trips(client):
    body = client.get("/api/runs/run-edge-unicode/steps/1").json()["data"]
    assert "座席" in body["messages"][0]["content"]


def test_long_payload_step_is_long(client):
    body = client.get("/api/runs/run-edge-long-payload/steps/4").json()["data"]
    assert len(body["messages"][0]["content"]) > 1000


def test_reruns_matrix_available_for_tested_run(client):
    body = client.get("/api/runs/brief-12-step/reruns").json()["data"]
    assert len(body["reruns"]) > 0
    assert {"treated", "control"} <= {row["arm"] for row in body["reruns"]}


def test_rerun_steps_for_one_individual_rerun(client):
    reruns = client.get("/api/runs/brief-12-step/reruns").json()["data"]["reruns"]
    rerun_id = reruns[0]["rerun_id"]
    body = client.get(f"/api/runs/brief-12-step/reruns/{rerun_id}/steps").json()["data"]
    assert isinstance(body, list)
    assert len(body) > 0


def test_state_diff_for_mutating_step(client):
    # step 7 of brief-12-step is book_reservation, a mutating tool.
    body = client.get("/api/runs/brief-12-step/steps/7/state-diff").json()["data"]
    assert body["step_idx"] == 7
