"""Benchmark page: method comparison, heatmap, sankey, ablation, dataset explorer."""

from __future__ import annotations


def test_benchmark_methods_all_present(client):
    body = client.get("/api/benchmark").json()["data"]
    methods = {m["method"] for m in body["methods"]}
    assert methods == {
        "bisect",
        "judge_all_at_once",
        "judge_step_by_step",
        "rerun_live",
        "no_control",
    }


def test_every_accuracy_has_a_ci(client):
    body = client.get("/api/benchmark").json()["data"]
    for method in body["methods"]:
        acc = method["accuracy"]
        assert acc["ci_low"] <= acc["value"] <= acc["ci_high"]


def test_heatmap_covers_all_fault_types(client):
    body = client.get("/api/benchmark").json()["data"]
    fault_types = {cell["fault_type"] for cell in body["heatmap"]}
    assert fault_types == {"wrong_value", "missing_field", "stale_record", "tool_error"}


def test_flaky_ablation_difference_has_ci(client):
    body = client.get("/api/benchmark").json()["data"]
    diff = body["flaky_ablation"]["difference"]
    assert diff["ci_low"] <= diff["value"] <= diff["ci_high"]


def test_sankey_labels_are_valid(client):
    body = client.get("/api/benchmark").json()["data"]
    assert {flow["label"] for flow in body["sankey"]} <= {"exact", "earlier", "later", "none"}


def test_dataset_pagination(client):
    body = client.get("/api/dataset?limit=10&page=1").json()
    assert body["meta"]["total"] > 0
    assert len(body["data"]["entries"]) <= 10


def test_dataset_entries_have_split(client):
    body = client.get("/api/dataset?limit=200").json()["data"]["entries"]
    assert all(e["split"] in ("dev", "test") for e in body)
