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


def test_list_runs_default_kind_is_top_level_only(client):
    """Fixture mode has no fork concept -- every simulated run is top-level,
    so the new default (`kind=top`) must not drop any of them."""
    default_total = client.get("/api/runs?limit=1").json()["meta"]["total"]
    all_total = client.get("/api/runs?kind=all&limit=1").json()["meta"]["total"]
    assert default_total == all_total
    assert default_total >= 260


def test_list_runs_kind_reruns_is_empty_in_fixture_mode(client):
    body = client.get("/api/runs?kind=reruns&limit=200").json()
    assert body["meta"]["total"] == 0
    assert body["data"]["runs"] == []


def test_list_runs_kind_invalid_value_is_422(client):
    assert client.get("/api/runs?kind=not_a_real_kind").status_code == 422


def test_list_runs_sort_descending(client):
    body = client.get("/api/runs?sort=-n_steps&limit=5").json()
    sizes = [r["n_steps"] for r in body["data"]["runs"]]
    assert sizes == sorted(sizes, reverse=True)


def test_q_filter_matches_run_id_case_insensitive(client):
    body = client.get("/api/runs?q=BRIEF-12-step").json()["data"]
    assert {r["run_id"] for r in body["runs"]} == {"brief-12-step"}


def test_q_filter_matches_task_id(client):
    body = client.get("/api/runs?q=refund_after_cancellation&limit=200").json()["data"]
    assert "brief-12-step" in {r["run_id"] for r in body["runs"]}
    assert all(r["task_id"] == "refund_after_cancellation" for r in body["runs"])


def test_q_filter_matches_model_substring(client):
    body = client.get("/api/runs?q=nemotron&limit=200").json()["data"]
    assert len(body["runs"]) > 0
    assert all("nemotron" in r["model"] for r in body["runs"])


def test_q_filter_matches_a_tool_name_not_present_on_run_summary(client):
    """`update_reservation_baggages` lives on individual steps, not on
    `RunSummary` -- the filter has to reach into per-run tool names."""
    body = client.get("/api/runs?q=update_reservation_baggages&limit=200").json()["data"]
    assert "brief-12-step" in {r["run_id"] for r in body["runs"]}


def test_q_filter_excludes_non_matching_runs(client):
    body = client.get("/api/runs?q=no_such_run_or_tool_exists_zzz").json()
    assert body["data"]["runs"] == []
    assert body["meta"]["total"] == 0


def test_q_over_max_length_is_rejected(client):
    assert client.get(f"/api/runs?q={'a' * 101}").status_code == 422


def test_fault_type_filter_exact_match(client):
    body = client.get("/api/runs?fault_type=wrong_value&limit=200").json()["data"]
    assert len(body["runs"]) > 0
    assert all(r["fault_type"] == "wrong_value" for r in body["runs"])


def test_fault_type_filter_none_means_unplanted(client):
    body = client.get("/api/runs?fault_type=none&limit=200").json()["data"]
    assert len(body["runs"]) > 0
    assert all(r["fault_type"] is None for r in body["runs"])


def test_fault_type_invalid_value_is_422(client):
    assert client.get("/api/runs?fault_type=not_a_real_fault_type").status_code == 422


def test_meta_total_reflects_the_filtered_count(client):
    filtered_total = client.get("/api/runs?fault_type=wrong_value&limit=1").json()["meta"]["total"]
    unfiltered_total = client.get("/api/runs?limit=1").json()["meta"]["total"]
    assert 0 < filtered_total < unfiltered_total


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
    # With the built dashboard's static/SPA fallback mounted
    # (agent_bisect/server/static/), a path that traverses out of
    # `/api/runs/` before routing no longer reaches the `{run_id}` regex at
    # all -- it matches the SPA catch-all instead and gets a 200 with the
    # built index page. Either way, real filesystem content must never leak.
    assert response.status_code in (200, 404, 422)
    assert "root:" not in response.text


def test_brief_run_detail_matches_worked_example(client):
    body = client.get("/api/runs/brief-12-step").json()["data"]
    assert body["planted_step"] == 7
    assert len(body["steps"]) == 12
    assert body["estimate"]["blamed_step"] == 7


def test_run_estimate_carries_the_actual_estimator_config(client):
    """The Run detail page must not hard-code delta client-side -- the
    blame result carries the real SequentialConfig used to produce it."""
    body = client.get("/api/runs/brief-12-step").json()["data"]
    config = body["estimate"]["config"]
    assert config["delta"] == 0.10
    assert config["batch"] == 4
    assert config["max_n"] == 16
    assert config["conf"] == 0.95
    assert config["efficacy_boundary"] == "obf"
    assert config["control_mode"] == "shared"
    assert config["shortlist_m"] == 3  # docs/decisions/0001-preregistration.md


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


def test_recording_run_detail_has_no_fabricated_outcome(client):
    body = client.get("/api/runs/run-edge-recording-1").json()["data"]
    assert body["status"] == "recording"
    assert body["outcome"] is None
    assert body["reward"] is None


def test_status_filter_selects_only_recording_runs(client):
    body = client.get("/api/runs?status=recording&limit=200").json()["data"]["runs"]
    assert len(body) == 2
    assert {r["run_id"] for r in body} == {"run-edge-recording-1", "run-edge-recording-2"}
    assert all(r["outcome"] is None for r in body)


def test_outcome_filter_excludes_recording_runs(client):
    body = client.get("/api/runs?outcome=fail&limit=200").json()["data"]["runs"]
    assert len(body) > 0
    assert all(r["status"] == "complete" for r in body)


def test_search_reports_status_for_a_recording_run(client):
    body = client.get("/api/search?q=run-edge-recording-1").json()["data"]
    hit = next(h for h in body["hits"] if h["id"] == "run-edge-recording-1")
    assert hit["status"] == "recording"
