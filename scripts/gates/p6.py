#!/usr/bin/env python3
"""P6 gate: the dashboard, mechanically checked against what ships.

    uv run python scripts/gates/p6.py [--write-evidence]

Five criteria, from the P6 gate instruction ("P6 gate: Playwright e2e for
every page passes; axe 0 serious/critical; Lighthouse performance >= 90 and
accessibility >= 95 on Overview and Run detail; design evaluator score >=
8.5/10 on every page; screenshots in docs/screenshots/"):

1. **e2e** — every Playwright spec passes against the production build
   served by `bisect serve --fixture` (not the Vite dev server): `n/n`,
   0 unexpected, 0 flaky.
2. **axe** — 0 serious/critical violations, counted from the axe-titled
   specs inside that same run (every page, dark and light).
3. **Lighthouse** — desktop preset, median of 3 runs, performance >= 90 and
   accessibility >= 95 on Overview (`/`) and Run detail.
4. **design score** — every page >= 8.5/10, read from the design
   evaluator's own final table in `docs/design/review-log.md`. The gate
   does not re-score; it reads the verdict the evaluator already reached
   and reports it honestly, including a failure the evaluator recorded.
5. **screenshots** — the curated final set exists in
   `docs/screenshots/final/`.

Like every other gate, this one reads evidence that was already produced
(the e2e and Lighthouse runs, the evaluator's log) rather than re-running
tools with side effects (a live server, a browser) as an import-time
effect of grading. Producing that evidence is documented in
`docs/gates/P6.md`'s Commands section.

Prints PASS/FAIL per criterion, writes `<runs>/p6/gate.json`, exits
non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.gates.evidence import (  # noqa: E402
    current_commit,
    format_evidence,
    provenance_for,
    render_table,
)

DEFAULT_RUNS_DIR = REPO_ROOT / "runs" / "p6"
DEFAULT_REVIEW_LOG = REPO_ROOT / "docs" / "design" / "review-log.md"
DEFAULT_SCREENSHOTS_DIR = REPO_ROOT / "docs" / "screenshots" / "final"
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "docs" / "gates" / "P6.md"

MIN_PERFORMANCE = 90.0
MIN_ACCESSIBILITY = 95.0
MIN_DESIGN_SCORE = 8.5
LIGHTHOUSE_PAGES = ("overview", "run-detail")
#: The 12 curated shots task 1e asked for, copied fresh from the production build.
REQUIRED_SCREENSHOTS = (
    "overview-dark-1440.png",
    "overview-light-1440.png",
    "runs-dark-1440.png",
    "run-detail-dark-1440.png",
    "run-detail-rewind-dark-1440.png",
    "run-detail-light-1440.png",
    "benchmark-dark-1440.png",
    "live-dark-1440.png",
    "pr-check-detail-dark-1440.png",
    "palette-dark-1440.png",
    "run-detail-dark-390.png",
    "overview-dark-390.png",
)
EVIDENCE_SOURCES = (
    "scripts/gates/p6.py",
    "web/playwright.gate.config.ts",
    "web/e2e/capture/final-capture.ts",
    "docs/design/review-log.md",
    "agent_bisect/server/static/index.html",
)


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def report(self) -> None:
        print(f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def _all_specs(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Every spec in a Playwright JSON report, flattened out of its `describe` nesting."""

    def walk(suite: dict[str, Any]) -> list[dict[str, Any]]:
        specs = list(suite.get("specs", ()))
        for sub in suite.get("suites", ()):
            specs.extend(walk(sub))
        return specs

    return [spec for suite in report.get("suites", ()) for spec in walk(suite)]


def check_e2e(report_path: Path) -> Criterion:
    """Criterion 1: every Playwright spec passes against the production build."""
    report = _load_json(report_path)
    if report is None:
        return Criterion("e2e", False, f"no readable report at {report_path}")
    stats = report.get("stats", {})
    expected = int(stats.get("expected", 0))
    unexpected = int(stats.get("unexpected", 0))
    flaky = int(stats.get("flaky", 0))
    skipped = int(stats.get("skipped", 0))
    total = expected + unexpected
    passed = total > 0 and unexpected == 0 and flaky == 0
    return Criterion(
        name="e2e",
        passed=passed,
        detail=(
            f"{expected}/{total} passed, {unexpected} unexpected, "
            f"{flaky} flaky, {skipped} skipped"
        ),
        data={"expected": expected, "unexpected": unexpected, "flaky": flaky, "skipped": skipped},
    )


