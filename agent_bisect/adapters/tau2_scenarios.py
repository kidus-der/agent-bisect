"""Scripted end-to-end scenarios for the offline record/replay tests.

Each one drives the **real** tau2 orchestrator, environment and evaluator
over a real domain; only the model is scripted
(`adapters.tau2_fake_llm.ScriptedLLM`). Between them they cover what the
P1/P2 offline suite must exercise: read-only tools, WRITE tools that move
the DB hash, a tool that errors, and an agent turn carrying more than one
tool call.

Shared by `tests/test_tau2_record.py`, `tests/test_tau2_replay.py` and the
gate scripts, so the scenarios and what "a recorded run" means have one
source of truth -- the same arrangement `adapters/tau2_snapshot_check.py`
uses for its scripted tool sequences, and the tool arguments here are the
ones verified there against the vendored airline and retail data.

Turn order, for reading the scripts: the orchestrator opens with a canned
agent greeting that costs no LLM call, so the **user** speaks first. The
user is asked for a turn only when the agent sends text; while the agent
makes tool calls it is asked again straight after the environment
answers. A user turn containing `###STOP###` ends the run
(`tau2.user.user_simulator.UserSimulator.is_stop`).
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_bisect.adapters.tau2_fake_llm import ScriptedToolCall, ScriptedTurn

AGENT_MODEL = "fake/agent-model"
USER_MODEL = "fake/user-model"
STOP = "###STOP###"


@dataclass(frozen=True)
class Scenario:
    """One scripted run: which task, and what each participant says."""

    name: str
    domain: str
    task_id: str
    agent: tuple[ScriptedTurn, ...]
    user: tuple[ScriptedTurn, ...]

    @property
    def scripts(self) -> dict[str, list[ScriptedTurn]]:
        return {AGENT_MODEL: list(self.agent), USER_MODEL: list(self.user)}


def _call(call_id: str, name: str, **arguments: object) -> ScriptedToolCall:
    return ScriptedToolCall(id=call_id, name=name, arguments=arguments)


#: Reads only, plus the two awkward shapes: one agent turn carrying two
#: tool calls, and a lookup of a reservation id that does not exist, which
#: the environment answers with `error=True`.
AIRLINE_READS = Scenario(
    name="airline-reads",
    domain="airline",
    task_id="0",
    agent=(
        ScriptedTurn(
            tool_calls=(
                _call("c1", "list_all_airports"),
                _call("c2", "get_reservation_details", reservation_id="NOPE11"),
            )
        ),
        ScriptedTurn(tool_calls=(_call("c3", "get_user_details", user_id="mia_li_3668"),)),
        ScriptedTurn(content="I could not find reservation NOPE11. Anything else?"),
        ScriptedTurn(content="Thanks for contacting us."),
    ),
    user=(
        ScriptedTurn(content="Hi, I would like to check a reservation."),
        ScriptedTurn(content="No, that is all."),
        ScriptedTurn(content=STOP),
    ),
)

#: WRITE tools: booking moves the DB hash, so does changing the baggage
#: count, so does cancelling. Every step of this one has a different
#: `state_hash` from the last.
AIRLINE_WRITES = Scenario(
    name="airline-writes",
    domain="airline",
    task_id="1",
    agent=(
        ScriptedTurn(tool_calls=(_call("c1", "get_user_details", user_id="mia_li_3668"),)),
        ScriptedTurn(
            tool_calls=(
                _call(
                    "c2",
                    "book_reservation",
                    user_id="mia_li_3668",
                    origin="PHL",
                    destination="LGA",
                    flight_type="one_way",
                    cabin="economy",
                    flights=[{"flight_number": "HAT001", "date": "2024-05-16"}],
                    passengers=[{"first_name": "Mia", "last_name": "Li", "dob": "1990-04-05"}],
                    payment_methods=[{"payment_id": "credit_card_4421486", "amount": 122}],
                    total_baggages=1,
                    nonfree_baggages=0,
                    insurance="no",
                ),
            )
        ),
        ScriptedTurn(
            tool_calls=(
                _call(
                    "c3",
                    "update_reservation_baggages",
                    reservation_id="HATHAT",
                    total_baggages=2,
                    nonfree_baggages=1,
                    payment_id="credit_card_4421486",
                ),
            )
        ),
        ScriptedTurn(tool_calls=(_call("c4", "cancel_reservation", reservation_id="HATHAT"),)),
        ScriptedTurn(content="Booked, amended and then cancelled, as you asked."),
    ),
    user=(
        ScriptedTurn(content="Book me PHL to LGA on 2024-05-16, then cancel it again."),
        ScriptedTurn(content=STOP),
    ),
)

#: The second domain, with its own WRITE tools, so nothing in the engine
#: can quietly depend on airline's data model.
RETAIL_WRITES = Scenario(
    name="retail-writes",
    domain="retail",
    task_id="0",
    agent=(
        ScriptedTurn(tool_calls=(_call("c1", "get_user_details", user_id="sofia_rossi_8776"),)),
        ScriptedTurn(
            tool_calls=(
                _call(
                    "c2",
                    "modify_user_address",
                    user_id="sofia_rossi_8776",
                    address1="1 New St",
                    address2="",
                    city="Austin",
                    state="TX",
                    country="USA",
                    zip="78784",
                ),
            )
        ),
        ScriptedTurn(
            tool_calls=(
                _call(
                    "c3",
                    "cancel_pending_order",
                    order_id="#W5918442",
                    reason="no longer needed",
                ),
            )
        ),
        ScriptedTurn(content="Address updated and the pending order is cancelled."),
    ),
    user=(
        ScriptedTurn(content="Please update my address and cancel my pending order."),
        ScriptedTurn(content=STOP),
    ),
)

#: Every scenario the offline suite runs. Airline first so a failure in
#: the commonest domain is the first thing reported.
SCENARIOS: tuple[Scenario, ...] = (AIRLINE_READS, AIRLINE_WRITES, RETAIL_WRITES)
