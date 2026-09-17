"""Tests for the shared gate-evidence writer.

A gate's evidence document is generated from the same criteria the gate
just evaluated, so the numbers in `docs/gates/*.md` cannot drift from the
numbers that produced the verdict.
"""

from __future__ import annotations

import pytest
from scripts.gates.evidence import (
    current_commit,
    format_evidence,
    last_commit_for,
    render_table,
)


class _Criterion:
    def __init__(self, name: str, passed: bool, detail: str) -> None:
        self.name = name
        self.passed = passed
        self.detail = detail


PASSING = [_Criterion("runs", True, "20 recorded runs"), _Criterion("state", True, "100.0%")]
FAILING = [_Criterion("runs", True, "20 recorded runs"), _Criterion("state", False, "98.1%")]


def _evidence(criteria, **overrides) -> str:
    kwargs = dict(
        gate="P1",
        title="record and snapshot",
        script="scripts/gates/p1.py",
        criteria=criteria,
        gate_text="20 recorded runs; restoring any step reproduces its recorded DB hash.",
        commands=["uv run python scripts/gates/p1.py"],
        provenance={"scripts/gates/p1.py": "abc1234 feat(gates): P1"},
        sections={},
        commit="deadbee",
    )
    kwargs.update(overrides)
    return format_evidence(**kwargs)


def test_a_passing_gate_says_pass_and_names_the_commit():
    text = _evidence(PASSING)

    assert "**Verdict: PASS**" in text
    assert "`deadbee`" in text


def test_a_failing_gate_says_failed():
    """A gate that failed must say so in the first line a reader sees."""
    text = _evidence(FAILING)

    assert "**Verdict: FAILED**" in text
    assert "PASS**" not in text.split("\n")[2]


def test_every_criterion_appears_with_its_own_verdict():
    text = _evidence(FAILING)

    assert "| `runs` | PASS | 20 recorded runs |" in text
    assert "| `state` | FAILED | 98.1% |" in text


def test_the_pre_registered_gate_text_is_quoted():
    text = _evidence(PASSING)

    assert "> 20 recorded runs; restoring any step reproduces its recorded DB hash." in text


def test_the_commands_are_reproducible_verbatim():
    text = _evidence(PASSING, commands=["uv run bisect record --tasks 0-19", "uv run pytest"])

    assert "uv run bisect record --tasks 0-19" in text
    assert "uv run pytest" in text


def test_provenance_names_the_commit_of_each_source():
    text = _evidence(PASSING)

    assert "| `scripts/gates/p1.py` | abc1234 feat(gates): P1 |" in text


def test_extra_sections_are_rendered_in_order():
    text = _evidence(PASSING, sections={"Calls": "a table", "Stats": "another"})

    assert text.index("## Calls") < text.index("## Stats")
    assert "a table" in text and "another" in text


def test_the_title_names_the_gate_and_its_phase():
    text = _evidence(PASSING)

    assert text.startswith("# P1 gate — record and snapshot")


def test_the_generator_says_how_to_regenerate_the_file():
    text = _evidence(PASSING)

    assert "scripts/gates/p1.py --write-evidence" in text


# ---- the small helpers ----


def test_render_table_writes_a_header_and_a_row_per_entry():
    table = render_table(("Model", "Calls"), [("a/b", "12"), ("c/d", "3")])

    assert table.splitlines()[0] == "| Model | Calls |"
    assert "| `a/b` | 12 |" not in table  # values are not quoted for the caller
    assert "| a/b | 12 |" in table


def test_render_table_of_nothing_says_so_rather_than_emitting_an_empty_table():
    assert "none" in render_table(("Model", "Calls"), []).lower()


def test_current_commit_is_a_short_sha():
    commit = current_commit()

    assert commit != "unknown"
    assert 6 <= len(commit) <= 12


def test_last_commit_for_a_tracked_file_names_its_commit():
    assert last_commit_for("pyproject.toml") != "uncommitted"


def test_last_commit_for_an_untracked_path_says_uncommitted():
    assert last_commit_for("no/such/file/anywhere.txt") == "uncommitted"


@pytest.mark.parametrize("passed", [True, False])
def test_the_verdict_matches_every_criterion_not_just_the_first(passed):
    criteria = [_Criterion("a", True, "ok"), _Criterion("b", passed, "maybe")]

    text = _evidence(criteria)

    assert ("PASS" if passed else "FAILED") in text.split("\n")[2]