def check_axe(report_path: Path) -> Criterion:
    """Criterion 2: 0 serious/critical axe violations, counted from the same e2e run.

    Every axe check is itself a Playwright test that asserts its blocking
    (serious/critical) violation list is empty (see e.g. `overview.spec.ts`'s
    per-theme axe tests) -- a failure here already failed criterion 1, so this
    criterion reports how many such checks ran and that all of them passed.
    """
    report = _load_json(report_path)
    if report is None:
        return Criterion("axe", False, f"no readable report at {report_path}")
    specs = _all_specs(report)
    axe_specs = [spec for spec in specs if "axe violations" in spec.get("title", "")]
    failing = [
        spec["title"]
        for spec in axe_specs
        if not all(test.get("status") == "expected" for test in spec.get("tests", ()))
    ]
    passed = len(axe_specs) > 0 and not failing
    detail = (
        f"{len(axe_specs) - len(failing)}/{len(axe_specs)} axe checks passed, "
        "0 serious/critical violations"
    )
    if failing:
        detail = f"{len(failing)} axe check(s) failed: {', '.join(failing)}"
    return Criterion(
        name="axe",
        passed=passed,
        detail=detail,
        data={"axe_checks": len(axe_specs), "failing": failing},
    )


def _lighthouse_scores(lighthouse_dir: Path, page: str) -> list[tuple[float, float]]:
    """`(performance, accessibility)` percentages for every numbered run of `page`."""
    scores: list[tuple[float, float]] = []
    for path in sorted(lighthouse_dir.glob(f"{page}-*.report.json")):
        report = _load_json(path)
        if report is None:
            continue
        categories = report.get("categories", {})
        perf = categories.get("performance", {}).get("score")
        a11y = categories.get("accessibility", {}).get("score")
        if perf is None or a11y is None:
            continue
        scores.append((perf * 100.0, a11y * 100.0))
    return scores


def check_lighthouse(lighthouse_dir: Path, page: str) -> Criterion:
    """Criterion 3, one page at a time: median performance >= 90, accessibility >= 95."""
    runs = _lighthouse_scores(lighthouse_dir, page)
    if not runs:
        return Criterion(f"lighthouse:{page}", False, f"no Lighthouse reports for {page}")
    perf_median = statistics.median(perf for perf, _ in runs)
    a11y_median = statistics.median(a11y for _, a11y in runs)
    passed = perf_median >= MIN_PERFORMANCE and a11y_median >= MIN_ACCESSIBILITY
    return Criterion(
        name=f"lighthouse:{page}",
        passed=passed,
        detail=(
            f"performance median {perf_median:.0f} (need >= {MIN_PERFORMANCE:.0f}), "
            f"accessibility median {a11y_median:.0f} (need >= {MIN_ACCESSIBILITY:.0f}), "
            f"n={len(runs)}"
        ),
        data={
            "performance_runs": [perf for perf, _ in runs],
            "accessibility_runs": [a11y for _, a11y in runs],
            "performance_median": perf_median,
            "accessibility_median": a11y_median,
        },
    )


_SCORE_ROW = re.compile(
    r"^\|\s*(?P<page>[^|]+?)\s*\|\s*\*\*(?P<score>[\d.]+)\*\*\s*\|\s*(?P<at_bar>yes|no)\s*\|"
)


def _final_scores(review_log: Path) -> list[tuple[str, float, bool]]:
    """Rows of the evaluator's own "Final scores" table: `(page, score, at_bar)`."""
    text = review_log.read_text(encoding="utf-8")
    marker = "### Final scores"
    start = text.find(marker)
    if start == -1:
        return []
    rows: list[tuple[str, float, bool]] = []
    for line in text[start:].splitlines():
        match = _SCORE_ROW.match(line)
        if match:
            rows.append((match["page"], float(match["score"]), match["at_bar"] == "yes"))
    return rows


