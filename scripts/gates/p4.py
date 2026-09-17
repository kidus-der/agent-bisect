#!/usr/bin/env python
"""P4 gate: the estimator, proven on synthetic runs with a planted causal step.

    uv run python scripts/gates/p4.py

Zero network calls. 200 synthetic runs from a master seed fixed in
`docs/decisions/0006-p4-synthetic-design.md`; every step of every run is tested,
so the multiple-testing burden on the earliest-step blame rule is the worst
case (no judge shortlist at this phase).

Gate, pre-registered in `docs/decisions/0001-preregistration.md`:

1. the planted step is found in >= 95% of runs, and
2. 95% CI coverage of the true effect is within [0.92, 0.98], measured on the
   **fixed N = 16 design** (a single look, no early stopping).

Coverage is reported twice. The sequential number is the coverage of the
interval as the stopping procedure actually reports it, and it is expected to
be worse: repeated looks at a fixed-coverage interval inflate its error rate and
nothing here corrects for that. Publishing the distortion is the point, so the
gated number is the fixed-design one and the sequential one is report-only.
Neither is tuned; a failure stays failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from agent_bisect.attribution.estimate import (
    DEFAULT_CONF,
    DEFAULT_MAX_N,
    OBF_CRITICAL_Z,
    RunEstimate,
    SequentialConfig,
    confidence_for_z,
    estimate_run,
    newcombe_diff_interval,
    wilson_interval,
)
from agent_bisect.attribution.fakes import FakeRunSpec, ScriptedSampler, sample_run_specs

MASTER_SEED = 20260917
N_RUNS = 200
MIN_FOUND_RATE = 0.95
COVERAGE_WINDOW = (0.92, 0.98)
CONTROL_MODE = "shared"
SEQUENTIAL_CONFIG = SequentialConfig()
# One look means no multiplicity to correct, so the fixed-N diagnostic keeps the
# nominal level (docs/decisions/0008). Its numbers -- including the gated
# coverage -- are therefore unaffected by the efficacy boundary.
FIXED_CONFIG = SequentialConfig(
    batch=DEFAULT_MAX_N, max_n=DEFAULT_MAX_N, efficacy_boundary="none"
)
UNCORRECTED_CONFIG = SequentialConfig(efficacy_boundary="none")
DEFAULT_OUTPUT = Path("runs/p4/gate.json")
_SEED_BYTES = 4


@dataclass(frozen=True, slots=True)
class Criterion:
    """One pre-registered pass/fail bar and the number measured against it."""

    name: str
    value: float
    requirement: str
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "requirement": self.requirement,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """What the estimator made of one synthetic run, under both sampling designs."""

    run_id: str
    n_steps: int
    planted_step: int
    blamed_step: int | None
    outcome: str
    blamed_step_fixed: int | None
    outcome_fixed: str
    sequential_covered: int
    sequential_tested: int
    fixed_covered: int
    fixed_tested: int
    sequential_reruns: int
    fixed_reruns: int
    null_steps: int
    null_flagged_sequential: int
    null_flagged_fixed: int


@dataclass(frozen=True, slots=True)
class GateReport:
    """Every number the P4 evidence quotes, and the verdict."""

    n_runs: int
    master_seed: int
    n_found: int
    found_rate: float
    found_ci: tuple[float, float]
    coverage_fixed: float
    coverage_fixed_counts: tuple[int, int]
    coverage_sequential: float
    coverage_sequential_counts: tuple[int, int]
    mean_reruns_sequential: float
    mean_reruns_fixed: float
    rerun_saving: float
    mean_steps_tested: float
    outcome_counts: dict[str, int]
    criteria: tuple[Criterion, ...]
    # Report-only diagnosis of *why* the gate lands where it does. These are not
    # gated and no threshold depends on them.
    n_found_fixed: int
    found_rate_fixed: float
    outcome_counts_fixed: dict[str, int]
    null_step_flag_rate_sequential: float
    null_step_flag_rate_fixed: float
    null_step_counts: tuple[int, int, int]

    @property
    def passed(self) -> bool:
        return all(criterion.passed for criterion in self.criteria)

    def to_dict(self) -> dict[str, object]:
        return {
            "gate": "P4",
            "n_runs": self.n_runs,
            "master_seed": self.master_seed,
            "config": {
                "batch": SEQUENTIAL_CONFIG.batch,
                "max_n": SEQUENTIAL_CONFIG.max_n,
                "delta": SEQUENTIAL_CONFIG.delta,
                "conf": SEQUENTIAL_CONFIG.conf,
                "control_mode": CONTROL_MODE,
            },
            "planted_step_found": {
                "count": self.n_found,
                "rate": self.found_rate,
                "ci_low": self.found_ci[0],
                "ci_high": self.found_ci[1],
            },
            "coverage_fixed_n16": {
                "rate": self.coverage_fixed,
                "covered": self.coverage_fixed_counts[0],
                "tested": self.coverage_fixed_counts[1],
            },
            "coverage_sequential": {
                "rate": self.coverage_sequential,
                "covered": self.coverage_sequential_counts[0],
                "tested": self.coverage_sequential_counts[1],
            },
            "cost": {
                "mean_reruns_sequential": self.mean_reruns_sequential,
                "mean_reruns_fixed": self.mean_reruns_fixed,
                "rerun_saving": self.rerun_saving,
                "mean_steps_tested": self.mean_steps_tested,
            },
            "outcome_counts": dict(sorted(self.outcome_counts.items())),
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "passed": self.passed,
            "diagnosis_report_only": {
                "planted_step_found_fixed_n16": {
                    "count": self.n_found_fixed,
                    "rate": self.found_rate_fixed,
                },
                "outcome_counts_fixed_n16": dict(sorted(self.outcome_counts_fixed.items())),
                "null_steps_tested": self.null_step_counts[0],
                "null_steps_flagged_sequential": self.null_step_counts[1],
                "null_steps_flagged_fixed_n16": self.null_step_counts[2],
                "null_step_flag_rate_sequential": self.null_step_flag_rate_sequential,
                "null_step_flag_rate_fixed_n16": self.null_step_flag_rate_fixed,
            },
        }


def classify_outcome(blamed_step: int | None, planted_step: int) -> str:
    """`found`, or how the blame missed: an `earlier` step, a `later` one, or `none`."""
    if blamed_step is None:
        return "none"
    if blamed_step == planted_step:
        return "found"
    return "earlier" if blamed_step < planted_step else "later"


def evaluate_criteria(found_rate: float, coverage_fixed: float) -> tuple[Criterion, ...]:
    """The two pre-registered bars. Thresholds are constants; never arguments."""
    low, high = COVERAGE_WINDOW
    return (
        Criterion(
            name="planted step found",
            value=found_rate,
            requirement=f">= {MIN_FOUND_RATE}",
            passed=found_rate >= MIN_FOUND_RATE,
        ),
        Criterion(
            name="coverage (fixed N=16)",
            value=coverage_fixed,
            requirement=f"in [{low}, {high}]",
            passed=low <= coverage_fixed <= high,
        ),
    )


def _sampler_seed(master_seed: int, index: int) -> int:
    payload = f"p4:{master_seed}:{index}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=_SEED_BYTES).digest(), "big")


def _coverage(estimate: RunEstimate, spec: FakeRunSpec) -> tuple[int, int]:
    """How many tested steps had the true effect inside the reported interval."""
    covered = sum(
        1
        for effect in estimate.step_effects
        if effect.interval.contains(spec.true_effect(effect.step))
    )
    return covered, len(estimate.step_effects)


def _null_steps_flagged(estimate: RunEstimate, spec: FakeRunSpec, delta: float) -> int:
    """Truly-null steps (before the fault, true effect 0) whose interval cleared delta.

    Report-only diagnosis of the multiple-testing burden: a false flag here only
    costs the run if it is also the earliest flagged step.
    """
    return sum(
        1
        for effect in estimate.step_effects
        if effect.step < spec.planted_step and effect.ci_low > delta
    )


def evaluate_run(spec: FakeRunSpec, index: int, master_seed: int) -> RunOutcome:
    """Estimate every step of one run twice: sequentially, and at a fixed N = 16."""
    sampler = ScriptedSampler(spec)
    seed = _sampler_seed(master_seed, index)
    tested_steps = tuple(spec.steps)

    sequential = estimate_run(tested_steps, sampler, SEQUENTIAL_CONFIG, CONTROL_MODE, seed=seed)
    fixed = estimate_run(tested_steps, sampler, FIXED_CONFIG, CONTROL_MODE, seed=seed)
    sequential_covered, sequential_tested = _coverage(sequential, spec)
    fixed_covered, fixed_tested = _coverage(fixed, spec)

    return RunOutcome(
        run_id=spec.run_id,
        n_steps=spec.n_steps,
        planted_step=spec.planted_step,
        blamed_step=sequential.blamed_step,
        outcome=classify_outcome(sequential.blamed_step, spec.planted_step),
        blamed_step_fixed=fixed.blamed_step,
        outcome_fixed=classify_outcome(fixed.blamed_step, spec.planted_step),
        sequential_covered=sequential_covered,
        sequential_tested=sequential_tested,
        fixed_covered=fixed_covered,
        fixed_tested=fixed_tested,
        sequential_reruns=sequential.total_reruns,
        fixed_reruns=fixed.total_reruns,
        null_steps=spec.planted_step - 1,
        null_flagged_sequential=_null_steps_flagged(sequential, spec, SEQUENTIAL_CONFIG.delta),
        null_flagged_fixed=_null_steps_flagged(fixed, spec, FIXED_CONFIG.delta),
    )


def build_report(outcomes: tuple[RunOutcome, ...], master_seed: int) -> GateReport:
    n_runs = len(outcomes)
    counts = Counter(outcome.outcome for outcome in outcomes)
    n_found = counts["found"]
    found_interval = wilson_interval(n_found, n_runs)

    sequential_covered = sum(outcome.sequential_covered for outcome in outcomes)
    sequential_tested = sum(outcome.sequential_tested for outcome in outcomes)
    fixed_covered = sum(outcome.fixed_covered for outcome in outcomes)
    fixed_tested = sum(outcome.fixed_tested for outcome in outcomes)
    mean_sequential = sum(outcome.sequential_reruns for outcome in outcomes) / n_runs
    mean_fixed = sum(outcome.fixed_reruns for outcome in outcomes) / n_runs

    counts_fixed = Counter(outcome.outcome_fixed for outcome in outcomes)
    null_tested = sum(outcome.null_steps for outcome in outcomes)
    null_sequential = sum(outcome.null_flagged_sequential for outcome in outcomes)
    null_fixed = sum(outcome.null_flagged_fixed for outcome in outcomes)

    coverage_fixed = fixed_covered / fixed_tested
    return GateReport(
        n_runs=n_runs,
        master_seed=master_seed,
        n_found=n_found,
        found_rate=n_found / n_runs,
        found_ci=(found_interval.low, found_interval.high),
        coverage_fixed=coverage_fixed,
        coverage_fixed_counts=(fixed_covered, fixed_tested),
        coverage_sequential=sequential_covered / sequential_tested,
        coverage_sequential_counts=(sequential_covered, sequential_tested),
        mean_reruns_sequential=mean_sequential,
        mean_reruns_fixed=mean_fixed,
        rerun_saving=1.0 - mean_sequential / mean_fixed,
        mean_steps_tested=fixed_tested / n_runs,
        outcome_counts={key: counts.get(key, 0) for key in ("found", "earlier", "later", "none")},
        criteria=evaluate_criteria(n_found / n_runs, coverage_fixed),
        n_found_fixed=counts_fixed["found"],
        found_rate_fixed=counts_fixed["found"] / n_runs,
        outcome_counts_fixed={
            key: counts_fixed.get(key, 0) for key in ("found", "earlier", "later", "none")
        },
        null_step_flag_rate_sequential=null_sequential / null_tested,
        null_step_flag_rate_fixed=null_fixed / null_tested,
        null_step_counts=(null_tested, null_sequential, null_fixed),
    )


def run_gate(n_runs: int = N_RUNS, master_seed: int = MASTER_SEED) -> GateReport:
    """Generate the synthetic runs, estimate them all, and score the gate."""
    specs = sample_run_specs(n_runs, master_seed=master_seed)
    outcomes = tuple(
        evaluate_run(spec, index=index, master_seed=master_seed)
        for index, spec in enumerate(specs)
    )
    return build_report(outcomes, master_seed)


def write_report(report: GateReport, destination: Path = DEFAULT_OUTPUT) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _verdict(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def format_report(report: GateReport) -> str:
    """The human-readable gate result; the JSON file carries the same numbers."""
    found_count = f"{report.n_found}/{report.n_runs}"
    fixed_covered, fixed_tested = report.coverage_fixed_counts
    sequential_covered, sequential_tested = report.coverage_sequential_counts
    misses = report.outcome_counts
    lines = [
        "P4 gate - estimator on synthetic runs with a planted causal step",
        f"  runs {report.n_runs} - master seed {report.master_seed} - "
        f"batch {SEQUENTIAL_CONFIG.batch} - max_n {SEQUENTIAL_CONFIG.max_n} - "
        f"delta {SEQUENTIAL_CONFIG.delta} - control {CONTROL_MODE}",
        f"  planted step found    {found_count} = {report.found_rate:.4f}  "
        f"95% CI [{report.found_ci[0]:.4f}, {report.found_ci[1]:.4f}]",
        f"  coverage fixed N=16   {fixed_covered}/{fixed_tested} = {report.coverage_fixed:.4f}",
        f"  coverage sequential   {sequential_covered}/{sequential_tested} = "
        f"{report.coverage_sequential:.4f}  (report only, not gated)",
        f"  mean re-runs per run  sequential {report.mean_reruns_sequential:.1f} - "
        f"fixed {report.mean_reruns_fixed:.1f} - saving {report.rerun_saving:.1%}",
        f"  mean steps tested     {report.mean_steps_tested:.1f}",
        f"  misses                earlier {misses['earlier']} - later {misses['later']} - "
        f"none {misses['none']}",
        "  -- diagnosis, report only --",
        f"  found at fixed N=16   {report.n_found_fixed}/{report.n_runs} = "
        f"{report.found_rate_fixed:.4f}  misses: "
        f"earlier {report.outcome_counts_fixed['earlier']} - "
        f"later {report.outcome_counts_fixed['later']} - "
        f"none {report.outcome_counts_fixed['none']}",
        f"  null steps flagged    sequential {report.null_step_counts[1]}/"
        f"{report.null_step_counts[0]} = {report.null_step_flag_rate_sequential:.4f} - "
        f"fixed {report.null_step_counts[2]}/{report.null_step_counts[0]} = "
        f"{report.null_step_flag_rate_fixed:.4f}",
    ]
    lines += [
        f"  [{_verdict(criterion.passed)}] {criterion.name}: "
        f"{criterion.value:.4f} (requires {criterion.requirement})"
        for criterion in report.criteria
    ]
    lines.append(f"  RESULT: {_verdict(report.passed)}")
    return "\n".join(lines)


POWER_CONTROL_RATES = (0.00, 0.10, 0.15)
POWER_TREATED_RATES = (0.60, 0.70, 0.80, 0.90)


def _binomial_pmf(successes: int, n: int, prob: float) -> float:
    return math.comb(n, successes) * prob**successes * (1.0 - prob) ** (n - successes)


def detection_power(
    treated_prob: float,
    control_prob: float,
    n: int = DEFAULT_MAX_N,
    delta: float = SEQUENTIAL_CONFIG.delta,
    conf: float = DEFAULT_CONF,
) -> float:
    """P(Newcombe lower bound > delta) at `n` per arm, by exact enumeration.

    Every (x_treated, x_control) pair is weighted by its binomial probability --
    no simulation, so the number is exact to floating point.
    """
    return sum(
        _binomial_pmf(treated, n, treated_prob)
        * _binomial_pmf(control, n, control_prob)
        * (newcombe_diff_interval(treated, n, control, n, conf=conf).low > delta)
        for treated in range(n + 1)
        for control in range(n + 1)
    )


def format_power_table(n: int = DEFAULT_MAX_N) -> str:
    """Why N = 16 caps P4 accuracy, independent of any seed or simulation."""
    obf_conf = confidence_for_z(OBF_CRITICAL_Z[-1])
    header = "  control |" + "".join(f"  treated {p:.2f}" for p in POWER_TREATED_RATES)
    lines = [
        f"Detection power at N = {n} per arm: P(Newcombe lower bound > "
        f"delta = {SEQUENTIAL_CONFIG.delta}), exact enumeration",
        f"  nominal 95% (the reported interval) and OBF final look "
        f"(z = {OBF_CRITICAL_Z[-1]}, conf {obf_conf:.4f})",
        "",
        header,
        "  " + "-" * (len(header) - 2),
    ]
    for control in POWER_CONTROL_RATES:
        nominal = "".join(
            f"       {detection_power(p, control, n):.3f}" for p in POWER_TREATED_RATES
        )
        boundary = "".join(
            f"       {detection_power(p, control, n, conf=obf_conf):.3f}"
            for p in POWER_TREATED_RATES
        )
        lines.append(f"     {control:.2f} |{nominal}   (95%)")
        lines.append(f"          |{boundary}   (OBF final)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the P4 estimator gate.")
    parser.add_argument("--runs", type=int, default=N_RUNS)
    parser.add_argument("--seed", type=int, default=MASTER_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--power-table",
        action="store_true",
        help="print the exact N=16 detection-power table and exit 0",
    )
    args = parser.parse_args(argv)

    if args.power_table:
        sys.stdout.write(format_power_table() + "\n")
        return 0

    report = run_gate(n_runs=args.runs, master_seed=args.seed)
    write_report(report, args.out)
    sys.stdout.write(format_report(report) + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
