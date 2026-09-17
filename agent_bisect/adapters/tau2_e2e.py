"""Run one τ² airline task end to end with the chosen models — the P0 gate's live check.

This is the smallest possible real exercise of the whole stack: config →
limiter → router → τ² orchestrator → deterministic evaluator → a numeric
reward. `bisect doctor --live` calls it; without `--live` the doctor reads
back the JSON this wrote (`runs/p0/e2e.json`).

`text_run_config()` is the single definition of the τ² settings pinned in
`docs/decisions/0004-p0-probe-protocol.md` §1 — the probe script imports
it too, so the gate's live task and the 20-task probes cannot drift apart.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir
from agent_bisect.adapters.tau2_llm import route_tau2_llm
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.config import redact

DEFAULT_E2E_PATH = Path("runs/p0/e2e.json")
DOMAIN = "airline"
AGENT_IMPLEMENTATION = "llm_agent"
USER_IMPLEMENTATION = "user_simulator"
TAU2_SEED = 300
TAU2_MAX_STEPS = 200
TAU2_MAX_ERRORS = 10
TAU2_TEMPERATURE = 0.0
SEED_UPPER_BOUND = 1000000


def trial_seed(config_seed: int = TAU2_SEED) -> int:
    """The seed τ²'s batch runner derives for trial 0 from `config.seed`."""
    rng = random.Random()
    rng.seed(config_seed)
    return rng.randint(0, SEED_UPPER_BOUND)


def text_run_config(agent_model: str, user_model: str) -> Any:
    """A `TextRunConfig` carrying exactly the τ² defaults pinned in 0004 §1."""
    from tau2.data_model.simulation import TextRunConfig

    # pyright cannot see τ²'s `Annotated[..., Field(default=...)]` defaults and
    # believes every other field is required; they all exist at runtime.
    return TextRunConfig(  # pyright: ignore[reportCallIssue]
        domain=DOMAIN,
        agent=AGENT_IMPLEMENTATION,
        user=USER_IMPLEMENTATION,
        llm_agent=agent_model,
        llm_args_agent={"temperature": TAU2_TEMPERATURE},
        llm_user=user_model,
        llm_args_user={"temperature": TAU2_TEMPERATURE},
        num_trials=1,
        max_steps=TAU2_MAX_STEPS,
        max_errors=TAU2_MAX_ERRORS,
        seed=TAU2_SEED,
        log_level="ERROR",
    )


def load_airline_tasks(limit: int | None = None) -> list[Any]:
    """The airline task set in the task file's own order (0004 §1)."""
    from tau2.run import get_tasks

    tasks = get_tasks(task_set_name=DOMAIN)
    return tasks if limit is None else tasks[:limit]


def run_airline_task(
    *,
    agent_model: str,
    user_sim_model: str,
    ledger: BudgetLedger,
    task_id: str = "0",
    phase: str = "P0",
    out_path: Path | None = DEFAULT_E2E_PATH,
) -> dict:
    """Run one airline task live and return `{task_id, reward, ...}`. Writes `out_path`."""
    ensure_tau2_data_dir()
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.run import run_single_task

    task = next(t for t in load_airline_tasks() if t.id == task_id)
    config = text_run_config(agent_model, user_sim_model)
    started = time.monotonic()
    with route_tau2_llm(ledger=ledger, phase=phase):
        simulation = run_single_task(
            config, task, seed=trial_seed(), evaluation_type=EvaluationType.ALL
        )
    reward = simulation.reward_info.reward if simulation.reward_info else None
    result = {
        "task_id": task_id,
        "domain": DOMAIN,
        "agent": agent_model,
        "user_sim": user_sim_model,
        "reward": reward,
        "termination_reason": str(getattr(simulation.termination_reason, "value", "")),
        "n_messages": len(simulation.messages or []),
        "seed": trial_seed(),
        "wall_time_s": time.monotonic() - started,
        "live": True,
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(redact(json.dumps(result, indent=2, sort_keys=True)))
    return result
