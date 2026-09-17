"""Static vocabulary the generator draws from: domains, tau2-like tool names,
task titles, and text snippets. Every list here is a plain tuple so draws
from it (via `rng.integers(len(...))`) are reproducible across platforms.
"""

from __future__ import annotations

from agent_bisect.server.schemas_runs import FaultType

DOMAINS: tuple[str, ...] = ("airline", "retail")

AIRLINE_TOOLS: tuple[str, ...] = (
    "get_reservation_details",
    "search_direct_flight",
    "search_onestop_flight",
    "book_reservation",
    "cancel_reservation",
    "update_reservation_baggages",
    "update_reservation_flights",
    "update_reservation_passengers",
    "get_user_details",
    "list_all_airports",
    "send_certificate",
    "transfer_to_human_agents",
)

RETAIL_TOOLS: tuple[str, ...] = (
    "get_order_details",
    "get_product_details",
    "get_user_details",
    "find_user_id_by_email",
    "list_all_product_types",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "cancel_pending_order",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
    "transfer_to_human_agents",
)

AIRLINE_TASKS: tuple[str, ...] = (
    "refund_after_cancellation",
    "baggage_fee_dispute",
    "reservation_lookup_by_name",
    "reschedule_flight_change",
    "seat_upgrade_request",
    "duplicate_booking_cleanup",
    "certificate_reissue",
    "passenger_name_correction",
)

RETAIL_TASKS: tuple[str, ...] = (
    "order_dup_investigation",
    "return_window_dispute",
    "address_change_pending",
    "payment_method_swap",
    "exchange_wrong_size",
    "cancel_before_ship",
    "product_availability_check",
    "refund_partial_items",
)

FAULT_TYPES: tuple[FaultType, ...] = ("wrong_value", "missing_field", "stale_record", "tool_error")

DIFF_PATHS_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "airline": (
        "reservation.status",
        "reservation.passengers[0].seat",
        "reservation.flights[0].origin",
        "reservation.baggages",
        "user.membership",
    ),
    "retail": (
        "order.status",
        "order.items[0].quantity",
        "order.address.zip",
        "order.payment.method",
        "user.email",
    ),
}

# A short unicode phrase mixed into one edge-case run's messages, to exercise
# non-ASCII rendering in the step inspector (never a stand-in for real PII).
UNICODE_PHRASE = "座席のアップグレードをお願いします — thanks! 🎫"

# Named edge-case run ids the UI must render correctly. Shared between
# `dataset.py` (which builds their `RunPlan`s) and `serialize.py` (which
# special-cases their deep payloads on demand).
LONG_PAYLOAD_RUN_ID = "run-edge-long-payload"
LONG_PAYLOAD_STEP = 4
LONG_PAYLOAD_LENGTH = 6000
UNICODE_RUN_ID = "run-edge-unicode"
UNICODE_STEP = 1
BRIEF_RUN_ID = "brief-12-step"
BRIEF_FAULT_STEP = 7
BRIEF_ORIGINAL_RESULT = "NM1VX1"
BRIEF_REPLACED_RESULT = "ZFA04Y"
