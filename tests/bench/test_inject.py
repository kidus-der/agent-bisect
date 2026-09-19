"""The injection pipeline, driven by a fake runner.

The pipeline's job is the funnel of `docs/brief/summary.md` §3: record
successes, keep the stable ones, plant a fault at a stratified tool step,
re-run N = 4, keep it if it flips. What is tested here is that funnel —
the thresholds, the caps, the resume, and the rule that nothing is ever
dropped silently. Driving it against tau2's real orchestrator is
`tests/test_tau2_inject_e2e.py`.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from agent_bisect.bench.inject import (
    BaseRun,
    InjectConfig,
    Journal,
    RerunResult,
    ToolStep,
    collect,
)
from agent_bisect.core.budget import BudgetExceededError
from agent_bisect.core.llm import AuthenticationError

AIRLINE = [("airline", str(index)) for index in range(4)]


def tool_step(step_idx: int) -> ToolStep:
    return ToolStep(
        step_idx=step_idx,
        tool_name="get_reservation_details",
        # Distinct arguments per step: a standing fault matches by call,
        # so two identical calls in one run cannot both be candidates.
        tool_args={"reservation_id": f"HAT{step_idx:03d}"},
        result={"id": f"c{step_idx}", "role": "tool", "requestor": "assistant",
                "error": False,
                "content": json.dumps({"reservation_id": f"HAT{step_idx:03d}",
                                       "status": "confirmed",
                                       "total_baggages": 2, "price": 122})},
        result_ref=f"{step_idx:064d}",
        downstream=f"the agent quotes HAT{step_idx:03d} back",
    )


class FakeRunner:
    """A runner whose outcomes are decided by rules, not by a model.

    `faulted_passes` says how many of the N faulted re-runs pass, so a
    test can make a candidate flip (0 of 4) or not (all 4).
    """

    def __init__(
        self,
        *,
        base_passes: bool = True,
        stability_passes: int = 4,
        faulted_passes: int = 0,
        tool_steps_per_run: int = 9,
        infra_failures: int = 0,
    ) -> None:
        self.base_passes = base_passes
        self.stability_passes = stability_passes
        self.faulted_passes = faulted_passes
        self.tool_steps_per_run = tool_steps_per_run
        self.infra_failures = infra_failures
        self.recorded: list[str] = []
        self.resamples: list[str] = []
        self.forks: list[tuple[str, int, str]] = []

    def record_base(self, domain: str, task_id: str, trial: int) -> BaseRun:
        run_id = f"{domain}-{task_id}-t{trial}"
        self.recorded.append(run_id)
        return BaseRun(run_id=run_id, domain=domain, task_id=task_id,
                       passed=self.base_passes, steps=20)

    def fresh_run(self, domain: str, task_id: str, *, attempt: int) -> RerunResult:
        run_id = f"{domain}-{task_id}-t{100 + attempt}"
        self.resamples.append(run_id)
        return RerunResult(run_id=run_id, passed=attempt < self.stability_passes)

    def tool_steps(self, base_run_id: str) -> list[ToolStep]:
        return [tool_step(index * 2 + 1) for index in range(self.tool_steps_per_run)]

    def fault_fork(self, base_run_id, *, run_id, step_idx, tool_name, tool_args,
                   faulted_result, fault_type, seed) -> RerunResult:
        if self.infra_failures > 0:
            self.infra_failures -= 1
            raise RuntimeError("infrastructure_error: the provider hung up")
        self.forks.append((base_run_id, step_idx, run_id))
        index = len([f for f in self.forks if f[0] == base_run_id and f[1] == step_idx]) - 1
        return RerunResult(run_id=run_id, passed=index < self.faulted_passes)


def config_for(**overrides) -> InjectConfig:
    # No backoff in tests: the re-queue pass is what is under test, not
    # the minute it waits for a provider to recover.
    return InjectConfig(pass_backoff_seconds=0.0, **overrides)


def run(tmp_path, runner, **overrides):
    return collect(
        runner, tasks=AIRLINE, journal=Journal(tmp_path), config=config_for(**overrides)
    )


# ---- the funnel ----


def test_a_flipping_fault_is_kept_and_labelled(tmp_path):
    result = run(tmp_path, FakeRunner(faulted_passes=0))

    assert result.items
    item = result.items[0]
    assert item["planted_step"] in {step.step_idx for step in FakeRunner().tool_steps("x")}
    assert item["faulted_pass_rate"] == 0.0
    assert item["base_pass_rate"] == 1.0
    assert item["oracle"]["tool_result_ref"].endswith(str(item["planted_step"]))
    assert item["intervention"]["name"] == "replace_tool_result"


def test_a_fault_that_does_not_flip_the_run_is_rejected(tmp_path):
    result = run(tmp_path, FakeRunner(faulted_passes=4))

    assert result.items == []
    assert result.counts["rejected_not_flipped"] > 0


def test_the_keep_rule_is_the_pre_registered_one_quarter(tmp_path):
    kept = run(tmp_path, FakeRunner(faulted_passes=1))
    not_kept = run(tmp_path / "other", FakeRunner(faulted_passes=2))

    assert kept.items
    assert not_kept.items == []


def test_an_unstable_base_run_is_never_faulted(tmp_path):
    runner = FakeRunner(stability_passes=2)

    result = run(tmp_path, runner)

    assert result.items == []
    assert runner.forks == []
    # Two base trials per task: a task is the split unit, so a second
    # trajectory is a second chance at the task, not a second sample.
    assert result.counts["rejected_unstable"] == len(AIRLINE) * InjectConfig().base_trials


def test_a_base_run_that_failed_is_never_faulted(tmp_path):
    runner = FakeRunner(base_passes=False)

    result = run(tmp_path, runner)

    assert result.items == []
    assert runner.resamples == []
    assert result.counts["rejected_base_failed"] == len(AIRLINE) * InjectConfig().base_trials


def test_stability_is_the_pre_registered_three_of_four(tmp_path):
    stable = run(tmp_path, FakeRunner(stability_passes=3))

    assert stable.items


def test_a_task_whose_first_base_run_fails_gets_a_second_trajectory(tmp_path):
    """A task is the unit the split is grouped by, so recording it again
    is a second chance at the task rather than a second sample of the
    same run (`0017` section 9)."""

    class FailsOnce(FakeRunner):
        def record_base(self, domain, task_id, trial):
            base = super().record_base(domain, task_id, trial)
            return base if trial > 0 else replace(base, passed=False)

    runner = FailsOnce()
    result = run(tmp_path, runner)

    assert result.items
    assert result.counts["rejected_base_failed"] == len(AIRLINE)
    assert any(run_id.endswith("t1") for run_id in runner.recorded)


def test_one_base_trial_means_one_chance(tmp_path):
    class AlwaysFails(FakeRunner):
        def record_base(self, domain, task_id, trial):
            return replace(super().record_base(domain, task_id, trial), passed=False)

    result = run(tmp_path, AlwaysFails(), base_trials=1)

    assert result.counts["rejected_base_failed"] == len(AIRLINE)


# ---- the caps ----


def test_no_base_run_contributes_more_than_three_faults(tmp_path):
    result = run(tmp_path, FakeRunner(), attempts_per_bucket=3)

    per_run: dict[str, int] = {}
    for item in result.items:
        per_run[item["base_run_id"]] = per_run.get(item["base_run_id"], 0) + 1
    assert max(per_run.values()) <= 3


def test_no_base_run_contributes_two_faults_from_one_bucket(tmp_path):
    result = run(tmp_path, FakeRunner(), attempts_per_bucket=3)

    seen = {(item["base_run_id"], item["position_bucket"]) for item in result.items}
    assert len(seen) == len(result.items)


def test_collection_stops_once_the_target_is_reached(tmp_path):
    result = run(tmp_path, FakeRunner(), target_items=2)

    assert len(result.items) == 2
    assert result.stopped_reason == "target reached"


def test_every_fault_type_is_used_across_the_dataset(tmp_path):
    result = run(tmp_path, FakeRunner(), attempts_per_bucket=1)

    assert len({item["fault_type"] for item in result.items}) >= 3


def test_every_position_bucket_is_represented(tmp_path):
    result = run(tmp_path, FakeRunner(), attempts_per_bucket=1)

    assert {item["position_bucket"] for item in result.items} == {"early", "middle", "late"}


# ---- nothing is dropped silently ----


def test_every_candidate_is_logged_with_its_verdict(tmp_path):
    journal = Journal(tmp_path)
    collect(FakeRunner(faulted_passes=4), tasks=AIRLINE, journal=journal,
            config=config_for())

    verdicts = [event for event in journal.events() if event["kind"] == "candidate"]
    assert verdicts
    assert all(event["status"] in {"kept", "rejected"} for event in verdicts)
    assert all(event.get("reason") for event in verdicts if event["status"] == "rejected")


def test_the_funnel_counts_add_up(tmp_path):
    result = run(tmp_path, FakeRunner(faulted_passes=4))

    assert result.counts["candidates"] == (
        result.counts["kept"] + result.counts["rejected_not_flipped"]
        + result.counts["rejected_unplantable"] + result.counts["rejected_repeated_call"]
    )


def test_a_call_that_already_happened_earlier_is_never_faulted(tmp_path):
    """A standing fault matches by call, so faulting a repeated call would
    corrupt its earlier occurrences and rewrite the prefix
    (`docs/decisions/0016-persistent-planted-fault.md`)."""

    class SameCallTwice(FakeRunner):
        def tool_steps(self, base_run_id):
            return [replace(tool_step(index * 2 + 1), tool_args={"reservation_id": "SAME"})
                    for index in range(6)]

    result = run(tmp_path, SameCallTwice())

    assert result.counts["rejected_repeated_call"] > 0
    assert {item["planted_step"] for item in result.items} <= {1}


# ---- infrastructure never decides anything ----


def test_a_task_lost_to_infrastructure_goes_back_on_the_queue(tmp_path):
    """An infra failure decides nothing, so it must not be able to remove
    a task from the collection simply by happening."""

    class FlakyOnce(FakeRunner):
        def __init__(self) -> None:
            super().__init__()
            self._failed: set[str] = set()

        def fresh_run(self, domain, task_id, *, attempt):
            if task_id not in self._failed:
                self._failed.add(task_id)
                raise RuntimeError("504 Gateway Timeout")
            return super().fresh_run(domain, task_id, attempt=attempt)

    result = run(tmp_path, FlakyOnce())

    assert result.counts["requeued"] > 0
    assert result.counts["parked"] == 0
    assert result.items


def test_tasks_that_never_clear_are_parked_and_reported(tmp_path):
    class AlwaysBroken(FakeRunner):
        def fresh_run(self, domain, task_id, *, attempt):
            raise RuntimeError("504 Gateway Timeout")

    result = run(tmp_path, AlwaysBroken())

    assert result.counts["parked"] == len(AIRLINE)
    assert "parked" in result.stopped_reason


def test_a_parked_collection_short_of_its_target_is_not_reported_as_done(tmp_path):
    class AlwaysBroken(FakeRunner):
        def fresh_run(self, domain, task_id, *, attempt):
            raise RuntimeError("504 Gateway Timeout")

    collect(AlwaysBroken(), tasks=AIRLINE, journal=Journal(tmp_path / "p3"),
            config=config_for(), runs_dir=tmp_path)

    status = json.loads((tmp_path / "p3" / "status.json").read_text())
    assert status["state"] == "failed"
    assert "parked" in status["error"]


def test_the_transport_error_mix_is_counted(tmp_path):
    from agent_bisect.core.llm import TransportError

    class Gateways(FakeRunner):
        def fresh_run(self, domain, task_id, *, attempt):
            raise TransportError("litellm.Timeout: OpenAIException - Error code: 504")

    result = run(tmp_path, Gateways())

    assert result.counts["transport_504"] > 0


def test_the_gate_halves_in_flight_under_a_storm_and_creeps_back():
    from agent_bisect.bench.inject import _Gate

    gate = _Gate(allowed=16, minimum=2)

    for _ in range(_Gate.STORM):
        gate.on_transport_failure()
    halved = gate.allowed
    for _ in range(_Gate.RECOVERY):
        gate.on_success()

    assert halved == 8
    assert gate.allowed == 9


def test_the_gate_never_falls_below_its_minimum():
    from agent_bisect.bench.inject import _Gate

    gate = _Gate(allowed=4, minimum=2)

    for _ in range(_Gate.STORM * 10):
        gate.on_transport_failure()

    assert gate.allowed == 2


# ---- concurrency ----


def test_tasks_run_concurrently_without_losing_any(tmp_path):
    """Several task threads share the tallies, the fault-type balance and
    the decision log; only the bookkeeping needs guarding, because each
    task owns its own runs."""
    journal = Journal(tmp_path)
    tasks = [("airline", str(index)) for index in range(12)]

    result = collect(FakeRunner(), tasks=tasks, journal=journal,
                     config=config_for(attempts_per_bucket=1), concurrency=6)

    assert result.counts["base_recorded"] == len(tasks)
    assert result.counts["candidates"] == sum(
        result.counts[name] for name in
        ("kept", "rejected_not_flipped", "rejected_unplantable", "rejected_repeated_call")
    )
    verdicts = [event for event in journal.events() if event["kind"] == "candidate"]
    assert len(verdicts) == result.counts["candidates"]


def test_concurrent_collection_breaks_the_same_steps_as_a_serial_one(tmp_path):
    """Which steps are faulted is fixed by the seed; which fault TYPE each
    one gets is not, because the balancer is global and draws in whatever
    order the threads finish. The balance still holds — only the
    assignment moves — so a concurrent collection is reproducible in what
    it tries, not in which type each kept item ended up with."""
    tasks = [("airline", str(index)) for index in range(6)]
    serial = collect(FakeRunner(), tasks=tasks, journal=Journal(tmp_path / "one"),
                     config=config_for(attempts_per_bucket=1))

    parallel = collect(FakeRunner(), tasks=tasks, journal=Journal(tmp_path / "two"),
                       config=config_for(attempts_per_bucket=1), concurrency=4)

    def steps(result):
        return sorted((item["task_id"], item["planted_step"]) for item in result.items)

    assert steps(parallel) == steps(serial)
    assert len({item["fault_type"] for item in parallel.items}) >= 3


def test_a_concurrent_collection_stops_on_the_target_too(tmp_path):
    tasks = [("airline", str(index)) for index in range(12)]

    result = collect(FakeRunner(), tasks=tasks, journal=Journal(tmp_path),
                     config=config_for(target_items=2), concurrency=4)

    assert result.stopped_reason == "target reached"


# ---- the stop rule ----


def test_the_wall_clock_budget_stops_the_collection(tmp_path):
    result = run(tmp_path, FakeRunner(), max_seconds=0.0, floor_items=0)

    assert result.stopped_reason == "time budget reached"
    assert result.items == []


def test_the_budget_never_cuts_below_the_floor_the_gate_needs(tmp_path):
    """Past the deadline the collection keeps going until there is a
    dataset at all (`docs/decisions/0012-p3-floor.md`)."""
    result = run(tmp_path, FakeRunner(), max_seconds=0.0, floor_items=3)

    assert len(result.items) >= 3
    assert result.stopped_reason == "time budget reached"


def test_a_shard_stops_on_the_shared_count_not_its_own(tmp_path):
    """Two shards write one journal, so the second sees the first's items
    and stops when the dataset is big enough."""
    journal = Journal(tmp_path)
    collect(FakeRunner(), tasks=AIRLINE[:2], journal=journal, config=config_for())
    first = _kept_on_disk(journal)

    second = collect(FakeRunner(), tasks=AIRLINE[2:], journal=journal,
                     config=config_for(target_items=first))

    assert second.stopped_reason == "target reached"
    assert _kept_on_disk(journal) == first


def _kept_on_disk(journal: Journal) -> int:
    return sum(1 for record in journal.all("candidate") if record.get("status") == "kept")


# ---- telling the dashboard where we are ----


def test_progress_is_published_where_the_live_page_reads_it(tmp_path):
    from agent_bisect.server.schemas_live import JobStatus

    collect(FakeRunner(), tasks=AIRLINE, journal=Journal(tmp_path / "p3"),
            config=config_for(target_items=100), runs_dir=tmp_path,
            calls_spent=lambda: 412)

    status = json.loads((tmp_path / "p3" / "status.json").read_text())
    assert status["state"] == "done"
    assert status["kind"] == "inject"
    assert status["calls_spent"] == 412
    assert status["items_done"] > 0
    JobStatus(job_id="p3", **status)


def test_a_clean_stop_is_published_as_a_failure(tmp_path):
    class Broke(FakeRunner):
        def fault_fork(self, *args, **kwargs):
            raise BudgetExceededError("budget exceeded")

    collect(Broke(), tasks=AIRLINE, journal=Journal(tmp_path / "p3"),
            config=config_for(), runs_dir=tmp_path)

    status = json.loads((tmp_path / "p3" / "status.json").read_text())
    assert status["state"] == "failed"
    assert "budget" in status["error"]


def test_nothing_is_published_without_a_runs_directory(tmp_path):
    run(tmp_path, FakeRunner())

    assert not (tmp_path / "p3" / "status.json").exists()


# ---- resume ----


def test_a_second_pass_pays_for_nothing_twice(tmp_path):
    journal = Journal(tmp_path)
    first = collect(FakeRunner(), tasks=AIRLINE, journal=journal, config=config_for())
    runner = FakeRunner()

    second = collect(runner, tasks=AIRLINE, journal=journal, config=config_for())

    assert [item["item_id"] for item in second.items] == [item["item_id"] for item in first.items]
    assert runner.recorded == []
    assert runner.resamples == []
    assert runner.forks == []


# ---- infrastructure ----


def test_an_infrastructure_failure_is_retried_not_scored(tmp_path):
    runner = FakeRunner(infra_failures=2)

    result = run(tmp_path, runner)

    assert result.items
    assert result.counts["infra_retries"] == 2


def test_an_infrastructure_failure_that_never_clears_abandons_the_candidate(tmp_path):
    runner = FakeRunner(infra_failures=999)

    result = run(tmp_path, runner)

    assert result.items == []
    assert result.counts["rejected_infra"] > 0


def test_a_spent_budget_stops_the_run_cleanly(tmp_path):
    class Broke(FakeRunner):
        def fault_fork(self, *args, **kwargs):
            raise BudgetExceededError("budget exceeded: cap is 10 calls")

    result = run(tmp_path, Broke())

    assert result.stopped_reason == "budget exhausted"
    assert result.items == []


def test_a_rejected_key_stops_the_run_cleanly(tmp_path):
    class Unauthorised(FakeRunner):
        def record_base(self, *args, **kwargs):
            raise AuthenticationError("401 unauthorized")

    result = run(tmp_path, Unauthorised())

    assert result.stopped_reason == "authentication rejected"


# ---- the journal ----


def test_the_journal_remembers_and_replays(tmp_path):
    journal = Journal(tmp_path)

    journal.write("base", "airline-0-t0", {"run_id": "airline-0-t0", "passed": True})

    assert journal.read("base", "airline-0-t0") == {"run_id": "airline-0-t0", "passed": True}
    assert journal.read("base", "absent") is None
    assert len(journal.all("base")) == 1


def test_the_journal_is_safe_for_keys_with_separators(tmp_path):
    journal = Journal(tmp_path)

    journal.write("candidate", "airline/0:k3", {"ok": True})

    assert journal.read("candidate", "airline/0:k3") == {"ok": True}


def test_an_unreadable_journal_entry_is_treated_as_absent(tmp_path):
    journal = Journal(tmp_path)
    journal.write("base", "airline-0-t0", {"run_id": "x"})
    next(iter((tmp_path / "base").glob("*.json"))).write_text("{ not json")

    with pytest.raises(ValueError, match="airline-0-t0"):
        journal.read("base", "airline-0-t0")
