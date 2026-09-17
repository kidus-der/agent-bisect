"""The fork: `restore(k) → apply(intervention) → run_rest(seed) → Outcome`.

A fork is a new run (`run_id`) that shares a prefix with its parent
(`parent_run_id`, `fork_step`). What actually drives one is domain
specific, so this module holds only the shape: a `ForkSpec`, a
`ForkDriver` protocol, the three-call sequence, the derivation of the
forked `RunManifest`, and the two checks a full-run replay ends with.
The tau2 driver lives in `adapters/tau2_replay.py` — `core/` never imports
tau2 (nor `attribution`/`bench`/`gate`).

On the mechanism chosen in `docs/decisions/0010-replay-mechanism.md`,
`restore` and `apply` *arm* the engine (they say where the tape stops
being authoritative and what changes there) and `run_rest` does the
driving, re-running tau2's own orchestrator from step 0 with the prefix
served from the tape. The sequence is still the documented one, and a
driver that restored eagerly would satisfy the same protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_bisect.core.replay import DivergenceError, Intervention, TapeCursor
from agent_bisect.core.tape import Outcome, RunManifest

#: How the tool executions *before* the fork step are obtained.
#:
#: - `snapshot`: serve the recorded tool result and restore the world from
#:   the recorded snapshot — Bisect.
#: - `rerun_live`: execute the tools for real, restoring nothing — the
#:   CAR-style baseline of `docs/brief/summary.md` §8. On deterministic
#:   tau2 the two agree; in the flaky world they must not, which is the
#:   ablation that justifies snapshots at all.
PrefixMode = Literal["snapshot", "rerun_live"]


class ForkSpec(BaseModel):
    """Which run to fork, where, and how to obtain its prefix."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parent_run_id: str
    run_id: str
    fork_step: int = Field(ge=0)
    prefix_tools: PrefixMode = "snapshot"
    seed: int | None = None


@runtime_checkable
class ForkDriver(Protocol):
    """What `run_fork` needs from a domain to fork one run."""

    def restore(self, fork_step: int) -> None:
        """Put the world as it was entering `fork_step`."""
        ...

    def apply(self, intervention: Intervention) -> None:
        """Arrange for `intervention` to change exactly the fork step."""
        ...

    def run_rest(self, seed: int | None) -> Outcome:
        """Run from the fork step to the end, live, and return the outcome."""
        ...


def run_fork(driver: ForkDriver, spec: ForkSpec, intervention: Intervention) -> Outcome:
    """The three documented calls, in order."""
    driver.restore(spec.fork_step)
    driver.apply(intervention)
    return driver.run_rest(spec.seed)


def fork_manifest(
    parent: RunManifest,
    *,
    run_id: str,
    fork_step: int,
    created_at: datetime,
    seed: int | None = None,
) -> RunManifest:
    """A new manifest for a fork of `parent`, leaving `parent` untouched.

    Everything the parent pinned (domain, task, both models, params, tau2
    commit) carries over unchanged — a fork that re-pinned any of them
    would not be a counterfactual of the same run. `parent_run_id` is the
    *immediate* parent, so a fork of a fork records the chain one link at
    a time.
    """
    return RunManifest(
        run_id=run_id,
        domain=parent.domain,
        task_id=parent.task_id,
        agent_model=parent.agent_model,
        user_model=parent.user_model,
        params=dict(parent.params),
        seed=parent.seed if seed is None else seed,
        tau2_commit=parent.tau2_commit,
        created_at=created_at,
        parent_run_id=parent.run_id,
        fork_step=fork_step,
    )


def check_replay_complete(cursor: TapeCursor) -> None:
    """A full replay must consume the whole tape, not merely agree so far.

    A replay that stopped early (the agent said goodbye sooner, the user
    simulator terminated first) agrees with every step it *did* take and
    would otherwise pass silently.
    """
    if cursor.at_end:
        return
    raise DivergenceError(
        step_idx=cursor.position,
        actor="run",
        expected=f"{cursor.position + cursor.remaining} steps",
        got=f"{cursor.position} steps",
        diff=f"replay ended with {cursor.remaining} recorded steps unconsumed",
    )


def check_same_outcome(expected: Outcome | None, got: Outcome) -> None:
    """A replay that reproduces every step must reproduce the reward too."""
    if expected is None:
        raise DivergenceError(
            step_idx=-1,
            actor="run",
            expected="a recorded outcome",
            got=f"reward={got.reward}",
            diff="no recorded outcome to compare against",
        )
    if expected.reward != got.reward:
        raise DivergenceError(
            step_idx=-1,
            actor="run",
            expected=f"reward={expected.reward}",
            got=f"reward={got.reward}",
            diff=f"reward: {expected.reward} != {got.reward}",
        )
