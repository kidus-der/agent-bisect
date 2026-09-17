"""The PR comment: `docs/brief/summary.md` section 5's format, filled in.

One function, `render_comment`, turns a `GateComparison` plus (when
regressed) the decisive-step summary into the sticky comment `bisect gate`
posts. Kept separate from `action.py`'s orchestration so the format can be
tested against fixed data without running anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_bisect.gate.stats import GateComparison

DETAILS_LINE = "details -> bisect serve"


@dataclass(frozen=True, slots=True)
class DecisiveStepSummary:
    """One decisive step, named across a gate's new failures."""

    step: int
    actor: str
    tool_name: str | None
    effect: float
    ci_low: float
    ci_high: float
    n: int
    #: `-`/`+` lines describing what changed at this step, oldest first.
    changed_lines: tuple[str, ...]
    #: e.g. `"demo/agent_policy.yaml L23-L26 (this PR)"`.
    caused_by: str
    sharing_failures: int
    total_new_failures: int

    @property
    def actor_label(self) -> str:
        return f"{self.actor} -> {self.tool_name}" if self.tool_name else self.actor


@dataclass(frozen=True, slots=True)
class GateReport:
    """Everything one `bisect gate` run needs to render its comment."""

    suite: str
    scenario_count: int
    runs_per_scenario: int
    comparison: GateComparison
    decisive: DecisiveStepSummary | None
    total_calls: int
    error: str | None = None


def _clean_comment(report: GateReport) -> str:
    comparison = report.comparison
    return (
        "Bisect - agent suite unchanged\n"
        f"scenario suite     {report.suite} "
        f"({report.scenario_count} scenarios x {report.runs_per_scenario} runs)\n"
        f"pass rate          base {comparison.base_rate:.2f}  ->  "
        f"head {comparison.head_rate:.2f}   (p = {comparison.p_value:.3g})\n"
        f"no regression detected against the pre-registered rule "
        f"(docs/decisions/0019-gate-rule.md)\n"
        f"{DETAILS_LINE}"
    )


def _error_comment(report: GateReport) -> str:
    return f"Bisect - gate error\n{report.error}\n{DETAILS_LINE}"


def _regression_without_decisive_step(report: GateReport) -> str:
    comparison = report.comparison
    return (
        "Bisect - agent regression detected\n"
        f"scenario suite     {report.suite} "
        f"({report.scenario_count} scenarios x {report.runs_per_scenario} runs)\n"
        f"pass rate          base {comparison.base_rate:.2f}  ->  "
        f"head {comparison.head_rate:.2f}   (p = {comparison.p_value:.3g})\n"
        "decisive step      none of the new failures' shortlists confirmed a step\n"
        f"{report.total_calls} calls spent · {DETAILS_LINE}"
    )


def _regression_comment(report: GateReport) -> str:
    comparison = report.comparison
    decisive = report.decisive
    assert decisive is not None
    lines = [
        "Bisect - agent regression detected",
        f"scenario suite     {report.suite} "
        f"({report.scenario_count} scenarios x {report.runs_per_scenario} runs)",
        f"pass rate          base {comparison.base_rate:.2f}  ->  "
        f"head {comparison.head_rate:.2f}   (p = {comparison.p_value:.3g})",
        f"decisive step      step {decisive.step} · {decisive.actor_label}",
        f"effect of reverting at step {decisive.step}   "
        f"{decisive.effect:+.2f}  95% CI [{decisive.ci_low:.2f}, {decisive.ci_high:.2f}] "
        f"· N = {decisive.n}",
        f"what changed at step {decisive.step}",
    ]
    lines.extend(f"  {line}" for line in decisive.changed_lines)
    lines.append(f"  caused by: {decisive.caused_by}")
    lines.append(
        f"{decisive.sharing_failures} of {decisive.total_new_failures} new failures "
        f"share this step · {report.total_calls} calls · {DETAILS_LINE}"
    )
    return "\n".join(lines)


def render_comment(report: GateReport) -> str:
    """The full markdown comment for `report`, one of four shapes.

    Clean (no regression), regressed-with-a-named-step (the brief's
    illustrative shape), regressed-but-unconfirmed (every new failure's
    shortlist came up empty), and an error, each rendered by its own
    helper so a change to one shape cannot silently reformat another.
    """
    if report.error is not None:
        return _error_comment(report)
    if not report.comparison.is_regression:
        return _clean_comment(report)
    if report.decisive is None:
        return _regression_without_decisive_step(report)
    return _regression_comment(report)
