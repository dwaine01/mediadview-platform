# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Credit Notes service (Fase 5 · Sprint 1 · Etapa C3).

Every refund automatically emits a Credit Note (nota de crédito) with
its own immutable numbering `CN-YYYY-000001`. The credit note is a
first-class financial document, linked to:
    · the order
    · the original invoice
    · the refund
    · the ledger entry
    · the payment_intent / provider reference

The PDF is regenerable without changing the CN number or its financial
content — same idempotency guarantee as invoices.

Public API:
    · issue_credit_note_for_refund(db, refund_id, actor)  → dict
    · regenerate_credit_note_pdf(db, cn_id, actor)        → bytes
    · render_credit_note_pdf(cn) → bytes                  (pure)
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from financial_audit import audit
from financial_ledger import (
    DIR_DEBIT,
    EntryType,
    append_entry,
    next_credit_note_number,
    normalise_currency,
)
from motor.motor_asyncio import AsyncIOMotorDatabase
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

log = logging.getLogger("credit_notes")

CN_COLLECTION = "fin_credit_notes"

CN_ISSUED = "issued"
CN_VOIDED = "voided"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def issue_credit_note_for_refund(
    db: AsyncIOMotorDatabase,
    *,
    refund_id: str,
    actor_email: str,
    actor_user_id: Optional[str] = None,
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
) -> dict:
    """Emit a credit note for a SUCCEEDED refund. IDEMPOTENT — repeat
    calls return the existing credit note (unique index on refund_id).
    """
    existing = await db[CN_COLLECTION].find_one({"refund_id": refund_id})
    if existing:
        return existing

    refund = await db.refunds.find_one({"_id": refund_id})
    if not refund:
        raise ValueError(f"refund {refund_id!r} not found")
    if refund.get("status") not in ("succeeded", "executing"):
        # We only emit for successful refunds.
        raise ValueError(
            f"cannot issue credit note for refund in state {refund.get('status')!r}"
        )

    order = await db.orders.find_one({"_id": refund["order_id"]})
    invoice = None
    if refund.get("invoice_id"):
        invoice = await db.fin_invoices.find_one({"_id": refund["invoice_id"]})

    number = await next_credit_note_number(db)
    now = _utcnow()
    currency = normalise_currency(refund.get("currency"))

    amount = int(refund["amount_cents"])
    tax_breakdown = refund.get("tax_breakdown") or []
    tax_total = int(sum(int(t.get("amount_cents", 0)) for t in tax_breakdown))
    subtotal = amount - tax_total

    cn = {
        "_id": number,
        "id": number,
        "number": number,
        "status": CN_ISSUED,
        "order_id": refund["order_id"],
        "order_number": (order or {}).get("order_number"),
        "invoice_id": refund.get("invoice_id"),
        "invoice_number": (invoice or {}).get("number"),
        "refund_id": refund_id,
        "refund_number": refund.get("number"),
        "payment_intent_id": refund.get("payment_intent_id"),
        "provider": refund.get("provider"),
        "provider_ref": refund.get("provider_ref"),
        "customer": (invoice or {}).get("customer") or {
            "email": (order or {}).get("guest_email"),
            "name":  (order or {}).get("guest_name"),
            "phone": (order or {}).get("guest_phone"),
        },
        "screen": (invoice or {}).get("screen") or {
            "id": (order or {}).get("screen_id"),
            "name": (order or {}).get("screen_name"),
        },
        "lines": [{
            "description": (
                f"Refund of {refund.get('refund_type','partial')} amount — "
                f"{refund.get('policy','manual')} — {(refund.get('reason') or '')[:120]}"
            ),
            "quantity": 1,
            "unit": "refund",
            "unit_price_cents": amount,
            "total_cents": amount,
        }],
        "subtotal_cents": subtotal,
        "tax_cents": tax_total,
        "tax_breakdown": tax_breakdown,
        "total_cents": amount,
        "currency": currency,
        "base_currency": "usd",
        "exchange_rate": refund.get("exchange_rate"),
        # DR preparation — empty for now.
        "rnc": (order or {}).get("rnc"),
        "ncf": None,
        "issued_at": now,
        "issued_by": actor_email,
        "reason": refund.get("reason"),
        "ledger_entry_id": None,
        "pdf_generated_at": None,
        "pdf_hash_sha256": None,
        "pdf_bytes_size": None,
        "created_at": now,
        "updated_at": now,
    }
    await db[CN_COLLECTION].insert_one(cn)

    # Ledger: CREDIT_NOTE_ISSUED entry (idempotent by CN number)
    idem_key = f"credit_note_issued:{number}"
    entry = await append_entry(
        db,
        entry_type=EntryType.CREDIT_NOTE_ISSUED,
        direction=DIR_DEBIT,
        amount_cents=amount,
        currency=currency,
        order_id=refund["order_id"],
        invoice_id=refund.get("invoice_id"),
        credit_note_id=number,
        refund_id=refund_id,
        payment_intent_id=refund.get("payment_intent_id"),
        provider=refund.get("provider") or "system",
        provider_ref=refund.get("provider_ref"),
        actor_kind="admin",
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        reason=f"Credit note {number} issued for refund {refund_id}",
        idempotency_key=idem_key,
        tax_breakdown=tax_breakdown,
        metadata={"refund_type": refund.get("refund_type"),
                  "policy": refund.get("policy")},
    )
    await db[CN_COLLECTION].update_one(
        {"_id": number},
        {"$set": {"ledger_entry_id": entry["_id"], "updated_at": _utcnow()}}
    )

    # Legacy audit trail (kept for backward compat with financial_audit reads)
    await audit(db,
                action="credit_note.issued",
                actor_kind="admin", actor_id=actor_email,
                entity_type="credit_note", entity_id=number,
                amount_cents=amount, currency=currency,
                reason=refund.get("reason"),
                metadata={"refund_id": refund_id,
                          "order_id": refund["order_id"],
                          "invoice_id": refund.get("invoice_id")})

    # Backlink on the refund and the invoice.
    await db.refunds.update_one(
        {"_id": refund_id},
        {"$set": {"credit_note_number": number,
                  "credit_note_id": number,
                  "updated_at": _utcnow()}})
    if invoice:
        await db.fin_invoices.update_one(
            {"_id": invoice["_id"]},
            {"$push": {"credit_notes": number},
             "$set": {"updated_at": _utcnow()}})

    log.info("credit note %s issued for refund %s (%s cents %s)",
             number, refund_id, amount, currency)
    return cn


