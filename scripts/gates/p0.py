#!/usr/bin/env python3
"""The P0 gate: does the phase meet every threshold pre-registered in 0001?

Gate (from `docs/decisions/0001-preregistration.md`): `bisect doctor` exits
0 — key found; the chosen agent reaches ≥ 95% valid tool calls **and** an
airline pass rate inside 35–75% over 20 tasks; one τ² task runs end to end
with a reward; and the measured rate limit (requests/min per model) is
written to `docs/decisions/models.md`.

The gate deliberately **re-derives** the agent's two numbers from the raw
per-task checkpoints in `runs/p0/probe/`, not from `config/models.toml`.
The toml is something P0b wrote about itself; the checkpoints are the
evidence. If the two disagree, the checkpoints win and the gate fails.

Exit code 0 only when every criterion passes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent_bisect.adapters.tau2_probe import (  # noqa: E402
    AGENT_PASS_WINDOW,
    MIN_VALID_TOOL_CALL_RATE,
    TaskProbeResult,
    choose_agent,
    summarise_probe,
)
from agent_bisect.core.doctor import (  # noqa: E402
    DEFAULT_MODELS_CONFIG_PATH,
    REQUIRED_MODEL_ROLES,
    load_models_config,
)

DEFAULT_PROBE_DIR = REPO_ROOT / "runs" / "p0" / "probe"
DEFAULT_RATE_LIMIT_PATH = REPO_ROOT / "runs" / "p0" / "rate_limit.json"
DEFAULT_MODELS_DOC = REPO_ROOT / "docs" / "decisions" / "models.md"
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "docs" / "gates" / "P0.md"
N_TASKS = 20
RPM_MARKERS = ("rpm", "requests/min", "requests per minute")


@dataclass(frozen=True)
class Criterion:
    name: str
    passed: bool
    detail: str


def load_probe_results(probe_dir: Path, model: str) -> list[TaskProbeResult]:
    """Every per-task checkpoint for one model, read straight off disk."""
    directory = probe_dir / model.replace("/", "__")
    if not directory.exists():
        return []
    rows: list[TaskProbeResult] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith((".simulation.json", ".error.json")):
            continue
        payload = json.loads(path.read_text())
        payload["invalid_reasons"] = tuple(payload.get("invalid_reasons") or ())
        rows.append(TaskProbeResult(**payload))
    return rows


def recheck_agent_from_checkpoints(
    probe_dir: Path, agent: str, *, n_tasks: int = N_TASKS
) -> list[Criterion]:
    """Re-derive the agent's pass rate and tool-call rate from the raw evidence."""
    rows = load_probe_results(probe_dir, agent)
    summary = summarise_probe(agent, rows, n_tasks=n_tasks)
    low, high = AGENT_PASS_WINDOW
    rate = summary.valid_tool_call_rate
    shown = "no tool call emitted" if rate is None else f"{rate:.3f}"
    return [
        Criterion(
            "probe_complete",
            summary.complete,
            f"{summary.n_completed}/{n_tasks} tasks have a checkpoint for {agent}",
        ),
        Criterion(
            "valid_tool_call_rate",
            summary.meets_tool_call_floor,
            f"{shown} over {summary.n_tool_calls} agent tool calls "
            f"(>= {MIN_VALID_TOOL_CALL_RATE} required)",
        ),
        Criterion(
            "airline_pass_rate",
            summary.in_pass_window,
            f"{summary.n_passed}/{n_tasks} = {summary.pass_rate:.2f} "
            f"[95% CI {summary.ci_low:.2f}, {summary.ci_high:.2f}] (window [{low}, {high}])",
        ),
    ]


def evaluate_doctor(payload: list[dict], exit_code: int) -> Criterion:
    failing = [check["name"] for check in payload if not check.get("passed")]
    if exit_code == 0 and not failing:
        return Criterion("doctor", True, f"`bisect doctor` exits 0 ({len(payload)} checks)")
    detail = f"`bisect doctor` exited {exit_code}"
    if failing:
        detail += f"; failing checks: {', '.join(failing)}"
    return Criterion("doctor", False, detail)


def evaluate_rate_limit(path: Path) -> Criterion:
    """The measured requests/min per model must exist as data, not just prose."""
    if not path.exists():
        return Criterion("rate_limit_measured", False, f"{path} not found")
    try:
        state = json.loads(path.read_text())
    except ValueError as exc:
        return Criterion("rate_limit_measured", False, f"{path} is not valid JSON: {exc}")
    measured = state.get("measured_rpm") or {}
    windows = state.get("windows") or []
    if not measured:
        return Criterion("rate_limit_measured", False, "no model has a measured rpm")
    calls = sum(window.get("sent", 0) for window in windows)
    return Criterion(
        "rate_limit_measured",
        True,
        f"{len(measured)} model(s) measured over {len(windows)} windows ({calls} calls)",
    )