def check_design_scores(review_log: Path) -> Criterion:
    """Criterion 4: every page >= 8.5, read from the evaluator's own final table.

    The evaluator's design loop is closed (max 6 rounds reached); this gate
    does not re-score anything, and reports a recorded miss as FAILED rather
    than rounding it up or excluding it.
    """
    rows = _final_scores(review_log)
    if not rows:
        return Criterion("design_score", False, f"no final scores table found in {review_log}")
    failing = [(page, score) for page, score, at_bar in rows if not at_bar]
    passed = not failing
    detail = (
        f"all {len(rows)} pages >= {MIN_DESIGN_SCORE}"
        if passed
        else f"{len(failing)}/{len(rows)} page(s) below {MIN_DESIGN_SCORE}: "
        + ", ".join(f"{page} {score}" for page, score in failing)
    )
    return Criterion(
        name="design_score",
        passed=passed,
        detail=detail,
        data={
            "scores": [
                {"page": page, "score": score, "at_bar": at_bar} for page, score, at_bar in rows
            ]
        },
    )


def check_screenshots(screenshots_dir: Path) -> Criterion:
    """Criterion 5: the curated final set exists."""
    missing = [name for name in REQUIRED_SCREENSHOTS if not (screenshots_dir / name).exists()]
    passed = not missing
    shown = (
        screenshots_dir.relative_to(REPO_ROOT)
        if screenshots_dir.is_relative_to(REPO_ROOT)
        else screenshots_dir
    )
    detail = (
        f"all {len(REQUIRED_SCREENSHOTS)} curated screenshots present in {shown}"
        if passed
        else f"missing {len(missing)}: {', '.join(missing)}"
    )
    return Criterion("screenshots", passed, detail, data={"missing": missing})


def run_gate(
    runs_dir: Path = DEFAULT_RUNS_DIR,
    review_log: Path = DEFAULT_REVIEW_LOG,
    screenshots_dir: Path = DEFAULT_SCREENSHOTS_DIR,
) -> list[Criterion]:
    e2e_report = runs_dir / "e2e-report.json"
    lighthouse_dir = runs_dir / "lighthouse"
    return [
        check_e2e(e2e_report),
        check_axe(e2e_report),
        *(check_lighthouse(lighthouse_dir, page) for page in LIGHTHOUSE_PAGES),
        check_design_scores(review_log),
        check_screenshots(screenshots_dir),
    ]


