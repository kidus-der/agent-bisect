"""`bisect gate`: run the demo suite on base and head, compare, blame.

Orchestration only -- every decision it makes is one of the pure functions
below, each testable against fixed JSON without a worktree, a subprocess,
or a git repository:

1. checkout base and head into throwaway worktrees (`gate.worktree`);
2. run `python -m demo.runner` in each, writing its recorded store to a
   *persistent* path this process controls (`--out`), not inside the
   worktree, so the worktree can close the moment the subprocess returns;
3. `compare_suites` (pure) pools the two summaries and applies
   `docs/decisions/0019-gate-rule.md`'s rule (`gate.stats.GateComparison`);
4. if regressed, `new_failures` (pure) names which `(scenario, run_index)`
   pairs are new, and `demo.blame_cli` runs inside the **head** worktree
   (still open) to confirm them;
5. `decisive_step_summary` (pure) picks the modal blamed step and maps it
   to what changed in `demo/` between base and head;
6. `gate.comment.render_comment` renders the sticky comment; `result.json`
   is `to_result_json`'s output, shaped for `server.schemas_pr`.

Exit codes: 0 clean, 1 regression, 2 error (`docs/LOOP_STATE.md`'s P7 row).
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_bisect.gate.comment import DecisiveStepSummary, GateReport, render_comment
from agent_bisect.gate.stats import GateComparison
from agent_bisect.gate.worktree import worktree_at

CLEAN_EXIT = 0
REGRESSION_EXIT = 1
ERROR_EXIT = 2

DEFAULT_SUITE = "demo"
DEFAULT_RUNS = 4
DEFAULT_SEED = 20260917


class GateError(RuntimeError):
    """Something the gate could not recover from: a bad ref, a crashed subprocess."""


@dataclass(frozen=True, slots=True)
class GateConfig:
    repo: Path
    base: str
    head: str
    out: Path
    runs: int = DEFAULT_RUNS
    seed: int = DEFAULT_SEED
    suite: str = DEFAULT_SUITE


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_index: int
    passed: bool
    run_id: str


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    """One scenario's runs, from either side's `summary.json`."""

    name: str
    rule_id: str
    runs: tuple[RunRecord, ...]

    @property
    def n(self) -> int:
        return len(self.runs)

    @property
    def passes(self) -> int:
        return sum(1 for r in self.runs if r.passed)


def _scenario_summaries(document: dict[str, Any]) -> dict[str, ScenarioSummary]:
    return {
        entry["name"]: ScenarioSummary(
            name=entry["name"],
            rule_id=entry["rule_id"],
            runs=tuple(
                RunRecord(run_index=run["run_index"], passed=run["passed"], run_id=run["run_id"])
                for run in entry["runs"]
            ),
        )
        for entry in document["scenarios"]
    }


@dataclass(frozen=True, slots=True)
class SuiteComparison:
    """Everything `compare_suites` derives from two `summary.json` documents."""

    comparison: GateComparison
    base: dict[str, ScenarioSummary]
    head: dict[str, ScenarioSummary]


def compare_suites(base_document: dict[str, Any], head_document: dict[str, Any]) -> SuiteComparison:
    """Pool both sides' pass counts and apply the pre-registered rule."""
    base = _scenario_summaries(base_document)
    head = _scenario_summaries(head_document)
    comparison = GateComparison(
        head_passes=sum(s.passes for s in head.values()),
        head_n=sum(s.n for s in head.values()),
        base_passes=sum(s.passes for s in base.values()),
        base_n=sum(s.n for s in base.values()),
    )
    return SuiteComparison(comparison=comparison, base=base, head=head)


def new_failures(suite: SuiteComparison) -> list[dict[str, Any]]:
    """`(scenario, run_index)` pairs that failed on head but passed on base."""
    found: list[dict[str, Any]] = []
    for name, head_scenario in suite.head.items():
        base_scenario = suite.base.get(name)
        if base_scenario is None:
            continue
        base_by_index = {r.run_index: r for r in base_scenario.runs}
        for run in head_scenario.runs:
            if run.passed:
                continue
            base_run = base_by_index.get(run.run_index)
            if base_run is not None and base_run.passed:
                found.append(
                    {
                        "scenario_name": name,
                        "run_index": run.run_index,
                        "head_run_id": run.run_id,
                        "base_run_id": base_run.run_id,
                    }
                )
    return found