def evaluate_models_doc(path: Path, chosen: list[str]) -> Criterion:
    """`docs/decisions/models.md` must name every chosen model and record the rate limit."""
    if not path.exists():
        return Criterion("models_doc", False, f"{path} not found")
    text = path.read_text()
    missing = [model for model in chosen if model and model not in text]
    if missing:
        return Criterion("models_doc", False, f"not documented: {', '.join(missing)}")
    if not any(marker in text.lower() for marker in RPM_MARKERS):
        return Criterion("models_doc", False, "no measured requests/min recorded")
    return Criterion("models_doc", True, f"{path.name} documents {len(chosen)} chosen model(s)")


def evaluate_criteria(
    *,
    models_config: dict | None,
    doctor_payload: list[dict],
    doctor_exit_code: int,
    probe_dir: Path,
    rate_limit_path: Path,
    models_doc_path: Path,
    n_tasks: int = N_TASKS,
) -> list[Criterion]:
    """Every P0 criterion, in report order."""
    criteria = [evaluate_doctor(doctor_payload, doctor_exit_code)]
    agent = (models_config or {}).get("agent")
    if not agent:
        criteria.append(Criterion("agent_chosen", False, "no agent chosen in config/models.toml"))
    else:
        criteria.append(Criterion("agent_chosen", True, agent))
        criteria.extend(recheck_agent_from_checkpoints(probe_dir, agent, n_tasks=n_tasks))
    criteria.append(evaluate_rate_limit(rate_limit_path))
    chosen = [(models_config or {}).get(role, "") for role in REQUIRED_MODEL_ROLES]
    criteria.append(evaluate_models_doc(models_doc_path, [c for c in chosen if c]))
    return criteria


def format_report(criteria: list[Criterion], *, commit: str) -> str:
    verdict = "PASS" if all(c.passed for c in criteria) else "FAILED"
    lines = [f"P0 gate: {verdict}  (commit {commit})", ""]
    for criterion in criteria:
        mark = "PASS" if criterion.passed else "FAIL"
        lines.append(f"  [{mark}] {criterion.name}: {criterion.detail}")
    return "\n".join(lines)


def format_evidence(
    criteria: list[Criterion],
    *,
    commit: str,
    calls_per_model: dict[str, int],
    provenance: dict[str, str],
    notes: list[str] | None = None,
) -> str:
    """`docs/gates/P0.md`: the commands, the numbers and the verdict, per criterion."""
    verdict = "PASS" if all(c.passed for c in criteria) else "FAILED"
    lines = [
        "# P0 gate — setup and model choice",
        "",
        f"**Verdict: {verdict}** at commit `{commit}`.",
        "",
        "Generated by `scripts/gates/p0.py --write-evidence`; re-running it reproduces "
        "this file from `runs/p0/` and `config/models.toml`.",
        "",
        "## Provenance",
        "",
        "The commit above is repository HEAD when this ran; in a shared tree that can "
        "be an unrelated change. These are the commits that actually produced the "
        "verdict:",
        "",
        "| File | Commit |",
        "|---|---|",
    ]
    for path, source_commit in provenance.items():
        lines.append(f"| `{path}` | {source_commit} |")
    lines += [
        "",
        "## Gate (pre-registered in docs/decisions/0001-preregistration.md)",
        "",
        "> `bisect doctor` exits 0: key found; chosen agent ≥ 95% valid tool calls **and** "
        "airline pass rate within 35–75% (20 airline tasks); one τ² task runs end to end "
        "with a reward; measured rate limit (requests/min per model) written to "
        "`docs/decisions/models.md`.",
        "",
        "## Commands",
        "",
        "```",
        "uv run python scripts/measure_rate_limit.py --only all",
        "uv run python scripts/measure_rate_limit.py \\",
        "    --isolate nvidia/nemotron-3.5-lightning-30b-a3b --rate 120 --window 30",
        "uv run python scripts/probe_models.py --stage all --concurrency 5 --tasks 20",
        "uv run python scripts/decide_models.py",
        "uv run bisect doctor --live",
        "uv run python scripts/gates/p0.py",
        "```",
        "",
        "## Criteria",
        "",
        "| Criterion | Result | Detail |",
        "|---|---|---|",
    ]
    for criterion in criteria:
        mark = "PASS" if criterion.passed else "**FAIL**"
        lines.append(f"| `{criterion.name}` | {mark} | {criterion.detail} |")
    lines += [
        "",
        "## Calls spent (from the budget ledger, phase P0)",
        "",
        "| Model | Calls |",
        "|---|---|",
    ]
    for model, calls in sorted(calls_per_model.items()):
        lines.append(f"| `{model}` | {calls} |")
    lines.append(f"| **total** | **{sum(calls_per_model.values())}** |")
    if notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {note}" for note in notes]
    lines += ["", "Full numbers and the rule that produced each choice: "
              "`docs/decisions/models.md`."]
    return "\n".join(lines) + "\n"