def write_report(runs_dir: Path, criteria: list[Criterion]) -> Path:
    path = runs_dir / "gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "gate": "P6",
                "passed": all(criterion.passed for criterion in criteria),
                "criteria": [
                    {
                        "name": criterion.name,
                        "passed": criterion.passed,
                        "detail": criterion.detail,
                        **criterion.data,
                    }
                    for criterion in criteria
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return path


def _design_scores_section(criteria: list[Criterion]) -> str:
    scores = next((c.data["scores"] for c in criteria if c.name == "design_score"), [])
    rows = [
        (row["page"], f"{row['score']:.1f}", "yes" if row["at_bar"] else "no") for row in scores
    ]
    table = render_table(("Page", "Score", "At the bar (>= 8.5)"), rows)
    return (
        f"{table}\n\n"
        "Six of seven pages clear the 8.5 bar. PR checks is 0.1 short, held there by a "
        "390px defect the evaluator found in round 6: `ScenarioTable` dropped every "
        "numeric column at that width, leaving a bar with no number on it. The defect "
        "was fixed afterwards (`2badc16`, `17de8f6`) but the design loop had already "
        "reached its pre-registered 6-round cap, so the fix is **not re-scored** -- "
        "reported here as a known-fixed defect on a FAILED criterion, not rounded up."
    )


def _static_dir_size(static_dir: Path) -> tuple[int, int]:
    """(total bytes, count) of everything under the built dashboard."""
    files = [p for p in static_dir.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files)


def _packaging_section(static_dir: Path) -> str:
    total_bytes, count = _static_dir_size(static_dir)
    return (
        f"Built dashboard: {total_bytes / 1024:.0f} KiB across {count} files under "
        f"`{static_dir.relative_to(REPO_ROOT)}` (committed; see `git log -1 -- "
        f"{static_dir.relative_to(REPO_ROOT)}`), produced by `make web` "
        "(`cd web && npm run build`; `vite.config.ts`'s `build.outDir` already points "
        "there).\n\n"
        "Verified with `uv build --wheel` that the wheel bundles it: "
        "`agent_bisect/server/static/**` is present under `agent_bisect/server/` "
        "because `[tool.hatch.build.targets.wheel] packages = [\"agent_bisect\"]` walks "
        "the package directory as it exists on disk, not filtered by `.gitignore` -- no "
        "pyproject.toml change was needed. `data/fixtures/` is not needed at runtime: "
        "`FixtureRepository` builds its bundle in memory from `build_bundle(seed)` "
        "(`agent_bisect/server/fixture_repository.py`), no filesystem read.\n\n"
        "Install proof, in a clean venv (`uv venv` + `uv pip install <repo path>`, not "
        "`uv tool install` itself, to avoid touching the user's global tool list): "
        "`bisect --help` lists all commands; `bisect doctor --json` runs to completion "
        "(warns about the vendored tau2 data directory not being on `TAU2_DATA_DIR` -- "
        "a pre-existing gap outside P6's scope, unrelated to the dashboard); "
        "`bisect serve --fixture --port <port>` then answers `GET /api/health` and "
        "`GET /api/meta`, `GET /` returns the SPA's `index.html`, and a hashed asset "
        "under `/assets/` returns 200 with `etag`/`last-modified` validators. No `web/` "
        "or `node_modules/` directory exists in that venv at any point. Installing the "
        "**wheel alone** outside the source tree resolves `tau2` from PyPI instead of "
        "the vendored `vendor/tau2-bench` (`[tool.uv.sources]` only applies when uv "
        "resolves the project's own dependencies from its `pyproject.toml`) -- not "
        "what `uv tool install .` does, and out of scope for a project that is not "
        "published to a real index (docs/decisions/0003-tau2-pin.md)."
    )


def write_evidence(criteria: list[Criterion], path: Path = DEFAULT_EVIDENCE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        format_evidence(
            gate="P6",
            title="dashboard: e2e, axe, Lighthouse, design score, release build",
            script="scripts/gates/p6.py",
            criteria=criteria,
            gate_text=(
                "Playwright e2e for every page passes; axe 0 serious/critical; Lighthouse "
                "performance >= 90 and accessibility >= 95 on Overview and Run detail; "
                "design evaluator score >= 8.5/10 on every page; screenshots in "
                "docs/screenshots/."
            ),
            commands=[
                "cd web && npm run build",
                "uv run bisect serve --fixture --port 8500",
                "cd web && BISECT_E2E_PORT=8500 "
                "npx playwright test --config playwright.gate.config.ts",
                "npx lighthouse http://127.0.0.1:8500/ --preset=desktop ...  (x3)",
                "npx lighthouse http://127.0.0.1:8500/runs/brief-12-step "
                "--preset=desktop ...  (x3)",
                "cd web && FINAL_BASE_URL=http://127.0.0.1:8500 "
                "npx playwright test --config e2e/capture/final.config.ts",
                "uv run python scripts/gates/p6.py --write-evidence",
            ],
            provenance=provenance_for(EVIDENCE_SOURCES),
            sections={
                "Design scores (docs/design/review-log.md, round 6 final)": _design_scores_section(
                    criteria
                ),
                "Packaging (uv tool install ., no Node on the target machine)": _packaging_section(
                    REPO_ROOT / "agent_bisect" / "server" / "static"
                ),
            },
            commit=current_commit(),
        )
    )
    return path


def format_report(criteria: list[Criterion]) -> str:
    lines = ["P6 gate — dashboard: e2e, axe, Lighthouse, design score, screenshots", ""]
    lines.extend(
        f"[{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}" for c in criteria
    )
    lines.append("")
    lines.append("GATE PASS" if all(c.passed for c in criteria) else "GATE FAILED")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_REVIEW_LOG)
    parser.add_argument("--screenshots-dir", type=Path, default=DEFAULT_SCREENSHOTS_DIR)
    parser.add_argument(
        "--write-evidence", action="store_true", help="Regenerate docs/gates/P6.md."
    )
    args = parser.parse_args(argv)

    criteria = run_gate(args.runs_dir, args.review_log, args.screenshots_dir)
    for criterion in criteria:
        criterion.report()
    report = write_report(args.runs_dir, criteria)
    passed = all(criterion.passed for criterion in criteria)
    print(f"P6 gate: {'PASS' if passed else 'FAILED'} — report at {report}")
    if args.write_evidence:
        print(f"wrote {write_evidence(criteria, DEFAULT_EVIDENCE_PATH)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
