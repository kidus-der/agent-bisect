#!/usr/bin/env python3
"""Regenerate every report table, figure and the spliced numbers in
`docs/report.md`, from committed inputs only.

    uv run python scripts/report/render.py

Writes:

- `docs/report/tables/*.md` — one file per table, plain Markdown fragments.
- `docs/report/figures/*.svg` — deterministic (see `figures.py`).
- `docs/report.md` — every `<!-- BEGIN table:NAME --> ... <!-- END table:NAME -->`
  region is replaced with the matching fragment's content, so a number in
  the prose can never drift from the table it came from.

Two consecutive runs produce byte-identical output (checked by
`tests/report/test_reproducible.py` and by `make reproduce`, which also runs
this under a blocked socket to enforce the offline claim).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.report import figures, loaders, tables  # noqa: E402

TABLES_DIR = REPO_ROOT / "docs" / "report" / "tables"
FIGURES_DIR = REPO_ROOT / "docs" / "report" / "figures"
REPORT_MD = REPO_ROOT / "docs" / "report.md"

_MARKER = re.compile(
    r"(<!-- BEGIN table:(?P<name>[a-z0-9_]+) -->\n).*?(\n<!-- END table:(?P=name) -->)",
    re.DOTALL,
)


def build_table_fragments() -> dict[str, str]:
    """Every table this package knows how to produce, by its marker name."""
    manifest = loaders.load_manifest()
    manifest_extended = loaders.load_manifest_extended()
    manifest_flaky = loaders.load_manifest_flaky()
    summary = loaders.load_p5_summary()
    items = loaders.load_p5_items()
    summary_dev = loaders.load_p5_summary_dev()
    items_dev = loaders.load_p5_items_dev()
    p4_gate = loaders.load_p4_gate()
    p4_power = loaders.load_p4_power_table()
    p5_power = loaders.load_p5_power_table()
    flaky_mech = loaders.load_flaky_mechanism()
    ledger = loaders.load_ledger_by_phase()

    is_test = tables.is_test_split(summary)

    def _test_only(build: Callable[[], str], reason: str) -> str:
        """The primary (test-split) section must never silently show dev data."""
        return build() if is_test else tables.pending(reason)

    no_test_yet = "No test-split summary yet."
    fragments: dict[str, str] = {
        # (a) accuracy, primary split (test once it exists; pending until then)
        "accuracy": _test_only(lambda: tables.table_accuracy(summary), no_test_yet),
        "gap": _test_only(lambda: tables.table_gap(summary), no_test_yet),
        "power_mde": tables.table_power_mde(p5_power),
        # dev split, diagnostic only, always real
        "accuracy_dev": tables.table_accuracy(summary_dev),
        "gap_dev": tables.table_gap(summary_dev),
        # (d)
        "by_position": _test_only(lambda: tables.table_by_position(summary), no_test_yet),
        "by_fault_type": _test_only(lambda: tables.table_by_fault_type(summary), no_test_yet),
        "by_position_dev": tables.table_by_position(summary_dev),
        "by_fault_type_dev": tables.table_by_fault_type(summary_dev),
        # (e)
        "per_item": _test_only(lambda: tables.table_per_item(items), "No test-split items yet."),
        "per_item_dev": tables.table_per_item(items_dev),
        # (f)
        "funnel": tables.table_funnel(manifest, manifest_extended, manifest_flaky),
        # (g)
        "p4": tables.table_p4(p4_gate, p4_power),
        # (h)
        "flaky_mechanism": tables.table_flaky_mechanism(flaky_mech),
        # (i)
        "calls_by_phase": tables.table_calls_by_phase(ledger),
    }
    return fragments


def write_table_files(fragments: dict[str, str]) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in fragments.items():
        (TABLES_DIR / f"{name}.md").write_text(content.rstrip() + "\n", encoding="utf-8")


def write_figures() -> None:
    summary = loaders.load_p5_summary()
    summary_dev = loaders.load_p5_summary_dev()
    is_test = tables.is_test_split(summary)
    pending_msg = (
        f"{tables.PENDING} — test split not yet run.\n"
        "See the dev split (diagnostic) figure below."
    )

    figures.save_deterministic(
        figures.figure_recall_curve(summary) if is_test else figures.figure_pending(pending_msg),
        FIGURES_DIR / "recall_curve.svg",
    )
    figures.save_deterministic(
        figures.figure_cost(summary) if is_test else figures.figure_pending(pending_msg),
        FIGURES_DIR / "cost.svg",
    )
    figures.save_deterministic(
        figures.figure_recall_curve(summary_dev), FIGURES_DIR / "recall_curve_dev.svg"
    )
    figures.save_deterministic(figures.figure_cost(summary_dev), FIGURES_DIR / "cost_dev.svg")


def splice_report_md(fragments: dict[str, str]) -> None:
    """Replace every `<!-- BEGIN table:NAME -->...<!-- END table:NAME -->` region."""
    text = REPORT_MD.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        content = fragments.get(name)
        if content is None:
            raise KeyError(
                f"docs/report.md references table:{name}, which render.py does not produce"
            )
        begin, end = match.group(1), match.group(3)
        return f"{begin}{content.rstrip()}{end}"

    new_text, count = _MARKER.subn(_replace, text)
    referenced = set(re.findall(r"table:([a-z0-9_]+)", text))
    unused = set(fragments) - referenced
    if unused:
        sys.stderr.write(
            f"warning: unused table fragments not referenced in docs/report.md: {sorted(unused)}\n"
        )
    REPORT_MD.write_text(new_text, encoding="utf-8")
    sys.stdout.write(f"spliced {count} table region(s) into {REPORT_MD}\n")


def main() -> int:
    fragments = build_table_fragments()
    write_table_files(fragments)
    write_figures()
    splice_report_md(fragments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
