"""Table-building logic: the parts with a fact to get wrong."""

from __future__ import annotations

from scripts.report import tables


def test_pending_fragment_carries_the_literal_placeholder_token() -> None:
    fragment = tables.pending("some reason")
    assert tables.PENDING in fragment
    assert "some reason" in fragment


def test_is_test_split_reads_the_summary_config() -> None:
    assert tables.is_test_split({"config": {"split": "test"}})
    assert not tables.is_test_split({"config": {"split": "dev"}})
    assert not tables.is_test_split({"config": {}})
    assert not tables.is_test_split({})


def test_table_per_item_pivots_one_row_per_item_one_column_per_method() -> None:
    items = [
        {
            "item_id": "a-1",
            "domain": "airline",
            "fault_type": "tool_error",
            "position_bucket": "early",
            "planted_step": 4,
            "method": "bisect",
            "predicted_step": 4,
            "verdict": "exact",
            "shortlist_hit": True,
        },
        {
            "item_id": "a-1",
            "domain": "airline",
            "fault_type": "tool_error",
            "position_bucket": "early",
            "planted_step": 4,
            "method": "judge_all_at_once",
            "predicted_step": None,
            "verdict": "none",
            "shortlist_hit": False,
        },
    ]
    out = tables.table_per_item(items)
    lines = out.strip().splitlines()
    # header + separator + exactly one data row for the one item
    assert len(lines) == 3
    assert "a-1" in lines[2]
    assert "4 / exact" in lines[2]
    assert "none / none" in lines[2]


def test_table_per_item_empty_is_a_pending_fragment() -> None:
    out = tables.table_per_item([])
    assert tables.PENDING in out


def test_table_accuracy_empty_methods_is_pending() -> None:
    out = tables.table_accuracy({"methods": []})
    assert tables.PENDING in out


def test_table_gap_missing_is_pending() -> None:
    out = tables.table_gap({})
    assert tables.PENDING in out
