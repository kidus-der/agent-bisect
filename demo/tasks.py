"""The 8 demo scenarios: tau2's vendored "mock" domain tasks this suite runs.

Picked from `vendor/tau2-bench/data/tau2/domains/mock/tasks.json` for
`reward_basis` that never needs an LLM judge (DB / ACTION / ENV_ASSERTION,
or COMMUNICATE with no `communicate_info` to match, all resolved by
re-executing a reference trajectory or checking DB state -- see
`docs/decisions/0019-gate-rule.md`). Two mock tasks are excluded for the
opposite reason: `create_task_1_nl_eval` and `update_task_with_user_tools`
either need the NL-assertion judge or drive the user's own tools, neither of
which this offline suite exercises.

Each scenario names the one `demo.policy` rule that governs its agent's
behaviour (`demo/agent.py` dispatches on `family`, and applies exactly one
rule's slip decision per run). `docs/decisions/0019-gate-rule.md` explains
why `use_correct_task_id`'s four scenarios are the ones this suite's own
self-test (`scripts/gates/p7.py`) plants regressions on: it is the only
rule confirmable through a **tool**-step fault (`demo.faults`), which gives
Bisect a reliable, deterministic "truth" to confirm against -- the other
three rules are agent-decision steps, confirmed (when confirmable at all)
through `Resample`, exactly the limitation `docs/decisions
/0013-suspect-interventions.md` already documents for that intervention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: What tau2 calls this suite's scripted participants. Distinct from
#: `adapters.tau2_scenarios`'s `fake/*` names so a stray cross-import can
#: never serve one suite's script to the other's model.
AGENT_MODEL = "demo/agent-model"
USER_MODEL = "demo/user-model"

#: Which reactive script family a scenario's agent follows
#: (`demo/agent.py`'s `_SCRIPTS` dispatch table).
Family = Literal["create", "update_fixed", "update_lookup", "impossible"]

DOMAIN = "mock"


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """One demo scenario: a mock-domain task, a family, and its governing rule."""

    name: str
    task_id: str
    family: Family
    rule_id: str
    #: The line the PR-check comment quotes for "what changed" -- kept short
    #: and stable so a diff of this file reads as a diff of scenario intent.
    summary: str


SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        name="create_task",
        task_id="create_task_1",
        family="create",
        rule_id="use_stated_title",
        summary="create a task with the title the user asked for",
    ),
    ScenarioSpec(
        name="create_task_env_assertion",
        task_id="create_task_1_with_env_assertions",
        family="create",
        rule_id="use_stated_title",
        summary="create a task; graded by an env assertion on its status",
    ),
    ScenarioSpec(
        name="update_task_fixed_id",
        task_id="update_task_1",
        family="update_fixed",
        rule_id="set_completed_status",
        summary="mark a named task (task_1) completed",
    ),
    ScenarioSpec(
        name="update_task_from_history",
        task_id="update_task_with_message_history",
        family="update_lookup",
        rule_id="use_correct_task_id",
        summary="mark the task from the seeded conversation completed",
    ),
    ScenarioSpec(
        name="update_task_from_initialization_data",
        task_id="update_task_with_initialization_data",
        family="update_lookup",
        rule_id="use_correct_task_id",
        summary="mark the pre-seeded task completed",
    ),
    ScenarioSpec(
        name="update_task_from_initialization_actions",
        task_id="update_task_with_initialization_actions",
        family="update_lookup",
        rule_id="use_correct_task_id",
        summary="mark the env-action-created task completed",
    ),
    ScenarioSpec(
        name="update_task_history_env_assertion",
        task_id="update_task_with_history_and_env_assertions",
        family="update_lookup",
        rule_id="use_correct_task_id",
        summary="mark the seeded task completed; graded by an env assertion",
    ),
    ScenarioSpec(
        name="impossible_delete",
        task_id="impossible_task_1",
        family="impossible",
        rule_id="escalate_impossible_requests",
        summary="escalate a request no tool can satisfy",
    ),
)

_BY_NAME: dict[str, ScenarioSpec] = {scenario.name: scenario for scenario in SCENARIOS}


def scenario(name: str) -> ScenarioSpec:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise KeyError(f"no demo scenario named {name!r}; known: {sorted(_BY_NAME)}") from None


def run_id_for(scenario_name: str, run_index: int) -> str:
    """The stable id this suite records a scenario's `run_index`'th run under."""
    return f"demo-{scenario_name}-{run_index}"


def scenario_of_run_id(run_id: str) -> ScenarioSpec:
    """The scenario a run id (or a fork's run id, which prefixes it) belongs to.

    Fork ids are `f"{parent_run_id}-{arm}{step}-{digest}"`
    (`attribution.search.rerun_id`), and a fault-fork's id is caller-chosen
    but still built from the parent's -- both keep the original
    `demo-<name>-<index>` prefix, so a longest-prefix match over known
    scenario names resolves either one back to its scenario.
    """
    candidates = [spec for spec in SCENARIOS if run_id.startswith(f"demo-{spec.name}-")]
    if not candidates:
        raise KeyError(f"run id {run_id!r} does not belong to any demo scenario")
    return max(candidates, key=lambda spec: len(spec.name))
