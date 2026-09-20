"""Markdown table fragments for `docs/report.md`.

Every function takes already-loaded data (see `loaders.py`) and returns a
Markdown string with no trailing newline surprises — `render.py` owns
writing files and splicing fragments into `docs/report.md`. Reuses
`scripts.gates.evidence.render_table` rather than a second table
formatter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gates.evidence import render_table  # noqa: E402

#: Literal token left in a fragment when the test split has not run yet.
PENDING = "{{P5_TEST}}"

_METHOD_LABEL = {
    "bisect": "Bisect",
    "judge_all_at_once": "Judge, all-at-once",
    "judge_step_by_step": "Judge, step-by-step",
    "no_control": "No-control (derived)",
    "rerun_live": "Re-run-live",
    "snapshot": "Snapshot",
    "no_snapshot": "No-snapshot (rerun-live baseline)",
}


def _label(method: str) -> str:
    return _METHOD_LABEL.get(method, method)


def _pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def pending(reason: str) -> str:
    """The fragment left in a test-split table until the test split has run."""
    return (
        f"_{PENDING} — test split not yet run. {reason} "
        "Re-run `make reproduce` once P5 STAGE B lands to fill this table in._"
    )


def _pending_fragment(reason: str) -> str:
    return pending(reason)


def is_test_split(summary: dict[str, Any]) -> bool:
    return (summary.get("config") or {}).get("split") == "test"


# ---- (a) accuracy table ------------------------------------------------


def table_accuracy(summary: dict[str, Any]) -> str:
    """Per-method accuracy with Wilson CIs and mean cost."""
    rows = []
    for row in summary.get("methods") or ():
        acc = row["accuracy"]
        rows.append(
            (
                _label(row["method"]),
                str(row["n"]),
                f"{acc['value']:.3f}",
                f"[{acc['ci_low']:.3f}, {acc['ci_high']:.3f}]",
                f"{row.get('mean_calls', 0):.1f}",
                f"{row.get('mean_reruns', 0):.1f}",
            )
        )
    if not rows:
        return _pending_fragment("No method rows in the summary.")
    return render_table(
        ("Method", "n", "Accuracy", "95% Wilson CI", "Mean calls", "Mean re-runs"), rows
    )


def table_gap(summary: dict[str, Any]) -> str:
    """The headline gap: Bisect vs the best judge, with its paired-bootstrap CI."""
    gap = summary.get("gap")
    if not gap:
        return _pending_fragment("No gap in the summary.")
    rows = [
        (
            _label(gap.get("comparator", "")),
            f"{gap['points']:+.1f} pts",
            f"[{gap['ci_low'] * 100:+.1f}, {gap['ci_high'] * 100:+.1f}] pts",
            "yes" if gap.get("ci_above_zero") else "no",
            "yes" if gap.get("clears_fifteen_points") else "no",
            str(gap.get("resamples", "")),
        )
    ]
    return render_table(
        (
            "Comparator",
            "Gap (points)",
            "95% paired-bootstrap CI",
            "CI entirely above 0",
            "Clears the +15pt bar",
            "Resamples",
        ),
        rows,
    )


def table_power_mde(power: dict[str, Any]) -> str:
    """The pre-computed power/MDE line: what this n could resolve, before spending."""
    strict = power["power_by_true_gap"]["strict"]
    rows = [
        (
            f"+{row['true_gap_points']} pts",
            f"{row['judge_0.10']:.2f}",
            f"{row['judge_0.25']:.2f}",
            f"{row['judge_0.40']:.2f}",
        )
        for row in strict
    ]
    table = render_table(
        ("True gap", "Power (judge base 0.10)", "Power (0.25)", "Power (0.40)"), rows
    )
    smallest = power["smallest_clearing_result"]
    note = (
        f"\n\n_Strict test split: n={power['strict_test_items']} items, "
        f"{power['strict_test_clusters']} task clusters. The smallest observed result that "
        f"clears the gate's CI is {smallest['description']} "
        f"(CI [{smallest['ci_low']:+.3f}, {smallest['ci_high']:+.3f}]). "
        f"Source: `{power['source']}`, reproduce with `{power['reproduce']}`._"
    )
    return table + note


# ---- (d) accuracy by fault type and position ---------------------------


def table_by_position(summary: dict[str, Any]) -> str:
    rows = [
        (_label(r["method"]), r["position"], str(r["n"]), f"{r['accuracy']:.3f}")
        for r in summary.get("by_position") or ()
    ]
    if not rows:
        return _pending_fragment("No by-position rows in the summary.")
    return render_table(("Method", "Position", "n", "Accuracy"), rows)


def table_by_fault_type(summary: dict[str, Any]) -> str:
    rows = [
        (_label(r["method"]), r["fault_type"], str(r["n"]), f"{r['accuracy']:.3f}")
        for r in summary.get("heatmap") or ()
    ]
    if not rows:
        return _pending_fragment("No heatmap rows in the summary.")
    return render_table(("Method", "Fault type", "n", "Accuracy"), rows)


# ---- (e) per-item table --------------------------------------------------


def table_per_item(items: list[dict[str, Any]]) -> str:
    """One row per item, one column per method: predicted step and verdict."""
    if not items:
        return _pending_fragment("No item rows.")
    by_item: dict[str, dict[str, Any]] = {}
    methods_seen: list[str] = []
    for row in items:
        item_id = row["item_id"]
        by_item.setdefault(
            item_id,
            {
                "domain": row["domain"],
                "fault_type": row["fault_type"],
                "position_bucket": row["position_bucket"],
                "planted_step": row["planted_step"],
                "methods": {},
            },
        )
        by_item[item_id]["methods"][row["method"]] = row
        if row["method"] not in methods_seen:
            methods_seen.append(row["method"])

    header = ["Item", "Domain", "Fault", "Position", "Planted step"]
    for method in methods_seen:
        header.append(f"{_label(method)} (predicted / verdict)")

    rows = []
    for item_id in sorted(by_item):
        entry = by_item[item_id]
        row_cells = [
            item_id,
            entry["domain"],
            entry["fault_type"],
            entry["position_bucket"],
            str(entry["planted_step"]),
        ]
        for method in methods_seen:
            m = entry["methods"].get(method)
            if m is None:
                row_cells.append("—")
                continue
            predicted = m.get("predicted_step")
            predicted_label = predicted if predicted is not None else "none"
            hit = "shortlisted" if m.get("shortlist_hit") else "not shortlisted"
            row_cells.append(f"{predicted_label} / {m['verdict']} ({hit})")
        rows.append(tuple(row_cells))
    return render_table(tuple(header), rows)


# ---- (f) dataset funnel --------------------------------------------------


def table_funnel(
    manifest: dict[str, Any], extended: dict[str, Any], flaky: dict[str, Any]
) -> str:
    counts = manifest["counts"]
    ext_counts = extended["counts"]
    flaky_counts = flaky["counts"]
    funnel_rows = [
        ("base runs attempted", str(counts["base_runs"])),
        ("stable (>= 0.75 over 4 re-runs)", str(counts["stable"])),
        ("unstable", str(counts["unstable"])),
        ("candidates tried", str(counts["candidate_kept"] + counts["candidate_not_flipped"])),
        ("candidates: not flipped (faulted pass > 0.25)", str(counts["candidate_not_flipped"])),
        ("candidates: repeated call before k (rejected)", str(counts["candidate_repeated_call"])),
        ("candidates: infrastructure-lost", str(counts["candidate_infra"])),
        ("kept (faulted pass <= 0.25 at N=4)", str(counts["candidate_kept"])),
    ]
    funnel = render_table(("Stage", "Count"), funnel_rows)

    size_rows = [
        (
            "strict (primary; P3 gate evaluated on this)",
            str(counts["items"]),
            str(counts["dev"]),
            str(counts["test"]),
        ),
        (
            "extended (secondary; faulted pass <= 0.50, post hoc)",
            str(ext_counts["items"]),
            str(ext_counts["dev"]),
            str(ext_counts["test"]),
        ),
        (
            "flaky world (unsplit; bounded, infra-limited attempt)",
            str(flaky_counts["items"]),
            "—",
            "—",
        ),
    ]
    sizes = render_table(("Manifest", "Items", "Dev", "Test"), size_rows)

    strata_rows = []
    for domain_fault, positions in _strata(manifest["items"]).items():
        for position, n in sorted(positions.items()):
            strata_rows.append((domain_fault, position, str(n)))
    strata = render_table(("Domain / fault type", "Position", "n"), strata_rows)

    return f"{funnel}\n\n**Manifest sizes**\n\n{sizes}\n\n**Strata (strict manifest)**\n\n{strata}"


def _strata(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for item in items:
        key = f"{item['domain']} / {item['fault_type']}"
        out.setdefault(key, {}).setdefault(item["position_bucket"], 0)
        out[key][item["position_bucket"]] += 1
    return dict(sorted(out.items()))


# ---- (g) P4 synthetic results -------------------------------------------


def table_p4(gate: dict[str, Any], power: dict[str, Any]) -> str:
    criteria_rows = [
        (c["name"], c["requirement"], f"{c['value']:.4f}", "PASS" if c["passed"] else "FAIL")
        for c in gate["criteria"]
    ]
    criteria = render_table(("Criterion", "Requirement", "Measured", "Result"), criteria_rows)

    found = gate["planted_step_found"]
    outcome = gate["outcome_counts"]
    detail_rows = [
        (
            "planted step found",
            f"{found['count']}/{gate['n_runs']} = {found['rate']:.4f}",
            f"[{found['ci_low']:.4f}, {found['ci_high']:.4f}]",
        ),
        (
            "outcome breakdown",
            f"earlier {outcome['earlier']} · later {outcome['later']} · none {outcome['none']}",
            "—",
        ),
    ]
    detail = render_table(("Measure", "Value", "95% CI"), detail_rows)

    power_header = ["control \\ treated"] + [
        k.split("_")[1] for k in next(iter(power["nominal_95"].values()))
    ]
    power_rows = []
    for control_key, row in power["nominal_95"].items():
        power_rows.append(
            tuple([control_key.split("_")[1]] + [f"{v:.3f}" for v in row.values()])
        )
    power_table = render_table(tuple(power_header), power_rows)

    return (
        f"{criteria}\n\n{detail}\n\n"
        f"**Power at N={power['n_per_arm']} per arm, delta={power['delta']} "
        "(exact enumeration, nominal 95% look)**\n\n"
        f"{power_table}\n\n"
        f"_Source: `{power['source']}`, reproduce with `{power['reproduce']}`._"
    )


# ---- (h) flaky-world mechanism -------------------------------------------


def table_flaky_mechanism(mech: dict[str, Any]) -> str:
    rows = [
        (arm["name"], arm["description"], _pct(arm["db_hash_reproduction_rate"], 0))
        for arm in mech["arms"]
    ]
    table = render_table(("Arm", "What it does", "DB-hash reproduction rate"), rows)
    note = (
        f"\n\n_Measured over {mech['runs_measured']} recorded runs and "
        f"{mech['tool_steps_measured']} tool steps, offline and deterministically "
        f"(`tests/test_tau2_flaky.py`). {mech['note']}_"
    )
    return table + note


# ---- (i) calls by phase --------------------------------------------------


def table_calls_by_phase(ledger: dict[str, Any]) -> str:
    rows = [(phase, str(n)) for phase, n in ledger["by_phase"].items()]
    rows.append(("**total**", f"**{ledger['total_calls']}**"))
    return render_table(("Phase", "Calls"), rows)
