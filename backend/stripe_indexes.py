"""
MediAd View — Stripe-related MongoDB indexes (Fase 5 · Sprint 1 · Etapa A).

Idempotent. Called from server.startup(). Every index here corresponds
to a hard invariant of the Stripe blueprint (see docs/FASE5_STRIPE_ARCHITECTURE.md).

Rules for editing this file:
  · Adding a new index → OK.
  · Renaming/removing → OK only if the collection is empty in prod, or
    with an explicit migration script; NEVER edit silently.
  · Every unique index MUST have a `partialFilterExpression` if the field
    can be NULL, otherwise inserts will collide on the sentinel value.
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("stripe_indexes")


async def ensure_stripe_indexes(db: AsyncIOMotorDatabase) -> None:
    # ── orders (new, source-of-truth) ────────────────────────────────
    await db.orders.create_index("stripe_payment_intent_id",
                                 unique=True,
                                 partialFilterExpression={"stripe_payment_intent_id": {"$type": "string"}},
                                 name="ux_orders_pi")
    await db.orders.create_index("order_number", unique=True, sparse=True, name="ux_orders_number")
    await db.orders.create_index([("status", 1), ("created_at", -1)], name="ix_orders_status_created")
    await db.orders.create_index("guest_email", name="ix_orders_guest_email")
    await db.orders.create_index("customer_id", sparse=True, name="ix_orders_customer")
    await db.orders.create_index("stripe_customer_id", sparse=True, name="ix_orders_stripe_customer")

    # ── stripe_events (webhook dedup — MOST critical unique index) ──
    await db.stripe_events.create_index("event_id", unique=True, name="ux_stripe_events_event_id")
    await db.stripe_events.create_index([("type", 1), ("received_at", -1)], name="ix_stripe_events_type")
    # TTL: keep processed events for 90 days for audit + replay resilience,
    # then let Mongo garbage-collect. Sprint 2 can bump this.
    await db.stripe_events.create_index("received_at", expireAfterSeconds=90 * 24 * 3600,
                                        name="ttl_stripe_events_90d")

    # ── slot_reservations (double-booking guard) ────────────────────
    await db.slot_reservations.create_index(
        [("screen_id", 1), ("day", 1), ("hour", 1)],
        unique=True,
        partialFilterExpression={"confirmed": True},
        name="ux_slot_reservations_confirmed")
    await db.slot_reservations.create_index("expires_at",
                                            expireAfterSeconds=0,
                                            name="ttl_slot_reservations")

    # ── refunds ─────────────────────────────────────────────────────
    await db.refunds.create_index("stripe_refund_id",
                                  unique=True,
                                  partialFilterExpression={"stripe_refund_id": {"$type": "string"}},
                                  name="ux_refunds_stripe")
    await db.refunds.create_index("order_id", name="ix_refunds_order")

    # ── payment_methods (references only, never PAN) ────────────────
    await db.payment_methods.create_index("stripe_payment_method_id",
                                          unique=True,
                                          partialFilterExpression={"stripe_payment_method_id": {"$type": "string"}},
                                          name="ux_pm_stripe")
    await db.payment_methods.create_index("customer_id", name="ix_pm_customer")

    # ── subscriptions (Sprint 2 will populate; index now to avoid schema churn) ──
    await db.subscriptions.create_index("stripe_subscription_id",
                                        unique=True,
                                        partialFilterExpression={"stripe_subscription_id": {"$type": "string"}},
                                        name="ux_sub_stripe")
    await db.subscriptions.create_index("customer_id", name="ix_sub_customer")

    # ── order_tokens (magic-link for guest checkout) ────────────────
    await db.order_tokens.create_index("jti", unique=True, name="ux_order_tokens_jti")
    await db.order_tokens.create_index("order_id", name="ix_order_tokens_order")
    await db.order_tokens.create_index("expires_at", expireAfterSeconds=0, name="ttl_order_tokens")

    # ── financial_audit (append-only ledger) ────────────────────────
    await db.financial_audit.create_index([("ts", -1)], name="ix_audit_ts")
    await db.financial_audit.create_index("entity_id", sparse=True, name="ix_audit_entity")
    await db.financial_audit.create_index("stripe_event_id", sparse=True, name="ix_audit_event")
    await db.financial_audit.create_index("action", name="ix_audit_action")

    # ── counters (invoice numbering, order numbering) ───────────────
    #   _id is naturally unique; no extra index needed. Keep for reference.

    # ── fin_invoices: idempotency on order_id ───────────────────────
    # Only enforced when a value is present (older invoices predate this rule).
    await db.fin_invoices.create_index("order_id",
                                       unique=True,
                                       partialFilterExpression={"order_id": {"$type": "string"}},
                                       name="ux_fin_invoices_order")
    await db.fin_invoices.create_index("stripe_invoice_id",
                                       unique=True,
                                       partialFilterExpression={"stripe_invoice_id": {"$type": "string"}},
                                       name="ux_fin_invoices_stripe")

    log.info("✓ Stripe/finance indexes ensured (orders, stripe_events, slot_reservations, "
             "refunds, payment_methods, subscriptions, order_tokens, financial_audit)")
