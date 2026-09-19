#!/usr/bin/env python
"""One live fork of one dev item, measured. The first thing P5 spends on.

    uv run python scripts/p5_probe.py [--item N] [--arm control|treated]

Why this exists before `bisect eval`: the whole P5 budget follows from two
numbers nobody has measured yet — how many LLM calls one fork costs and
how long one takes — and every integration hazard (the standing fault
being restored, tau2's NL-assertion judge being repointed, a prefix that
diverges) shows up on the first fork or not at all. A handful of calls
here decides how the remaining tens of thousands are spent.

It is dev-split work: it touches no test item, and its forks are ordinary
recorded runs that `bisect eval` will reuse rather than re-buy.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from agent_bisect.adapters.tau2 import recording_session
from agent_bisect.adapters.tau2_fork import Tau2ForkExecutor
from agent_bisect.adapters.tau2_truth import Tau2TruthResolver
from agent_bisect.attribution.interventions import Resample, TruthfulToolResult
from agent_bisect.attribution.search import RerunRequest, rerun_id
from agent_bisect.bench.manifest import DEFAULT_MANIFEST_PATH, load_frozen
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.replay import NoOpIntervention
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

PHASE = "P5"
#: A single fork cannot legitimately need more than this. A cap is the
#: only thing that makes a probe safe to run unattended.
PROBE_CALL_CAP = 200
RUNS_DIR = Path("runs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure one live fork.")
    parser.add_argument("--item", type=int, default=0, help="Index into the dev split.")
    parser.add_argument("--arm", choices=("control", "treated"), default="control")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)

    frozen = load_frozen(args.manifest)
    item = frozen.split("dev")[args.item]
    store = BlobStore(RUNS_DIR)
    reader = TapeReader(RUNS_DIR)
    steps = reader.get_steps(item.run_id)
    step = reader.get_step(item.run_id, item.planted_step)

    intervention = NoOpIntervention()
    if args.arm == "treated":
        intervention = (
            TruthfulToolResult(step=item.planted_step).with_truth(
                Tau2TruthResolver(item.domain, item.task_id, store)
            )
            if step.actor == "tool"
            else Resample(step=item.planted_step)
        )

    ledger = BudgetLedger(RUNS_DIR / "ledger.sqlite", max_calls=PROBE_CALL_CAP,
                          cap_scope="phase")
    before = ledger.totals_per_phase().get(PHASE, 0)
    executor = Tau2ForkExecutor(
        store=store, reader=reader, tape=TapeWriter(RUNS_DIR)
    )
    request = RerunRequest(
        parent_run_id=item.run_id,
        run_id=rerun_id(item.run_id, arm=args.arm, step=item.planted_step, seed=1, draw=0),
        fork_step=item.planted_step,
        arm=args.arm,
        intervention=intervention,
        seed=1,
        prefix_tools="snapshot",
        unsafe_positional=False,
    )

    started = time.monotonic()
    outcome = executor.run(request)
    elapsed = time.monotonic() - started
    spent = ledger.totals_per_phase().get(PHASE, 0) - before

    print(json.dumps({
        "item_id": item.item_id,
        "domain": item.domain,
        "task_id": item.task_id,
        "run_id": item.run_id,
        "parent_steps": len(steps),
        "planted_step": item.planted_step,
        "planted_actor": step.actor,
        "arm": args.arm,
        "intervention": intervention.name,
        "passed": outcome.passed,
        "fork_steps": outcome.n_steps,
        "live_llm_calls": outcome.calls,
        "unguarded_calls": outcome.unguarded_calls,
        "ledger_calls_spent": spent,
        "seconds": round(elapsed, 1),
        "reused_from_tape": executor.reused,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    with recording_session(
        ledger=BudgetLedger(RUNS_DIR / "ledger.sqlite"), phase=PHASE
    ):
        raise SystemExit(main())
