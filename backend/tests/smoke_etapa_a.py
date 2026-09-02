# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""Smoke test for Fase 5 Sprint 1 Etapa A. Run: python -m tests.smoke_etapa_a"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from financial_audit import audit, next_invoice_number
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Ensure the indexes we later assert on actually exist. In dev the
    # web-api startup handler creates them, but standalone smoke runs
    # (and CI ephemeral Mongo) never boot the server, so we call the
    # ensure_* helpers directly here. Idempotent.
    try:
        from stripe_indexes import ensure_stripe_indexes
        await ensure_stripe_indexes(db)
    except Exception as e:
        print(f"  warn: ensure_stripe_indexes failed: {e}")

    print("── invoice number generator ──")
    # Reset counter so numbers are predictable in the smoke run.
    await db.counters.delete_one({"_id": "invoice_number:2999"})
    n1 = await next_invoice_number(db, year=2999)
    n2 = await next_invoice_number(db, year=2999)
    n3 = await next_invoice_number(db, year=2999)
    assert n1 == "INV-2999-000001", n1
    assert n2 == "INV-2999-000002", n2
    assert n3 == "INV-2999-000003", n3
    print(" ", n1, n2, n3, "→ OK")

    print("── financial_audit (never-raises) ──")
    await audit(db, action="etapa_a.smoke", actor_kind="system",
                entity_type="test", entity_id="smoke-etapa-a",
                amount_cents=1099, currency="usd",
                metadata={"note": "sprint1 etapa A"})
    doc = await db.financial_audit.find_one({"entity_id": "smoke-etapa-a"})
    assert doc and doc["action"] == "etapa_a.smoke", doc
    print("  audit entry OK:", doc["_id"], doc["action"])

    print("── indexes present ──")
    for coll, expected in [
        ("orders", ["ux_orders_pi", "ux_orders_number", "ix_orders_status_created"]),
        ("stripe_events", ["ux_stripe_events_event_id", "ttl_stripe_events_90d"]),
        ("slot_reservations", ["ux_slot_reservations_slot", "ttl_slot_reservations"]),
        ("refunds", ["ux_refunds_stripe", "ix_refunds_order"]),
        ("payment_methods", ["ux_pm_stripe"]),
        ("subscriptions", ["ux_sub_stripe"]),
        ("order_tokens", ["ux_order_tokens_jti", "ttl_order_tokens"]),
        ("financial_audit", ["ix_audit_ts", "ix_audit_action"]),
        ("fin_invoices", ["ux_fin_invoices_order", "ux_fin_invoices_stripe"]),
    ]:
        got = await db[coll].index_information()
        missing = [name for name in expected if name not in got]
        assert not missing, f"{coll} missing indexes: {missing}"
        print(f"  {coll}: all expected indexes present")

    print("── stripe_events dedup constraint ──")
    await db.stripe_events.delete_many({"event_id": "evt_smoke_A"})
    await db.stripe_events.insert_one({"event_id": "evt_smoke_A", "type": "x"})
    try:
        await db.stripe_events.insert_one({"event_id": "evt_smoke_A", "type": "x"})
        raise AssertionError("duplicate event_id should have been rejected")
    except Exception as e:
        assert "duplicate" in str(e).lower() or "E11000" in str(e), e
        print("  duplicate event_id rejected → OK")
    await db.stripe_events.delete_many({"event_id": "evt_smoke_A"})

    print("── slot_reservations double-booking constraint ──")
    # Now: full unique index on (screen_id, day, hour) — applies to BOTH
    # pending AND confirmed docs. Two pending holds for same slot collide.
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    await db.slot_reservations.delete_many({"screen_id": "scr_smoke"})
    await db.slot_reservations.insert_one({
        "screen_id": "scr_smoke", "day": "2999-12-31", "hour": 15,
        "status": "pending", "expires_at": now + timedelta(minutes=10),
    })
    try:
        await db.slot_reservations.insert_one({
            "screen_id": "scr_smoke", "day": "2999-12-31", "hour": 15,
            "status": "pending", "expires_at": now + timedelta(minutes=10),
        })
        raise AssertionError("double-booking should have been rejected")
    except Exception as e:
        assert "duplicate" in str(e).lower() or "E11000" in str(e), e
        print("  pending double-booking rejected → OK")
    # Clean up
    await db.slot_reservations.delete_many({"screen_id": "scr_smoke"})
    await db.financial_audit.delete_many({"action": "etapa_a.smoke"})
    await db.counters.delete_one({"_id": "invoice_number:2999"})

    print("\n✅ Etapa A smoke test PASSED")

asyncio.run(main())
