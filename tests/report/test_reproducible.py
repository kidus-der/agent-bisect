"""Two consecutive report generations are byte-identical.

Runs entirely offline (the suite's `--disable-socket` default is enough; no
`live` marker needed) and never touches the committed `docs/report/` files —
figures are saved to a temp directory so this test cannot leave the working
tree dirty.
"""

from __future__ import annotations

from pathlib import Path

from scripts.report import figures, render


def test_table_fragments_are_byte_identical_across_two_builds() -> None:
    first = render.build_table_fragments()
    second = render.build_table_fragments()
    assert first == second
    assert first.keys(), "at least one table fragment should be produced"


def test_figures_are_byte_identical_across_two_builds(tmp_path: Path) -> None:
    from scripts.report import loaders

    summary_dev = loaders.load_p5_summary_dev()

    for name, build in (
        ("recall", lambda: figures.figure_recall_curve(summary_dev)),
        ("cost", lambda: figures.figure_cost(summary_dev)),
        ("pending", lambda: figures.figure_pending("{{P5_TEST}} pending")),
    ):
        first = tmp_path / f"{name}_1.svg"
        second = tmp_path / f"{name}_2.svg"
        figures.save_deterministic(build(), first)
        figures.save_deterministic(build(), second)
        assert first.read_bytes() == second.read_bytes(), f"{name} figure is not deterministic"


def test_markdown_files_reference_only_known_fragments() -> None:
    """Every `table:NAME` marker in a spliced file has a producer in render.py."""
    import re

    fragments = render.build_table_fragments()
    for path in render.SPLICE_TARGETS:
        text = path.read_text(encoding="utf-8")
        referenced = set(re.findall(r"table:([a-z0-9_]+)", text))
        missing = referenced - set(fragments)
        assert not missing, f"{path} references undefined table fragments: {missing}"
