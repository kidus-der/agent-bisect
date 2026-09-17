"""What a recorded tool call *really* answers: re-execute it on its own state.

This is the label-free fix behind `attribution.TruthfulToolResult`. Given
a recorded step, restore the world as it was **entering** that step into a
throwaway environment, execute the recorded call there, and return what
the tool said.

Two properties make it usable where no label exists:

- at a planted fault it equals the oracle, because the fault changed what
  the agent was *shown* and never the database, so the real call still
  answers the real thing;
- anywhere else on a deterministic domain it equals the recording, so
  applying it to an innocent step is a no-op and costs the treated arm
  nothing.

The environment is a fresh one of the run's own domain, never the
orchestrator's: executing on the live environment would advance the world
a second time and a write tool would apply twice. It is built once per
resolver and re-restored per call, so the cost is one DB rebuild rather
than one per step. Nothing here touches the network.

**One caveat on spelling, not on data.** A restored snapshot comes back
through the blob store, whose JSON is canonical, so its dictionaries are
key-sorted while the live database kept insertion order. A truthful
result is therefore equal to the recorded one as *data* and may differ as
*text*. tau2's own db hash sorts keys too (`utils.get_dict_hash`), so
nothing that is checked is affected; anything comparing tool results here
must parse them rather than compare strings.
"""

from __future__ import annotations

from typing import Any

from agent_bisect.adapters.tau2 import RunSpec, build_orchestrator
from agent_bisect.adapters.tau2_replay import VOLATILE_MESSAGE_FIELDS
from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import Step


class TruthUnavailableError(Exception):
    """This step cannot be re-executed, so no truthful result exists for it."""


class Tau2TruthResolver:
    """A `TruthProvider` over one recorded tau2 run's domain.

    Callable: `resolver(step)` returns the tool-result payload the step's
    call produces against the state it actually ran on.
    """

    def __init__(
        self,
        domain: str,
        task_id: str,
        store: BlobStore,
        *,
        agent_model: str = "unused/agent",
        user_model: str = "unused/user",
    ) -> None:
        self._domain = domain
        self._task_id = task_id
        self._store = store
        self._agent_model = agent_model
        self._user_model = user_model
        self._environment: Any | None = None

    def __call__(self, step: Step) -> dict[str, Any]:
        if step.actor != "tool" or not step.tool_name:
            raise TruthUnavailableError(
                f"step {step.step_idx} is a {step.actor} step; only a tool call can be "
                "re-executed"
            )
        environment = self._restored(step)
        message = environment.get_response(self._call_of(step))
        payload = message.model_dump(mode="json")
        return {
            key: value for key, value in payload.items() if key not in VOLATILE_MESSAGE_FIELDS
        }

    def _restored(self, step: Step) -> Any:
        """A throwaway environment holding the world as it entered `step`."""
        environment = self._environment
        if environment is None:
            environment = build_orchestrator(
                RunSpec(
                    domain=self._domain,
                    task_id=self._task_id,
                    agent_model=self._agent_model,
                    user_model=self._user_model,
                ),
                f"truth-{self._domain}-{self._task_id}",
            ).environment
            self._environment = environment
        snapshotter = Tau2Snapshotter(environment)
        snapshotter.restore(self._store.get_json(step.state_before))
        if step.state_hash_before and snapshotter.state_hash() != step.state_hash_before:
            raise TruthUnavailableError(
                f"restoring step {step.step_idx}'s entry state gave a different db hash; "
                "the recording and the domain disagree"
            )
        return environment

    def _call_of(self, step: Step) -> Any:
        from tau2.data_model.message import ToolCall

        return ToolCall(
            id=f"truth-{step.step_idx}",
            name=step.tool_name or "",
            arguments=dict(step.tool_args or {}),
            requestor="assistant",
        )
