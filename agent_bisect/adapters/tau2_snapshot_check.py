"""Scripted, real tau2 tool-call sequences and the snapshot round-trip check
that exercises `Tau2Snapshotter` against them.

Both domains currently vendored (airline, retail) are deterministic in
their WRITE tools -- fixed seed data, no clock/random dependency (see
`tau2.domains.airline.tools.AirlineTools._get_new_reservation_id`/
`_get_datetime`) -- so re-applying the same call on a freshly-restored
state must reproduce the exact same post-call hash. That's the property
this module checks.

Shared by `tests/test_tau2_snapshot.py` (per-step assertions) and
`scripts/gates/p1_offline.py` (a single PASS/FAIL for the P1 gate), so the
scripted call data and what "reproduced" means have one source of truth.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_bisect.adapters.tau2_snapshot import Tau2Snapshotter

AIRLINE_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("get_user_details", {"user_id": "mia_li_3668"}),
    ("list_all_airports", {}),
    ("search_direct_flight", {"origin": "PHL", "destination": "LGA", "date": "2024-05-16"}),
    (
        "book_reservation",
        {
            "user_id": "mia_li_3668",
            "origin": "PHL",
            "destination": "LGA",
            "flight_type": "one_way",
            "cabin": "economy",
            "flights": [{"flight_number": "HAT001", "date": "2024-05-16"}],
            "passengers": [{"first_name": "Mia", "last_name": "Li", "dob": "1990-04-05"}],
            "payment_methods": [{"payment_id": "credit_card_4421486", "amount": 122}],
            "total_baggages": 1,
            "nonfree_baggages": 0,
            "insurance": "no",
        },
    ),
    ("get_reservation_details", {"reservation_id": "HATHAT"}),
    (
        "update_reservation_baggages",
        {
            "reservation_id": "HATHAT",
            "total_baggages": 2,
            "nonfree_baggages": 1,
            "payment_id": "credit_card_4421486",
        },
    ),
    (
        "update_reservation_passengers",
        {
            "reservation_id": "HATHAT",
            "passengers": [{"first_name": "Mia", "last_name": "Li", "dob": "1990-04-05"}],
        },
    ),
    (
        "update_reservation_flights",
        {
            "reservation_id": "HATHAT",
            "cabin": "economy",
            "flights": [{"flight_number": "HAT001", "date": "2024-05-16"}],
            "payment_id": "credit_card_4421486",
        },
    ),
    ("send_certificate", {"user_id": "mia_li_3668", "amount": 50}),
    ("cancel_reservation", {"reservation_id": "HATHAT"}),
    ("calculate", {"expression": "2 + 2"}),
    ("get_flight_status", {"flight_number": "HAT001", "date": "2024-05-16"}),
]

RETAIL_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("get_user_details", {"user_id": "sofia_rossi_8776"}),
    ("get_order_details", {"order_id": "#W5918442"}),
    ("get_product_details", {"product_id": "6858788497"}),
    ("get_item_details", {"item_id": "1725100896"}),
    ("get_item_details", {"item_id": "5312063289"}),
    ("list_all_product_types", {}),
    ("find_user_id_by_email", {"email": "sofia.rossi2645@example.com"}),
    ("find_user_id_by_name_zip", {"first_name": "Sofia", "last_name": "Rossi", "zip": "78784"}),
    (
        "modify_user_address",
        {
            "user_id": "sofia_rossi_8776",
            "address1": "1 New St",
            "address2": "",
            "city": "Austin",
            "state": "TX",
            "country": "USA",
            "zip": "78784",
        },
    ),
    (
        "modify_pending_order_address",
        {
            "order_id": "#W5918442",
            "address1": "1 New St",
            "address2": "",
            "city": "Austin",
            "state": "TX",
            "country": "USA",
            "zip": "78784",
        },
    ),
    ("calculate", {"expression": "3 * 4"}),
    ("cancel_pending_order", {"order_id": "#W5918442", "reason": "no longer needed"}),
]


@dataclass(frozen=True)
class StepCapture:
    """One scripted call plus what its snapshot round trip must reproduce."""

    tool_name: str
    kwargs: dict[str, Any]
    state_before: Any
    hash_before: str
    hash_after: str


def run_scripted_sequence(
    environment: Any, calls: list[tuple[str, dict[str, Any]]]
) -> list[StepCapture]:
    """Executes `calls` in order on `environment`, capturing a `StepCapture` per call."""
    snapshotter = Tau2Snapshotter(environment)
    steps = []
    for tool_name, kwargs in calls:
        state_before = snapshotter.capture()
        hash_before = snapshotter.state_hash()
        environment.make_tool_call(tool_name, requestor="assistant", **kwargs)
        hash_after = snapshotter.state_hash()
        steps.append(StepCapture(tool_name, kwargs, state_before, hash_before, hash_after))
    return steps


@dataclass(frozen=True)
class RoundTripResult:
    domain: str
    total_steps: int
    reproduced: int
    failures: tuple[str, ...]

    @property
    def all_reproduced(self) -> bool:
        return self.total_steps > 0 and self.reproduced == self.total_steps


def check_round_trip(
    domain: str,
    steps: list[StepCapture],
    fresh_environment_factory: Callable[[], Any],
) -> RoundTripResult:
    """For every step: restore `state_before` into a fresh environment and
    check its hash matches `hash_before`, then re-apply the call and check
    the result matches `hash_after`. Never raises -- failures are
    collected into the returned `RoundTripResult`.
    """
    reproduced = 0
    failures: list[str] = []
    for index, step in enumerate(steps):
        fresh_env = fresh_environment_factory()
        fresh_snapshotter = Tau2Snapshotter(fresh_env)

        fresh_snapshotter.restore(step.state_before)
        before_ok = fresh_snapshotter.state_hash() == step.hash_before

        fresh_env.make_tool_call(step.tool_name, requestor="assistant", **step.kwargs)
        after_ok = fresh_snapshotter.state_hash() == step.hash_after

        if before_ok and after_ok:
            reproduced += 1
        else:
            failures.append(
                f"step {index} ({step.tool_name}): before_ok={before_ok} after_ok={after_ok}"
            )
    return RoundTripResult(
        domain=domain, total_steps=len(steps), reproduced=reproduced, failures=tuple(failures)
    )