def decisive_step_summary(
    blame_summaries: list[dict[str, Any]],
    *,
    total_new_failures: int,
    changed_files: dict[str, list[str]],
) -> DecisiveStepSummary | None:
    """The modal blamed step across every confirmed new failure, or `None`.

    Ties go to the smaller step index (`sorted` before `Counter.most_common`
    is stable on insertion order, so sorting the candidates first is what
    makes the tie-break deterministic rather than dict-order-dependent).
    """
    blamed = sorted(s["blamed_step"] for s in blame_summaries if s.get("blamed_step") is not None)
    if not blamed:
        return None
    step, sharing = Counter(blamed).most_common(1)[0]
    lines = changed_files.get("demo/agent_policy.yaml", []) or ["(no textual diff available)"]
    # Every failure that shares the decisive step ran the same confirmation
    # (same intervention, same N) against its own recording, so their
    # StepEffects are independent draws of the same quantity -- the first
    # one is as representative as any, and picking it (rather than
    # averaging) keeps the reported CI a real, reported interval instead of
    # a derived one nothing computed.
    effect = next(
        (s["effect"] for s in blame_summaries if s.get("blamed_step") == step and s.get("effect")),
        None,
    )
    effect = effect or {"effect": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    identity = next(
        (s["step"] for s in blame_summaries if s.get("blamed_step") == step and s.get("step")),
        None,
    ) or {"actor": "agent", "tool_name": None}
    return DecisiveStepSummary(
        step=step, actor=identity["actor"], tool_name=identity["tool_name"],
        effect=effect["effect"], ci_low=effect["ci_low"], ci_high=effect["ci_high"], n=effect["n"],
        changed_lines=tuple(lines), caused_by="demo/agent_policy.yaml (this PR)",
        sharing_failures=sharing, total_new_failures=total_new_failures,
    )


def diff_lines(repo: Path, base: str, head: str, path: str) -> list[str]:
    """`- old` / `+ new` lines `git diff` reports for `path` between the two refs."""
    result = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}..{head}", "--", path],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return []
    changed = [
        line for line in result.stdout.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not re.match(r"^(\+\+\+|---)", line)
    ]
    return changed


def to_result_json(
    *, config: GateConfig, suite: SuiteComparison, decisive: DecisiveStepSummary | None,
    total_calls: int, comment: str,
) -> dict[str, Any]:
    """Shaped to align with `server.schemas_pr.PrCheckDetail`."""
    return {
        "base_ref": config.base,
        "head_ref": config.head,
        "suite": config.suite,
        "runs_per_scenario": config.runs,
        "is_regression": suite.comparison.is_regression,
        "base_pass_rate": {
            "value": suite.comparison.base_rate,
            "ci_low": None, "ci_high": None, "n": suite.comparison.base_n,
        },
        "head_pass_rate": {
            "value": suite.comparison.head_rate,
            "ci_low": None, "ci_high": None, "n": suite.comparison.head_n,
        },
        "p_value": suite.comparison.p_value,
        "decisive_step_base": None,
        "decisive_step_head": None if decisive is None else decisive.step,
        "scenarios": [
            {
                "scenario": name,
                "base_pass_rate": suite.base[name].passes / suite.base[name].n
                if name in suite.base else None,
                "head_pass_rate": head.passes / head.n,
                "n": head.n,
            }
            for name, head in suite.head.items()
        ],
        "comment_markdown": comment,
    }


_prepared_worktrees: set[Path] = set()


