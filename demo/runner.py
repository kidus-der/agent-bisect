"""`python -m demo.runner`: record the whole demo suite, once.

Runs every scenario in `demo.tasks.SCENARIOS` `--runs` times each against
tau2's real orchestrator (vendored "mock" domain), scripted throughout by
`demo.agent.demo_completion` -- no network call, no secret. Writes a JSON
summary (pass/fail per run, per-scenario pass rate) and the tape/blob store
those runs were recorded into, so `demo.blame` can fork them later without
re-running anything.

Called directly by a developer (`uv run python -m demo.runner --seed 1
--out runs/demo`) and by `bisect gate`, once per side (base, head), each
inside its own git worktree -- see `docs/decisions/0019-gate-rule.md`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_bisect.adapters.tau2 import RunSpec, record_run, recording_session
from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir

from demo.agent import demo_completion, policy
from demo.faults import plant_wrong_lookup_key
from demo.harness import UNUSED_API_BASE, UNUSED_API_KEY, Store, ledger_for, no_limiter
from demo.tasks import (
    AGENT_MODEL,
    DEFAULT_SEED,
    DOMAIN,
    SCENARIOS,
    USER_MODEL,
    ScenarioSpec,
    run_id_for,
)

DEFAULT_RUNS_PER_SCENARIO = 4

#: The two `update_lookup` scenarios whose `use_correct_task_id` slip is a
#: standing tool fault rather than an agent decision (`demo/faults.py`).
FAULT_INJECTABLE = frozenset(
    {"update_task_from_initialization_data", "update_task_from_initialization_actions"}
)


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    run_index: int
    passed: bool
    faulted: bool


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    task_id: str
    rule_id: str
    runs: tuple[RunResult, ...]

    @property
    def pass_rate(self) -> float:
        return sum(1 for run in self.runs if run.passed) / len(self.runs)


@dataclass(frozen=True, slots=True)
class SuiteResult:
    seed: int
    runs_per_scenario: int
    store_dir: str
    scenarios: tuple[ScenarioResult, ...]

    @property
    def total_passes(self) -> int:
        return sum(run.passed for scenario in self.scenarios for run in scenario.runs)

    @property
    def total_runs(self) -> int:
        return sum(len(scenario.runs) for scenario in self.scenarios)

    @property
    def pass_rate(self) -> float:
        return self.total_passes / self.total_runs

    def to_json(self) -> dict:
        return {
            "seed": self.seed,
            "runs_per_scenario": self.runs_per_scenario,
            "store_dir": self.store_dir,
            "pass_rate": self.pass_rate,
            "total_passes": self.total_passes,
            "total_runs": self.total_runs,
            "scenarios": [
                {
                    "name": scenario.name,
                    "task_id": scenario.task_id,
                    "rule_id": scenario.rule_id,
                    "pass_rate": scenario.pass_rate,
                    "runs": [asdict(run) for run in scenario.runs],
                }
                for scenario in self.scenarios
            ],
        }


def _slips(rule_id: str, run_id: str) -> bool:
    """The same deterministic draw `demo.agent._slips` makes, computed here
    because the fault-planting decision must be made *before* recording."""
    rule = policy().rule(rule_id)
    rng = random.Random(f"{run_id}:{rule_id}")
    return type(policy()).slips(rule, rng)


def _run_spec(scenario: ScenarioSpec, seed: int) -> RunSpec:
    return RunSpec(
        domain=DOMAIN,
        task_id=scenario.task_id,
        agent_model=AGENT_MODEL,
        user_model=USER_MODEL,
        seed=seed,
    )


def _record_plain(store: Store, spec: RunSpec, run_id: str, run_index: int) -> RunResult:
    recorded = record_run(spec, run_id=run_id, store=store.blobs, tape=store.tape)
    assert recorded.outcome is not None, f"{run_id} aborted: {recorded.termination_reason}"
    return RunResult(
        run_id=run_id, run_index=run_index, passed=recorded.outcome.passed, faulted=False
    )


def _run_one(store: Store, scenario: ScenarioSpec, run_index: int, seed: int) -> RunResult:
    run_id = run_id_for(scenario.name, run_index, seed)
    spec = _run_spec(scenario, seed)
    if scenario.name not in FAULT_INJECTABLE:
        return _record_plain(store, spec, run_id, run_index)

    faulted = _slips(scenario.rule_id, run_id)
    if not faulted:
        return _record_plain(store, spec, run_id, run_index)

    clean_run_id = f"{run_id}-clean"
    recorded = record_run(spec, run_id=clean_run_id, store=store.blobs, tape=store.tape)
    assert recorded.outcome is not None, f"{clean_run_id} aborted: {recorded.termination_reason}"
    outcome = plant_wrong_lookup_key(
        parent_run_id=clean_run_id,
        run_id=run_id,
        store=store.blobs,
        reader=store.reader,
        tape=store.tape,
    )
    return RunResult(run_id=run_id, run_index=run_index, passed=outcome.passed, faulted=True)


def run_suite(
    *, seed: int, runs_per_scenario: int, out_dir: Path, scenarios=SCENARIOS
) -> SuiteResult:
    ensure_tau2_data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    store = Store(out_dir / "store")
    results: list[ScenarioResult] = []
    with recording_session(
        ledger=ledger_for(store.root),
        phase="demo",
        completion_fn=demo_completion,
        api_key=UNUSED_API_KEY,
        api_base=UNUSED_API_BASE,
        limiter_for=no_limiter,
    ):
        for scenario in scenarios:
            runs = tuple(
                _run_one(store, scenario, run_index, seed)
                for run_index in range(runs_per_scenario)
            )
            results.append(
                ScenarioResult(
                    name=scenario.name, task_id=scenario.task_id,
                    rule_id=scenario.rule_id, runs=runs,
                )
            )
    return SuiteResult(
        seed=seed,
        runs_per_scenario=runs_per_scenario,
        store_dir=str(store.root),
        scenarios=tuple(results),
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS_PER_SCENARIO)
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = run_suite(seed=args.seed, runs_per_scenario=args.runs, out_dir=args.out)
    summary_path = args.out / "summary.json"
    summary_path.write_text(json.dumps(result.to_json(), indent=2))
    print(json.dumps(result.to_json(), indent=2))  # noqa: T201 - this IS the CLI's output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
