#!/usr/bin/env python
"""P7 gate: the PR check flags a planted regression and stays quiet on a no-op.

    uv run python scripts/gates/p7.py [--skip-remote] [--write-evidence]

Two layers (docs/decisions/0001-preregistration.md's P7 row, "as real PRs on
the repo" -- see below for when layer (b) is skipped):

(a) LOCAL, always run: builds 3 planted-regression and 3 no-op variants of
    `demo/agent_policy.yaml` as branches in a **temporary clone** (never the
    shared working tree), runs `bisect gate --base main --head <branch>` for
    each against this repo's own `main`, and asserts 3/3 regressions are
    flagged with a step named, 0/3 no-ops raise a false alarm.

(b) REAL PRs on `kidus-der/agent-bisect` (private): pushes the same 6
    branches, opens PRs, waits for `.github/workflows/bisect-gate.yml`,
    reads the check conclusion and the sticky comment, asserts the same
    3/3 + 0/3, then closes the PRs and deletes the 6 remote branches. If
    GitHub Actions is unavailable for this repo (disabled, no minutes, a
    billing prompt), this layer is recorded NOT RUN with the exact reason
    -- never worked around, never silently skipped -- and the verdict
    rests on layer (a) alone.

The regression variants all raise `use_correct_task_id`'s slip_probability
(0.75, 0.90, 1.00) rather than three different rules: it is the one rule
whose slip is confirmed through a standing **tool** fault
(`demo/faults.py`), so `TruthfulToolResult` recovers it deterministically
regardless of how the fault was planted -- the reliable case to gate a
self-test on. `docs/decisions/0019-gate-rule.md` explains why the other
three rules (agent-decision steps, confirmed only through `Resample`) do
not get the same guarantee at small N.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.gates.evidence import current_commit, format_evidence, provenance_for  # noqa: E402

POLICY_PATH = "demo/agent_policy.yaml"
PROMPT_PATH = "demo/system_prompt.md"
OUT_ROOT = REPO_ROOT / "runs" / "p7"
GATED_REPO = "kidus-der/agent-bisect"
PR_TITLE_PREFIX = "[P7 demo]"
#: How often layer (b) polls a PR's checks, and the per-PR ceiling.
POLL_INTERVAL_S = 60
MAX_WAIT_S = 25 * 60
#: PRs watched at once, so layer (b) never floods the Actions queue.
CONCURRENCY = 3

GATE_TEXT = (
    "3 planted-regression PRs flagged with the planted step named 3/3; "
    "3 no-op PRs give 0 false alarms."
)


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


def _run(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} (in {cwd}) failed:\n{result.stderr}")
    return result


def set_slip_probability(text: str, rule_id: str, new_value: float) -> str:
    """Edit one rule's `slip_probability`, wherever it sits in the file.

    Bounded to the block starting at `- id: <rule_id>` so two rules that
    happen to share the same current value are never confused.
    """
    pattern = re.compile(rf"(- id: {re.escape(rule_id)}\n(?:.*\n)*?    slip_probability: )[\d.]+")
    new_text, count = pattern.subn(lambda m: f"{m.group(1)}{new_value}", text, count=1)
    if count != 1:
        raise ValueError(f"could not find rule {rule_id!r} in the policy text to edit")
    return new_text


@dataclass(frozen=True, slots=True)
class Variant:
    branch: str
    kind: str  # "regression" | "noop"
    planted: str  # human description, for the evidence table
    apply: Callable[[Path], None]


def _regression_variant(name: str, rule_id: str, new_value: float) -> Variant:
    def apply(clone: Path) -> None:
        path = clone / POLICY_PATH
        path.write_text(set_slip_probability(path.read_text(), rule_id, new_value))

    return Variant(
        branch=f"demo/p7-{name}",
        kind="regression",
        planted=f"{rule_id}.slip_probability -> {new_value}",
        apply=apply,
    )


def _noop_comment_variant() -> Variant:
    def apply(clone: Path) -> None:
        path = clone / POLICY_PATH
        comment = "\n# p7 self-test: a comment changes nothing at runtime.\n"
        path.write_text(path.read_text() + comment)

    return Variant(branch="demo/p7-noop-comment", kind="noop", planted="comment only", apply=apply)


def _noop_rename_variant() -> Variant:
    def apply(clone: Path) -> None:
        path = clone / POLICY_PATH
        text = path.read_text()
        marker = "actually about, not a guess."
        if marker not in text:
            raise ValueError("noop-rename variant: marker text not found in the policy")
        path.write_text(text.replace(marker, "actually about -- never a guess."))

    return Variant(
        branch="demo/p7-noop-rename", kind="noop",
        planted="reword a rule's prose, same id/order/slip_probability", apply=apply,
    )


def _noop_whitespace_variant() -> Variant:
    def apply(clone: Path) -> None:
        path = clone / PROMPT_PATH
        path.write_text(path.read_text() + "\n")

    return Variant(
        branch="demo/p7-noop-whitespace", kind="noop",
        planted="trailing blank line in system_prompt.md (never read at runtime)", apply=apply,
    )


VARIANTS: tuple[Variant, ...] = (
    _regression_variant("id-slip-75", "use_correct_task_id", 0.75),
    _regression_variant("id-slip-90", "use_correct_task_id", 0.90),
    _regression_variant("id-slip-100", "use_correct_task_id", 1.00),
    _noop_comment_variant(),
    _noop_rename_variant(),
    _noop_whitespace_variant(),
)


# ---- layer (a): local, in a temp clone -------------------------------------


def _prepare_clone(tmp: Path) -> Path:
    clone = tmp / "clone"
    # `--no-hardlinks`: the system temp dir is routinely a different
    # filesystem from the repo, where git's default hardlink optimisation
    # for a local-path clone fails outright ("Cross-device link").
    _run(
        ["git", "clone", "--no-hardlinks", "--branch", "main", str(REPO_ROOT), str(clone)],
        cwd=REPO_ROOT,
    )
    return clone


def _branch_for(clone: Path, variant: Variant) -> None:
    _run(["git", "checkout", "-b", variant.branch, "main"], cwd=clone)
    variant.apply(clone)
    _run(["git", "add", "--", POLICY_PATH, PROMPT_PATH], cwd=clone)
    _run(["git", "commit", "-m", f"p7 self-test: {variant.planted}"], cwd=clone)
    _run(["git", "checkout", "main"], cwd=clone)


def _gate_result(clone: Path, variant: Variant, *, out_dir: Path) -> dict[str, Any]:
    from agent_bisect.gate.action import GateConfig, run_gate

    config = GateConfig(
        repo=clone, base="main", head=variant.branch,
        out=out_dir / variant.branch.replace("/", "_"), runs=4, seed=20260917,
    )
    _, document = run_gate(config)
    return document


def local_self_test(*, out_dir: Path) -> tuple[list[Criterion], list[dict[str, Any]]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="bisect-p7-clone-") as tmp:
        clone = _prepare_clone(Path(tmp))
        for variant in VARIANTS:
            _branch_for(clone, variant)
            document = _gate_result(clone, variant, out_dir=out_dir)
            rows.append(
                {
                    "branch": variant.branch, "kind": variant.kind, "planted": variant.planted,
                    "is_regression": document["is_regression"],
                    "decisive_step_head": document["decisive_step_head"],
                    "base_pass_rate": document["base_pass_rate"]["value"],
                    "head_pass_rate": document["head_pass_rate"]["value"],
                    "p_value": document["p_value"],
                }
            )

    regressions = [r for r in rows if r["kind"] == "regression"]
    noops = [r for r in rows if r["kind"] == "noop"]
    flagged = [r for r in regressions if r["is_regression"] and r["decisive_step_head"] is not None]
    false_alarms = [r for r in noops if r["is_regression"]]
    regression_detail = ", ".join(
        f"{r['branch']}={r['is_regression']}/{r['decisive_step_head']}" for r in regressions
    )
    criteria = [
        Criterion(
            "regressions flagged with a named step",
            len(flagged) == len(regressions),
            f"{len(flagged)}/{len(regressions)}: {regression_detail}",
        ),
        Criterion(
            "no-ops raise no false alarm",
            len(false_alarms) == 0,
            f"{len(false_alarms)}/{len(noops)} false alarms"
            + (f": {[r['branch'] for r in false_alarms]}" if false_alarms else ""),
        ),
    ]
    return criteria, rows


# ---- layer (b): real PRs on the private repo -------------------------------


class ActionsUnavailableError(Exception):
    """GitHub Actions cannot run on this repo right now. Carries why."""


def _gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return _run(["gh", *args], cwd=REPO_ROOT, check=check)


def _check_actions_available() -> None:
    result = _gh(["api", f"repos/{GATED_REPO}/actions/permissions"], check=False)
    if result.returncode != 0:
        raise ActionsUnavailableError(f"could not read Actions settings: {result.stderr.strip()}")
    settings = json.loads(result.stdout)
    if not settings.get("enabled", False):
        raise ActionsUnavailableError("Actions is disabled for this repository")


def _push_and_open_pr(variant: Variant) -> int:
    _run(["git", "push", "-u", "origin", variant.branch], cwd=REPO_ROOT)
    result = _gh(
        [
            "pr", "create", "--repo", GATED_REPO, "--base", "main", "--head", variant.branch,
            "--title", f"{PR_TITLE_PREFIX} {variant.planted}",
            "--body",
            "Automated demo PR from scripts/gates/p7.py's layer (b) self-test. "
            "It will be closed and its branch deleted once the check is read.",
        ]
    )
    number = int(result.stdout.strip().rsplit("/", 1)[-1])
    return number


def _wait_for_check(pr_number: int) -> str:
    """`"success"`, `"failure"`, or `"timeout"`."""
    deadline = time.monotonic() + MAX_WAIT_S
    while time.monotonic() < deadline:
        result = _gh(
            ["pr", "checks", str(pr_number), "--repo", GATED_REPO, "--json", "state,bucket"],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            checks = json.loads(result.stdout)
            if checks and all(c.get("bucket") != "pending" for c in checks):
                return "success" if all(c.get("bucket") == "pass" for c in checks) else "failure"
        time.sleep(POLL_INTERVAL_S)
    return "timeout"


def _sticky_comment(pr_number: int) -> str | None:
    result = _gh(
        ["api", f"repos/{GATED_REPO}/issues/{pr_number}/comments", "--jq", ".[].body"], check=False
    )
    if result.returncode != 0:
        return None
    for body in result.stdout.splitlines():
        if "bisect-gate-comment" in body or "Bisect -" in body:
            return body
    return result.stdout or None


def _close_pr(pr_number: int, branch: str) -> None:
    _gh(
        [
            "pr", "close", str(pr_number), "--repo", GATED_REPO,
            "--comment", "p7 self-test done; closing and removing the demo branch.",
        ],
        check=False,
    )
    _run(["git", "push", "origin", "--delete", branch], cwd=REPO_ROOT, check=False)


RemotePrResult = tuple[list[Criterion], list[dict[str, Any]], str | None]


def remote_pr_test(*, evidence_dir: Path) -> RemotePrResult:
    """Returns `(criteria, rows, skip_reason)`. `skip_reason` set means NOT RUN."""
    try:
        _check_actions_available()
    except ActionsUnavailableError as exc:
        return [], [], str(exc)

    evidence_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    pending: list[tuple[Variant, int]] = []
    for batch_start in range(0, len(VARIANTS), CONCURRENCY):
        batch = VARIANTS[batch_start : batch_start + CONCURRENCY]
        for variant in batch:
            number = _push_and_open_pr(variant)
            pending.append((variant, number))
        for variant, number in pending[-len(batch):]:
            conclusion = _wait_for_check(number)
            comment = _sticky_comment(number)
            run_url = _gh(
                ["pr", "view", str(number), "--repo", GATED_REPO, "--json", "url", "--jq", ".url"],
                check=False,
            ).stdout.strip()
            (evidence_dir / f"{variant.branch.replace('/', '_')}.md").write_text(
                f"PR: {run_url}\nconclusion: {conclusion}\n\n{comment or '(no comment found)'}\n"
            )
            rows.append(
                {
                    "branch": variant.branch, "kind": variant.kind, "pr": number, "url": run_url,
                    "conclusion": conclusion,
                    "flagged": bool(comment and "regression detected" in (comment or "")),
                }
            )
            _close_pr(number, variant.branch)

    regressions = [r for r in rows if r["kind"] == "regression"]
    noops = [r for r in rows if r["kind"] == "noop"]
    flagged = [r for r in regressions if r["conclusion"] == "failure" and r["flagged"]]
    false_alarms = [r for r in noops if r["conclusion"] == "failure" or r["flagged"]]
    criteria = [
        Criterion(
            "real PRs: regressions flagged", len(flagged) == len(regressions),
            f"{len(flagged)}/{len(regressions)}",
        ),
        Criterion(
            "real PRs: no-ops give no false alarm", len(false_alarms) == 0,
            f"{len(false_alarms)}/{len(noops)}",
        ),
    ]
    return criteria, rows, None


# ---- entry point -------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-remote", action="store_true", help="Skip layer (b) entirely.")
    parser.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args(argv)

    from loguru import logger

    logger.remove()

    local_criteria, local_rows = local_self_test(out_dir=OUT_ROOT / "local")
    remote_criteria: list[Criterion] = []
    remote_rows: list[dict[str, Any]] = []
    remote_skip_reason: str | None = "--skip-remote passed" if args.skip_remote else None
    if not args.skip_remote:
        remote_criteria, remote_rows, remote_skip_reason = remote_pr_test(
            evidence_dir=OUT_ROOT / "remote"
        )

    criteria = local_criteria + remote_criteria
    for criterion in criteria:
        print(criterion.line())  # noqa: T201 - this IS the gate's console output
    if remote_skip_reason:
        print(f"[NOT RUN] real PRs (layer b): {remote_skip_reason}")  # noqa: T201

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    criteria_json = [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in criteria]
    (OUT_ROOT / "gate.json").write_text(
        json.dumps(
            {
                "local": local_rows,
                "remote": remote_rows,
                "remote_skip_reason": remote_skip_reason,
                "criteria": criteria_json,
            },
            indent=2, sort_keys=True,
        )
    )

    if args.write_evidence:
        _write_evidence(criteria, local_rows, remote_rows, remote_skip_reason)

    return 0 if all(c.passed for c in criteria) else 1


def _write_evidence(
    criteria: list[Criterion], local_rows: list[dict], remote_rows: list[dict],
    remote_skip_reason: str | None,
) -> None:
    local_table = "\n".join(
        f"- `{r['branch']}` ({r['kind']}): planted={r.get('planted', '-')!r}, "
        f"flagged={r['is_regression']}, step={r['decisive_step_head']}, "
        f"base={r['base_pass_rate']:.2f}, head={r['head_pass_rate']:.2f}, p={r['p_value']:.3g}"
        for r in local_rows
    )
    remote_section = (
        f"NOT RUN: {remote_skip_reason}" if remote_skip_reason else
        "\n".join(f"- `{r['branch']}`: {r['url']} -> {r['conclusion']}" for r in remote_rows)
    )
    doc = format_evidence(
        gate="P7", title="the PR check",
        script="scripts/gates/p7.py",
        criteria=criteria,
        gate_text=GATE_TEXT,
        commands=["uv run python scripts/gates/p7.py --write-evidence"],
        provenance=provenance_for(
            ["demo/", "agent_bisect/gate/", ".github/", "docs/decisions/0019-gate-rule.md"]
        ),
        sections={
            "Layer (a): local, 6 cases": local_table,
            "Layer (b): real PRs": remote_section,
        },
        commit=current_commit(),
    )
    (REPO_ROOT / "docs" / "gates" / "P7.md").write_text(doc)


if __name__ == "__main__":
    raise SystemExit(main())
