"""
MediAd View — Order state machine (Fase 5 · Sprint 1 · Etapa B).

Blueprint §5. Every allowed transition lives here so no route can invent
its own state change and drift from the design.

Terminal states:  completed, cancelled, refunded, rejected
Refundable:       paid, approved, scheduled, playing, completed
Not refundable:   any state where Stripe never charged the card
"""
from __future__ import annotations

from typing import Optional

# ── Canonical set of states ────────────────────────────────────────────
STATE_DRAFT              = "draft"
STATE_AWAITING_PAYMENT   = "awaiting_payment"
STATE_PAYMENT_PROCESSING = "payment_processing"
STATE_PAID               = "paid"
STATE_PENDING_REVIEW     = "pending_review"
STATE_CHANGES_REQUESTED  = "changes_requested"
STATE_APPROVED           = "approved"
STATE_SCHEDULED          = "scheduled"
STATE_PLAYING            = "playing"
STATE_COMPLETED          = "completed"
STATE_PAYMENT_FAILED     = "payment_failed"
STATE_CANCELLED          = "cancelled"
STATE_REJECTED           = "rejected"
STATE_REFUND_PENDING     = "refund_pending"
STATE_REFUNDED           = "refunded"
STATE_DISPUTED           = "disputed"

TERMINAL_STATES = {STATE_COMPLETED, STATE_CANCELLED, STATE_REJECTED, STATE_REFUNDED}
REFUNDABLE_STATES = {STATE_PAID, STATE_APPROVED, STATE_SCHEDULED, STATE_PLAYING, STATE_COMPLETED}
PLAYER_VISIBLE_STATES = {STATE_SCHEDULED, STATE_PLAYING}


# ── Transition matrix ─────────────────────────────────────────────────
# Every allowed transition is:
#   (from_state, to_state, allowed_actor)
# actor:  "client" | "webhook" | "admin" | "system"
#
# Any transition NOT in this table is REJECTED.
_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    # Draft → payment
    (STATE_DRAFT, STATE_AWAITING_PAYMENT):        {"system"},
    (STATE_DRAFT, STATE_CANCELLED):               {"client", "admin", "system"},

    # Awaiting payment → processing (Stripe PaymentIntent created)
    (STATE_AWAITING_PAYMENT, STATE_PAYMENT_PROCESSING): {"system"},
    (STATE_AWAITING_PAYMENT, STATE_CANCELLED):          {"client", "admin", "system"},

    # Payment processing → success/failure (webhook ONLY)
    (STATE_PAYMENT_PROCESSING, STATE_PAID):             {"webhook"},
    (STATE_PAYMENT_PROCESSING, STATE_PAYMENT_FAILED):   {"webhook"},
    (STATE_PAYMENT_PROCESSING, STATE_CANCELLED):        {"webhook", "system"},

    # Paid → review workflow (only admin can approve/reject)
    (STATE_PAID, STATE_PENDING_REVIEW):                 {"system", "webhook"},
    (STATE_PENDING_REVIEW, STATE_APPROVED):             {"admin"},
    (STATE_PENDING_REVIEW, STATE_REJECTED):             {"admin"},
    (STATE_PENDING_REVIEW, STATE_CHANGES_REQUESTED):    {"admin"},
    (STATE_CHANGES_REQUESTED, STATE_PENDING_REVIEW):    {"client", "system"},

    # Approval → playback (system scheduler moves through these)
    (STATE_APPROVED, STATE_SCHEDULED):                  {"system"},
    (STATE_SCHEDULED, STATE_PLAYING):                   {"system"},
    (STATE_PLAYING, STATE_COMPLETED):                   {"system"},

    # Refund workflow
    (STATE_PAID, STATE_REFUND_PENDING):                 {"admin"},
    (STATE_APPROVED, STATE_REFUND_PENDING):             {"admin"},
    (STATE_SCHEDULED, STATE_REFUND_PENDING):            {"admin"},
    (STATE_PLAYING, STATE_REFUND_PENDING):              {"admin"},
    (STATE_COMPLETED, STATE_REFUND_PENDING):            {"admin"},
    (STATE_REFUND_PENDING, STATE_REFUNDED):             {"webhook"},
    (STATE_REFUND_PENDING, STATE_DISPUTED):             {"webhook"},

    # Chargeback path (webhook-driven)
    (STATE_PLAYING, STATE_DISPUTED):                    {"webhook"},
    (STATE_COMPLETED, STATE_DISPUTED):                  {"webhook"},
}


class InvalidTransition(Exception):
    """Raised when a caller tries to move an order to an illegal state."""


def assert_transition(*, from_state: str, to_state: str, actor: str) -> None:
    """Raise InvalidTransition unless (from → to) is allowed for actor.

    Idempotent no-op if from_state == to_state (webhook retries).
    """
    if from_state == to_state:
        return
    allowed = _TRANSITIONS.get((from_state, to_state))
    if not allowed:
        raise InvalidTransition(
            f"order state transition not allowed: {from_state!r} → {to_state!r}"
        )
    if actor not in allowed:
        raise InvalidTransition(
            f"actor {actor!r} cannot move order from {from_state!r} → {to_state!r} "
            f"(allowed: {sorted(allowed)})"
        )


def is_refundable(state: str) -> bool:
    return state in REFUNDABLE_STATES


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def refund_policy(state: str) -> dict:
    """Return the refund policy hints for a given order state.

    Business rules approved by stakeholder (user message, Sprint 1):
      · Before approve: 100% refund (no admin gate needed for pre-approved).
      · Approved but not playing: 100% refund, admin approval required.
      · Playing: partial refund proportional to unused percentage; admin approval.
      · Completed: no automatic refund; admin override only, must be logged.
    """
    if state == STATE_PAID or state == STATE_PENDING_REVIEW:
        return {"allowed": True, "auto_full": True, "requires_admin": False,
                "kind": "pre_approval"}
    if state == STATE_APPROVED:
        return {"allowed": True, "auto_full": True, "requires_admin": True,
                "kind": "pre_play"}
    if state == STATE_SCHEDULED:
        return {"allowed": True, "auto_full": True, "requires_admin": True,
                "kind": "pre_play"}
    if state == STATE_PLAYING:
        return {"allowed": True, "auto_full": False, "requires_admin": True,
                "kind": "partial_by_unused"}
    if state == STATE_COMPLETED:
        return {"allowed": True, "auto_full": False, "requires_admin": True,
                "kind": "manual_admin_override"}
    return {"allowed": False, "reason": f"state {state!r} is not refundable"}
