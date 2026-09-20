"""Deterministic figures for `docs/report.md`.

Byte-identical run to run: the `Agg` backend, a fixed DPI, fixed fonts (the
default DejaVu family, shipped with matplotlib so it does not depend on the
machine's font cache), SVG output with no timestamp in its metadata, and no
randomness anywhere in these functions. `render.py` is the only caller and
always saves through `save_deterministic`.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

DPI = 100
plt.rcParams["svg.fonttype"] = "path"  # embed glyph outlines, not font names
plt.rcParams["font.family"] = "DejaVu Sans"
# Without a fixed salt, matplotlib derives clip-path/marker element ids from
# object identity, which differs run to run and breaks the byte-identical
# reproduce check for no reason connected to the data.
plt.rcParams["svg.hashsalt"] = "bisect-p8-report"

#: Measured recall@m is confirmed by re-running suspects; beyond m=3 it is
#: the judge's ranking alone (`recall_provenance` in `p5_summary.json`).
MEASURED_TO_M = 3

_METHOD_COLOR = {
    "bisect": "#D08A12",  # amber -> blame, matches the shipped palette
    "judge_all_at_once": "#8B6EE8",  # violet -> judge
    "judge_step_by_step": "#5A4A9E",
}


def save_deterministic(fig: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", dpi=DPI, metadata={"Date": None, "Creator": None})
    plt.close(fig)


def figure_pending(message: str) -> Figure:
    """A placeholder figure for the primary (test-split) section before the
    test split has run — never silently substitutes dev data into a figure
    the report presents as the primary result."""
    fig, ax = plt.subplots(figsize=(6.4, 2.4))
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True, fontsize=11)
    fig.tight_layout()
    return fig


def figure_recall_curve(summary: dict[str, Any]) -> Figure:
    """recall@m per method; a dashed vertical line marks where measurement stops."""
    recall = summary.get("recall") or {}
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ms = list(range(1, 11))
    for method, curve in recall.items():
        values = [curve.get(str(m), curve.get(m)) for m in ms]
        measured_x = [m for m in ms if m <= MEASURED_TO_M]
        measured_y = values[: len(measured_x)]
        judge_only_x = [m for m in ms if m >= MEASURED_TO_M]
        judge_only_y = values[len(measured_x) - 1 :]
        color = _METHOD_COLOR.get(method, "#4CC9F0")
        ax.plot(measured_x, measured_y, marker="o", color=color, label=f"{method} (measured)")
        ax.plot(judge_only_x, judge_only_y, marker="o", linestyle="--", color=color, alpha=0.6)
    ax.axvline(MEASURED_TO_M, color="#888888", linestyle=":", linewidth=1)
    ax.set_xlabel("m (shortlist size)")
    ax.set_ylabel("recall@m")
    ax.set_ylim(0.0, 1.05)
    ax.set_xticks(ms)
    ax.set_title("recall@m — solid: measured (re-run), dashed: judge ranking only")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig


def figure_cost(summary: dict[str, Any]) -> Figure:
    """Cost per diagnosis by method, and the (m+1)*N cost curve with the chosen point."""
    fig, (ax_bar, ax_curve) = plt.subplots(1, 2, figsize=(9.6, 4.0))

    methods = summary.get("methods") or ()
    names = [row["method"] for row in methods]
    calls = [row.get("mean_calls", 0.0) for row in methods]
    colors = [_METHOD_COLOR.get(n, "#4CC9F0") for n in names]
    ax_bar.bar(names, calls, color=colors)
    ax_bar.set_ylabel("mean calls per diagnosis")
    ax_bar.set_title("cost per diagnosis")
    ax_bar.tick_params(axis="x", rotation=30)

    ns = list(range(2, 21, 2))
    for m, style in ((1, ":"), (3, "-"), (6, "--")):
        cost = [(m + 1) * n for n in ns]
        ax_curve.plot(ns, cost, style, label=f"m={m}", color="#1FA2C8")
    ax_curve.scatter([16], [(3 + 1) * 16], color="#D08A12", zorder=5, label="chosen: m=3, N=16")
    ax_curve.set_xlabel("N (re-runs per arm)")
    ax_curve.set_ylabel("forks per diagnosis, (m+1) x N")
    ax_curve.set_title("cost curve")
    ax_curve.legend(fontsize=8)

    fig.tight_layout()
    return fig