def _prepare_worktree(worktree: Path) -> None:
    """Vendor tau2 and sync dependencies, once per worktree.

    A worktree shares no gitignored file with the repo it was checked out
    of (`vendor/tau2-bench`, `.venv`), so each one needs its own -- exactly
    what the GitHub Action's own "Vendor tau2-bench" / "Install
    dependencies" steps do, run here for `scripts/gates/p7.py`'s local
    worktrees the Action itself never touches.
    """
    if worktree in _prepared_worktrees:
        return
    setup = subprocess.run(
        ["bash", "scripts/setup_tau2.sh"], cwd=worktree, capture_output=True, text=True, check=False
    )
    if setup.returncode != 0:
        raise GateError(f"scripts/setup_tau2.sh failed in {worktree}: {setup.stderr[-4000:]}")
    sync = subprocess.run(
        ["uv", "sync", "--frozen"], cwd=worktree, capture_output=True, text=True, check=False
    )
    if sync.returncode != 0:
        raise GateError(f"uv sync --frozen failed in {worktree}: {sync.stderr[-4000:]}")
    _prepared_worktrees.add(worktree)


def run_demo_runner(worktree: Path, *, out: Path, seed: int, runs: int) -> dict[str, Any]:
    _prepare_worktree(worktree)
    out.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["uv", "run", "python", "-m", "demo.runner", "--seed", str(seed), "--runs", str(runs),
         "--out", str(out)],
        cwd=worktree, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise GateError(f"demo.runner failed in {worktree}: {result.stderr[-4000:]}")
    return json.loads((out / "summary.json").read_text())


def run_blame_cli(
    worktree: Path, *, failures_path: Path, head_store: Path, base_store: Path, out: Path, seed: int
) -> list[dict[str, Any]]:
    _prepare_worktree(worktree)
    out.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["uv", "run", "python", "-m", "demo.blame_cli",
         "--failures", str(failures_path), "--head-store", str(head_store),
         "--base-store", str(base_store), "--out", str(out), "--seed", str(seed)],
        cwd=worktree, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise GateError(f"demo.blame_cli failed in {worktree}: {result.stderr[-4000:]}")
    return json.loads((out / "failures_result.json").read_text())


def run_gate(config: GateConfig) -> tuple[int, dict[str, Any]]:
    """The whole pipeline. Returns `(exit_code, result.json's document)`."""
    config.out.mkdir(parents=True, exist_ok=True)
    with worktree_at(config.repo, config.base, label="base") as base_path:
        base_document = run_demo_runner(
            base_path, out=config.out / "base", seed=config.seed, runs=config.runs
        )
    with worktree_at(config.repo, config.head, label="head") as head_path:
        head_document = run_demo_runner(
            head_path, out=config.out / "head", seed=config.seed, runs=config.runs
        )
        suite = compare_suites(base_document, head_document)
        decisive: DecisiveStepSummary | None = None
        total_calls = 0
        if suite.comparison.is_regression:
            failures = new_failures(suite)
            failures_path = config.out / "failures.json"
            failures_path.write_text(json.dumps({"failures": failures}))
            blame_summaries = run_blame_cli(
                head_path, failures_path=failures_path,
                head_store=config.out / "head" / "store",
                base_store=config.out / "base" / "store",
                out=config.out / "blame", seed=config.seed,
            )
            total_calls = sum(s.get("total_calls", 0) for s in blame_summaries)
            changed = {"demo/agent_policy.yaml": diff_lines(
                config.repo, config.base, config.head, "demo/agent_policy.yaml"
            )}
            decisive = decisive_step_summary(
                blame_summaries, total_new_failures=len(failures), changed_files=changed
            )
    report = GateReport(
        suite=config.suite,
        scenario_count=len(suite.head),
        runs_per_scenario=config.runs,
        comparison=suite.comparison,
        decisive=decisive,
        total_calls=total_calls,
    )
    comment = render_comment(report)
    document = to_result_json(
        config=config, suite=suite, decisive=decisive, total_calls=total_calls, comment=comment
    )
    (config.out / "comment.md").write_text(comment + "\n")
    (config.out / "result.json").write_text(json.dumps(document, indent=2, sort_keys=True))
    exit_code = REGRESSION_EXIT if suite.comparison.is_regression else CLEAN_EXIT
    return exit_code, document