def run_doctor_json() -> tuple[list[dict], int]:
    """Shell out to the real CLI, so the gate checks what a user would run."""
    completed = subprocess.run(  # noqa: S603 - fixed, non-shell argv
        [sys.executable, "-m", "agent_bisect.cli", "doctor", "--json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        payload = []
    return payload, completed.returncode


def current_commit() -> str:
    completed = subprocess.run(  # noqa: S603 - fixed, non-shell argv
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    return completed.stdout.strip() or "unknown"


#: The files whose commits actually produced this verdict. HEAD alone is
#: misleading in a shared tree: it is whatever any other agent pushed last,
#: which can be an unrelated commit that never touched P0.
EVIDENCE_SOURCES = (
    "scripts/gates/p0.py",
    "scripts/decide_models.py",
    "config/models.toml",
    "docs/decisions/models.md",
)


def last_commit_for(path: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed, non-shell argv
        ["git", "log", "-1", "--format=%h %s", "--", path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return completed.stdout.strip() or "uncommitted"


def evidence_provenance() -> dict[str, str]:
    return {path: last_commit_for(path) for path in EVIDENCE_SOURCES}


def probed_models(probe_dir: Path) -> list[str]:
    """Candidates that have a checkpoint directory. `#` marks the sanity run."""
    if not probe_dir.exists():
        return []
    return sorted(
        d.name.replace("__", "/")
        for d in probe_dir.iterdir()
        if d.is_dir() and "#" not in d.name
    )


def invariance_notes(probe_dir: Path, n_tasks: int = N_TASKS) -> list[str]:
    """State plainly whether unfinished tasks could have changed the choice.

    A task that never completed after its retry passes is counted as "not
    passed" in the headline rate. That is one scoring convention, so the
    gate records whether the pre-registered rule picks the same model under
    EVERY outcome of those tasks. If it does, the convention did not decide
    anything and the choice stands on its own.
    """
    models = probed_models(probe_dir)
    if not models:
        return []
    summaries = [
        summarise_probe(m, load_probe_results(probe_dir, m), n_tasks=n_tasks)
        for m in models
    ]
    missing = {s.model: s.n_tasks - s.n_completed for s in summaries}
    unfinished = sum(missing.values())
    if unfinished == 0:
        return ["Every candidate completed all "
                f"{n_tasks} tasks; no unfinished task could affect the choice."]
    choices = set()
    for combo in itertools.product(*[range(missing[s.model] + 1) for s in summaries]):
        arms = []
        for summary, extra in zip(summaries, combo, strict=True):
            passed = summary.n_passed + extra
            arms.append(
                replace(summary, n_passed=passed, pass_rate=passed / n_tasks,
                        n_completed=n_tasks)
            )
        chosen, _ = choose_agent(arms, {}, models)
        choices.add(chosen)
    listed = ", ".join(f"`{m}` ({n})" for m, n in sorted(missing.items()) if n)
    if len(choices) == 1:
        verdict = (
            f"**The selection is invariant.** Enumerating every pass/fail outcome of "
            f"the {unfinished} unfinished task(s) — {listed} — the pre-registered rule "
            f"picks {choices.pop()} in all {2 ** unfinished} of them, so counting an "
            "unfinished task as a failure did not decide the choice."
        )
    else:
        verdict = (
            f"**The selection is NOT invariant.** The {unfinished} unfinished task(s) "
            f"— {listed} — admit outcomes selecting different models "
            f"({sorted(str(c) for c in choices)}); the choice is not decided."
        )
    return [verdict]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-dir", type=Path, default=DEFAULT_PROBE_DIR)
    parser.add_argument("--tasks", type=int, default=N_TASKS)
    parser.add_argument("--write-evidence", action="store_true",
                        help="Also write docs/gates/P0.md.")
    args = parser.parse_args()

    payload, exit_code = run_doctor_json()
    criteria = evaluate_criteria(
        models_config=load_models_config(REPO_ROOT / DEFAULT_MODELS_CONFIG_PATH),
        doctor_payload=payload,
        doctor_exit_code=exit_code,
        probe_dir=args.probe_dir,
        rate_limit_path=DEFAULT_RATE_LIMIT_PATH,
        models_doc_path=DEFAULT_MODELS_DOC,
        n_tasks=args.tasks,
    )
    commit = current_commit()
    print(format_report(criteria, commit=commit))
    if args.write_evidence:
        from agent_bisect.core.budget import BudgetLedger

        ledger = BudgetLedger(REPO_ROOT / "runs" / "ledger.sqlite")
        DEFAULT_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_EVIDENCE_PATH.write_text(
            format_evidence(
                criteria,
                commit=commit,
                calls_per_model=ledger.totals_per_model(),
                provenance=evidence_provenance(),
                notes=invariance_notes(args.probe_dir, args.tasks),
            )
        )
        print(f"\nwrote {DEFAULT_EVIDENCE_PATH}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