async def regenerate_credit_note_pdf(
    db: AsyncIOMotorDatabase, *, cn_id: str, actor_email: str,
) -> bytes:
    """Regenerate PDF for a credit note without touching its financial
    content or number. Bumps pdf_generated_at + stores sha256."""
    cn = await db[CN_COLLECTION].find_one({"_id": cn_id})
    if not cn:
        raise ValueError("credit note not found")
    pdf_bytes = render_credit_note_pdf(cn)
    h = hashlib.sha256(pdf_bytes).hexdigest()
    await db[CN_COLLECTION].update_one(
        {"_id": cn_id},
        {"$set": {
            "pdf_generated_at": _utcnow(),
            "pdf_hash_sha256": h,
            "pdf_bytes_size": len(pdf_bytes),
            "updated_at": _utcnow(),
        }}
    )
    await audit(db, action="credit_note.pdf_regenerated",
                actor_kind="admin", actor_id=actor_email,
                entity_type="credit_note", entity_id=cn_id,
                metadata={"sha256": h, "size": len(pdf_bytes)})
    return pdf_bytes


# ─────────────────────────────────────────────────────────────────────
# PDF renderer
# ─────────────────────────────────────────────────────────────────────
def render_credit_note_pdf(cn: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    W, H = LETTER

    # Header — red band to distinguish from invoices
    c.setFillColorRGB(0.55, 0.10, 0.14)
    c.rect(0, H - 3*cm, W, 3*cm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(2*cm, H - 1.7*cm, "MEDIAD VIEW")
    c.setFont("Helvetica", 9)
    c.drawString(2*cm, H - 2.3*cm, "Premium LED Advertising Platform")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(W - 2*cm, H - 1.7*cm, "CREDIT NOTE")
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 2*cm, H - 2.3*cm, cn.get("number", ""))

    y = H - 4.5*cm
    c.setFillColorRGB(0.15, 0.15, 0.2)

    # Customer + Meta
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2*cm, y, "CUSTOMER")
    c.drawString(W/2, y, "CREDIT NOTE DETAILS")
    y -= 0.5*cm
    c.setFont("Helvetica", 10)
    cu = cn.get("customer") or {}
    c.drawString(2*cm, y, cu.get("name") or "—")
    c.drawString(W/2, y, f"Number:   {cn['number']}"); y -= 0.5*cm
    c.drawString(2*cm, y, cu.get("email") or "")
    issued = cn.get("issued_at")
    c.drawString(W/2, y, f"Issued:   {issued.strftime('%Y-%m-%d') if issued else ''}"); y -= 0.5*cm
    c.drawString(2*cm, y, cu.get("phone") or "")
    if cn.get("invoice_number"):
        c.drawString(W/2, y, f"Invoice:  {cn.get('invoice_number')}")
    y -= 0.5*cm
    if cn.get("refund_number"):
        c.drawString(W/2, y, f"Refund:   {cn.get('refund_number')}")
        y -= 0.5*cm
    c.drawString(W/2, y, f"Status:   {cn.get('status','').upper()}")
    y -= 1.2*cm

    # Line items header
    c.setFillColorRGB(0.94, 0.94, 0.98)
    c.rect(2*cm, y, W - 4*cm, 0.7*cm, fill=1, stroke=0)
    c.setFillColorRGB(0.20, 0.20, 0.28)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2.2*cm, y + 0.22*cm, "DESCRIPTION")
    c.drawRightString(W - 8*cm, y + 0.22*cm, "QTY")
    c.drawRightString(W - 5*cm, y + 0.22*cm, "AMOUNT")
    c.drawRightString(W - 2.2*cm, y + 0.22*cm, "CREDIT")
    y -= 0.9*cm

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.15, 0.15, 0.2)
    for line in cn.get("lines", []):
        c.drawString(2.2*cm, y, str(line.get("description",""))[:60])
        c.drawRightString(W - 8*cm, y, f"{line.get('quantity',0)} {line.get('unit','')}")
        c.drawRightString(W - 5*cm, y, f"${line.get('unit_price_cents',0)/100:,.2f}")
        c.drawRightString(W - 2.2*cm, y, f"-${line.get('total_cents',0)/100:,.2f}")
        y -= 0.6*cm

    y -= 0.5*cm
    c.line(W - 8*cm, y, W - 2*cm, y)
    y -= 0.6*cm
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 5*cm, y, "Subtotal")
    c.drawRightString(W - 2.2*cm, y, f"-${cn.get('subtotal_cents',0)/100:,.2f}")
    y -= 0.5*cm
    if cn.get("tax_breakdown"):
        for t in cn["tax_breakdown"]:
            c.drawRightString(W - 5*cm, y, f"{t.get('name','Tax')} ({(t.get('rate') or 0)*100:.2f}%)")
            c.drawRightString(W - 2.2*cm, y, f"-${(t.get('amount_cents',0))/100:,.2f}")
            y -= 0.5*cm
    else:
        c.drawRightString(W - 5*cm, y, "Tax")
        c.drawRightString(W - 2.2*cm, y, f"-${cn.get('tax_cents',0)/100:,.2f}")
        y -= 0.5*cm
    y -= 0.2*cm
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.55, 0.10, 0.14)
    c.drawRightString(W - 5*cm, y, "TOTAL CREDIT")
    c.drawRightString(W - 2.2*cm, y,
                       f"-${cn.get('total_cents',0)/100:,.2f} {cn.get('currency','usd').upper()}")

    # Reason
    y -= 1.5*cm
    c.setFillColorRGB(0.40, 0.40, 0.48)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2*cm, y, "REASON")
    y -= 0.4*cm
    c.setFont("Helvetica", 9)
    reason = str(cn.get("reason") or "—")
    for i in range(0, len(reason), 90):
        c.drawString(2*cm, y, reason[i:i+90])
        y -= 0.35*cm

    # Payment info
    y -= 0.5*cm
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.40, 0.40, 0.48)
    c.drawString(2*cm, y, "REFUND REFERENCE")
    y -= 0.4*cm
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.15, 0.15, 0.2)
    c.drawString(2*cm, y, f"Provider:  {cn.get('provider','—')}")
    y -= 0.35*cm
    if cn.get("provider_ref"):
        c.drawString(2*cm, y, f"Reference: {cn['provider_ref']}")
        y -= 0.35*cm
    if cn.get("payment_intent_id"):
        c.drawString(2*cm, y, f"PaymentIntent: {cn['payment_intent_id']}")

    # Footer
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.55, 0.55, 0.6)
    c.drawCentredString(W/2, 1.2*cm,
        "This credit note is issued electronically by MediAd View. All amounts are shown in "
        f"{cn.get('currency','usd').upper()}. Original invoice: {cn.get('invoice_number') or '—'}.")

    c.showPage()
    c.save()
    return buf.getvalue()
