# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Reports & Analytics service (Fase 5 · Sprint 1 · Etapa C4).

Business goals (per user brief):
    · Executive dashboard readable by a manager in < 1 minute.
    · Financial KPIs (revenue today/month/year, invoices, refunds, credit,
      net income, avg ticket).
    · Business KPIs (revenue by screen/city/client, hours sold/available,
      occupancy %, avg hourly rate, SLA times).
    · Exportable to PDF / XLSX / CSV (see reports_exports).
    · BI-ready flat endpoints (see reports_routes /bi/*).
    · Real-time broadcast hook for admin dashboard subscribers.

Design principles:
    · The ledger (`fin_ledger`) is the SOURCE OF TRUTH for revenue and
      refunds. Never sum `orders.amount_cents` for financial reporting.
    · Multi-currency safe: aggregations are grouped by currency and
      surfaced separately. There is NO auto-conversion at this stage —
      that's a Sprint 2 concern.
    · All queries accept a common Filters object so the same aggregate
      can be reused for the dashboard, a per-city drill-down, and an
      exported report.

Public API (all coroutines):
    · executive_dashboard(db, f)                → full KPI bundle
    · revenue_by_screen(db, f)                  → list
    · revenue_by_city(db, f)                    → list
    · revenue_by_client(db, f)                  → list
    · revenue_timeseries(db, f, granularity)    → list of {bucket, cents}
    · screen_occupancy(db, f)                   → list per screen
    · sla_metrics(db, f)                        → aggregate + per-order sample
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from financial_ledger import (
    BASE_CURRENCY,
    LEDGER_COLLECTION,
    SUPPORTED_CURRENCIES,
    EntryType,
    normalise_currency,
)
from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("reports")


# ═══════════════════════════════════════════════════════════════════
# Filters (single source of truth for query params)
# ═══════════════════════════════════════════════════════════════════
@dataclass
class Filters:
    date_from: Optional[datetime] = None
    date_to:   Optional[datetime] = None
    screen_id: Optional[str] = None
    guest_email: Optional[str] = None
    city:      Optional[str] = None
    country:   Optional[str] = None
    currency:  Optional[str] = None
    order_status:   Optional[str] = None
    invoice_status: Optional[str] = None
    refund_status:  Optional[str] = None
    provider:  Optional[str] = None

    def ledger_query(self) -> dict:
        q: dict = {}
        if self.date_from or self.date_to:
            r: dict = {}
            if self.date_from: r["$gte"] = self.date_from
            if self.date_to:   r["$lte"] = self.date_to
            q["ts"] = r
        if self.currency:  q["currency"] = self.currency.lower()
        if self.screen_id:
            # ledger doesn't have screen_id directly; use metadata or link via orders.
            # This is applied post-fetch in some cases; here we accept a
            # metadata.screen_id if present.
            q["metadata.screen_id"] = self.screen_id
        return q

    def orders_query(self) -> dict:
        q: dict = {}
        if self.date_from or self.date_to:
            r: dict = {}
            if self.date_from: r["$gte"] = self.date_from
            if self.date_to:   r["$lte"] = self.date_to
            q["created_at"] = r
        if self.screen_id:   q["screen_id"] = self.screen_id
        if self.guest_email: q["guest_email"] = self.guest_email.lower()
        if self.currency:    q["currency"] = self.currency.lower()
        if self.order_status: q["status"] = self.order_status
        if self.provider:    q["payment_provider"] = self.provider
        return q

    def invoices_query(self) -> dict:
        q: dict = {}
        if self.date_from or self.date_to:
            r: dict = {}
            if self.date_from: r["$gte"] = self.date_from
            if self.date_to:   r["$lte"] = self.date_to
            q["issued_at"] = r
        if self.currency:       q["currency"] = self.currency.lower()
        if self.invoice_status: q["status"] = self.invoice_status
        return q

    def refunds_query(self) -> dict:
        q: dict = {}
        if self.date_from or self.date_to:
            r: dict = {}
            if self.date_from: r["$gte"] = self.date_from
            if self.date_to:   r["$lte"] = self.date_to
            q["created_at"] = r
        if self.currency:      q["currency"] = self.currency.lower()
        if self.refund_status: q["status"] = self.refund_status
        return q


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _range_today() -> tuple[datetime, datetime]:
    now = _utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _range_month() -> tuple[datetime, datetime]:
    now = _utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _range_year() -> tuple[datetime, datetime]:
    now = _utcnow()
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


# ═══════════════════════════════════════════════════════════════════
# Helpers — money aggregation
# ═══════════════════════════════════════════════════════════════════
async def _sum_ledger(
    db: AsyncIOMotorDatabase, *,
    entry_types: list[str],
    date_from: Optional[datetime] = None,
    date_to:   Optional[datetime] = None,
    currency:  Optional[str] = None,
    extra_match: Optional[dict] = None,
) -> list[dict]:
    """Sum ledger entries grouped by currency."""
    match: dict = {"entry_type": {"$in": entry_types}}
    if date_from or date_to:
        r: dict = {}
        if date_from: r["$gte"] = date_from
        if date_to:   r["$lte"] = date_to
        match["ts"] = r
    if currency: match["currency"] = currency.lower()
    if extra_match: match.update(extra_match)
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$currency",
            "sum_cents": {"$sum": "$amount_cents"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    result = []
    async for row in db[LEDGER_COLLECTION].aggregate(pipeline):
        result.append({"currency": row["_id"], "sum_cents": row["sum_cents"], "count": row["count"]})
    return result


def _mono_amount(rows: list[dict], preferred: str = BASE_CURRENCY) -> int:
    """Return the amount in the preferred currency if present; else the
    first currency available; else 0. Used by dashboard cards that show
    ONE number (managers cannot read 5 currencies at once)."""
    for r in rows:
        if r["currency"] == preferred:
            return int(r["sum_cents"])
    if rows:
        return int(rows[0]["sum_cents"])
    return 0


# ═══════════════════════════════════════════════════════════════════
# Executive Dashboard — ONE call, ALL KPIs
# ═══════════════════════════════════════════════════════════════════
async def executive_dashboard(
    db: AsyncIOMotorDatabase, f: Optional[Filters] = None,
) -> dict:
    f = f or Filters()
    today_from, today_to = _range_today()
    month_from, _ = _range_month()
    year_from,  _ = _range_year()
    now = _utcnow()

    currency = (f.currency or BASE_CURRENCY).lower()

    # ── Revenue today / month / year (from ledger PAYMENT_CAPTURED) ──
    rev_today = await _sum_ledger(db,
        entry_types=[EntryType.PAYMENT_CAPTURED],
        date_from=today_from, date_to=today_to, currency=currency)
    rev_month = await _sum_ledger(db,
        entry_types=[EntryType.PAYMENT_CAPTURED],
        date_from=month_from, date_to=now, currency=currency)
    rev_year = await _sum_ledger(db,
        entry_types=[EntryType.PAYMENT_CAPTURED],
        date_from=year_from, date_to=now, currency=currency)
    rev_all_time = await _sum_ledger(db,
        entry_types=[EntryType.PAYMENT_CAPTURED], currency=currency)

    # ── Refunds today / month ───────────────────────────────────────
    refunds_today = await _sum_ledger(db,
        entry_types=[EntryType.REFUND_FULL, EntryType.REFUND_PARTIAL],
        date_from=today_from, date_to=today_to, currency=currency)
    refunds_month = await _sum_ledger(db,
        entry_types=[EntryType.REFUND_FULL, EntryType.REFUND_PARTIAL],
        date_from=month_from, date_to=now, currency=currency)
    refunds_year = await _sum_ledger(db,
        entry_types=[EntryType.REFUND_FULL, EntryType.REFUND_PARTIAL],
        date_from=year_from, date_to=now, currency=currency)

    # ── Credit notes emitted ────────────────────────────────────────
    credit_month = await _sum_ledger(db,
        entry_types=[EntryType.CREDIT_NOTE_ISSUED],
        date_from=month_from, date_to=now, currency=currency)
    credit_year = await _sum_ledger(db,
        entry_types=[EntryType.CREDIT_NOTE_ISSUED],
        date_from=year_from, date_to=now, currency=currency)

    # ── Invoices ────────────────────────────────────────────────────
    inv_pipeline = [
        {"$match": {"currency": currency}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "sum_cents": {"$sum": "$total_cents"},
        }},
    ]
    invoices_by_status = {}
    async for row in db.fin_invoices.aggregate(inv_pipeline):
        invoices_by_status[row["_id"]] = {"count": row["count"], "sum_cents": row["sum_cents"]}
    invoices_total_count = sum(v["count"] for v in invoices_by_status.values())

    # ── Ticket promedio (paid orders only, in currency) ─────────────
    avg_pipeline = [
        {"$match": {"currency": currency,
                    "paid_at": {"$exists": True, "$ne": None},
                    "status": {"$nin": ["cancelled", "rejected", "payment_failed"]}}},
        {"$group": {"_id": None,
                    "avg_cents": {"$avg": "$amount_cents"},
                    "count": {"$sum": 1}}},
    ]
    avg_ticket = 0
    orders_paid_count = 0
    async for row in db.orders.aggregate(avg_pipeline):
        avg_ticket = int(round(row["avg_cents"] or 0))
        orders_paid_count = row["count"]

    # ── Campaigns / pending approvals (orders + legacy campaigns) ───
    pending_orders = await db.orders.count_documents({"status": "pending_review"})
    active_orders  = await db.orders.count_documents({"status": {"$in": ["approved", "scheduled", "playing"]}})
    pending_campaigns = await db.campaigns.count_documents({"status": "pending_approval"})
    active_campaigns  = await db.campaigns.count_documents({"status": {"$in": ["active", "approved", "scheduled", "playing"]}})

    # ── Screens count + occupancy quick roll-up ─────────────────────
    screens_count = await db.screens.count_documents({})

    # ── Top screens (revenue) + top clients (all-time) ──────────────
    top_screens = await revenue_by_screen(db, f, limit=5)
    top_clients = await revenue_by_client(db, f, limit=5)

    # ── Ingresos netos = revenue - refunds ──────────────────────────
    net_month_cents = _mono_amount(rev_month, currency) - _mono_amount(refunds_month, currency)
    net_year_cents  = _mono_amount(rev_year,  currency) - _mono_amount(refunds_year,  currency)

    return {
        "generated_at": now,
        "currency": currency,
        "base_currency": BASE_CURRENCY,
        "supported_currencies": sorted(SUPPORTED_CURRENCIES),
        "kpis": {
            "revenue": {
                "today_cents":    _mono_amount(rev_today,   currency),
                "month_cents":    _mono_amount(rev_month,   currency),
                "year_cents":     _mono_amount(rev_year,    currency),
                "all_time_cents": _mono_amount(rev_all_time, currency),
                "by_currency":    rev_year,  # full breakdown
            },
            "refunds": {
                "today_cents": _mono_amount(refunds_today, currency),
                "month_cents": _mono_amount(refunds_month, currency),
                "year_cents":  _mono_amount(refunds_year,  currency),
                "today_count": sum(r["count"] for r in refunds_today),
                "month_count": sum(r["count"] for r in refunds_month),
            },
            "credit_notes": {
                "month_cents": _mono_amount(credit_month, currency),
                "year_cents":  _mono_amount(credit_year,  currency),
            },
            "net_income": {
                "month_cents": net_month_cents,
                "year_cents":  net_year_cents,
            },
            "invoices": {
                "total":   invoices_total_count,
                "issued":  invoices_by_status.get("issued", {"count": 0, "sum_cents": 0}),
                "paid":    invoices_by_status.get("paid", {"count": 0, "sum_cents": 0}),
                "void":    invoices_by_status.get("void", {"count": 0, "sum_cents": 0}),
                "credited": invoices_by_status.get("credited", {"count": 0, "sum_cents": 0}),
                "pending_cents": (
                    invoices_by_status.get("issued", {}).get("sum_cents", 0)
                ),
            },
            "orders": {
                "pending_review":  pending_orders,
                "active":          active_orders,
                "paid_count":      orders_paid_count,
                "avg_ticket_cents": avg_ticket,
            },
            "campaigns": {
                "pending_approval": pending_campaigns,
                "active":           active_campaigns,
            },
            "screens": {
                "count": screens_count,
            },
        },
        "top_screens": top_screens,
        "top_clients": top_clients,
    }


# ═══════════════════════════════════════════════════════════════════
# Revenue by screen / city / client
# ═══════════════════════════════════════════════════════════════════
async def revenue_by_screen(
    db: AsyncIOMotorDatabase, f: Filters, limit: int = 50,
) -> list[dict]:
    """Aggregate revenue by screen. Joins ledger PAYMENT_CAPTURED with
    orders → screens. Uses $lookup to keep the pipeline in Mongo."""
    match = f.ledger_query()
    match.pop("metadata.screen_id", None)  # we join through orders here
    match["entry_type"] = EntryType.PAYMENT_CAPTURED
    pipeline: list = [
        {"$match": match},
        {"$lookup": {
            "from": "orders", "localField": "order_id", "foreignField": "_id",
            "as": "order",
        }},
        {"$unwind": "$order"},
    ]
    if f.screen_id:
        pipeline.append({"$match": {"order.screen_id": f.screen_id}})
    pipeline += [
        {"$group": {
            "_id": {"screen_id": "$order.screen_id", "currency": "$currency"},
            "revenue_cents": {"$sum": "$amount_cents"},
            "orders_count": {"$sum": 1},
        }},
        {"$sort": {"revenue_cents": -1}},
        {"$limit": limit},
    ]
    rows = []
    async for r in db[LEDGER_COLLECTION].aggregate(pipeline):
        rows.append({
            "screen_id": r["_id"]["screen_id"],
            "currency":  r["_id"]["currency"],
            "revenue_cents": r["revenue_cents"],
            "orders_count":  r["orders_count"],
        })
    # Hydrate screen names + city
    screen_ids = list({r["screen_id"] for r in rows if r["screen_id"]})
    screen_map = {}
    if screen_ids:
        async for s in db.screens.find({"id": {"$in": screen_ids}}):
            screen_map[s["id"]] = s
    for r in rows:
        s = screen_map.get(r["screen_id"]) or {}
        r["screen_name"] = s.get("name") or "(unknown)"
        r["data_quality_issue"] = None if s else "screen_missing"   # D-03 flag
        r["city"] = (s.get("location") or {}).get("city")
        r["country"] = (s.get("location") or {}).get("country")
    return rows


async def revenue_by_city(
    db: AsyncIOMotorDatabase, f: Filters, limit: int = 50,
) -> list[dict]:
    by_screen = await revenue_by_screen(db, f, limit=1000)
    agg: dict = {}
    for row in by_screen:
        key = (row.get("city") or "(unknown)", row.get("country") or "", row["currency"])
        cur = agg.setdefault(key, {"city": key[0], "country": key[1], "currency": key[2],
                                   "revenue_cents": 0, "orders_count": 0})
        cur["revenue_cents"] += row["revenue_cents"]
        cur["orders_count"]  += row["orders_count"]
    ordered = sorted(agg.values(), key=lambda r: -r["revenue_cents"])[:limit]
    return ordered


async def revenue_by_client(
    db: AsyncIOMotorDatabase, f: Filters, limit: int = 50,
) -> list[dict]:
    match = f.ledger_query()
    match.pop("metadata.screen_id", None)
    match["entry_type"] = EntryType.PAYMENT_CAPTURED
    pipeline = [
        {"$match": match},
        {"$lookup": {"from": "orders", "localField": "order_id",
                     "foreignField": "_id", "as": "order"}},
        {"$unwind": "$order"},
    ]
    if f.guest_email:
        pipeline.append({"$match": {"order.guest_email": f.guest_email.lower()}})
    pipeline += [
        {"$group": {
            "_id": {"email": "$order.guest_email", "name": "$order.guest_name",
                    "currency": "$currency"},
            "revenue_cents": {"$sum": "$amount_cents"},
            "orders_count": {"$sum": 1},
        }},
        {"$sort": {"revenue_cents": -1}},
        {"$limit": limit},
    ]
    rows = []
    async for r in db[LEDGER_COLLECTION].aggregate(pipeline):
        rows.append({
            "email": r["_id"]["email"],
            "name":  r["_id"]["name"],
            "currency": r["_id"]["currency"],
            "revenue_cents": r["revenue_cents"],
            "orders_count":  r["orders_count"],
        })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Revenue timeseries
# ═══════════════════════════════════════════════════════════════════
async def revenue_timeseries(
    db: AsyncIOMotorDatabase, f: Filters, granularity: str = "day",
) -> list[dict]:
    fmt = {"day": "%Y-%m-%d", "week": "%G-W%V", "month": "%Y-%m", "year": "%Y"}.get(granularity, "%Y-%m-%d")
    match = f.ledger_query()
    match["entry_type"] = EntryType.PAYMENT_CAPTURED
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "bucket": {"$dateToString": {"format": fmt, "date": "$ts", "timezone": "UTC"}},
                "currency": "$currency",
            },
            "revenue_cents": {"$sum": "$amount_cents"},
            "orders_count":  {"$sum": 1},
        }},
        {"$sort": {"_id.bucket": 1}},
    ]
    rows = []
    async for r in db[LEDGER_COLLECTION].aggregate(pipeline):
        rows.append({
            "bucket": r["_id"]["bucket"],
            "currency": r["_id"]["currency"],
            "revenue_cents": r["revenue_cents"],
            "orders_count":  r["orders_count"],
        })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Occupancy — hours sold vs available
# ═══════════════════════════════════════════════════════════════════
async def screen_occupancy(
    db: AsyncIOMotorDatabase, f: Filters,
) -> list[dict]:
    """Sum booked hours per screen from `orders.hours` within the range.
    Available hours = (screen operating hours per day) × days in range.
    We DO NOT assume 24h — we use `screen.operating_hours_per_day` if
    present, else fall back to 14h/day (typical LED billboard).
    """
    q = f.orders_query()
    q["status"] = q.get("status", {"$nin": ["cancelled", "rejected", "payment_failed"]})
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": {"screen_id": "$screen_id", "currency": "$currency"},
            "hours_sold": {"$sum": "$hours"},
            "revenue_cents": {"$sum": "$amount_cents"},
            "orders_count": {"$sum": 1},
        }},
        {"$sort": {"hours_sold": -1}},
    ]
    rows = []
    async for r in db.orders.aggregate(pipeline):
        rows.append({
            "screen_id": r["_id"]["screen_id"],
            "currency":  r["_id"]["currency"],
            "hours_sold": int(r["hours_sold"] or 0),
            "revenue_cents": r["revenue_cents"],
            "orders_count":  r["orders_count"],
        })

    # Available hours: if a date range is given, use it; else default to
    # the last 30 days for a meaningful denominator.
    if f.date_from and f.date_to:
        days = max(1, (f.date_to - f.date_from).days) + 1
    else:
        days = 30

    screen_ids = [r["screen_id"] for r in rows if r["screen_id"]]
    screen_map = {}
    if screen_ids:
        async for s in db.screens.find({"id": {"$in": screen_ids}}):
            screen_map[s["id"]] = s

    for r in rows:
        s = screen_map.get(r["screen_id"]) or {}
        # D-02: transparent about default hours source
        configured_hpd = s.get("operating_hours_per_day")
        if configured_hpd is not None:
            hpd = int(configured_hpd)
            hpd_source = "configured"
        elif not s:
            hpd = 14
            hpd_source = "unknown_screen"       # screen record missing entirely (D-03)
        else:
            hpd = 14
            hpd_source = "default_14h"          # screen exists but no operating hours field
        available = hpd * days
        r["screen_name"] = s.get("name") or "(unknown)"
        r["data_quality_issue"] = None if s else "screen_missing"   # D-03 flag
        r["city"] = (s.get("location") or {}).get("city")
        r["operating_hours_per_day"] = hpd
        r["operating_hours_source"] = hpd_source
        r["days_in_period"] = days
        r["hours_available"] = available
        r["occupancy_pct"] = round((r["hours_sold"] / available) * 100, 2) if available else 0
        r["avg_hourly_rate_cents"] = int(r["revenue_cents"] / r["hours_sold"]) if r["hours_sold"] else 0
    return rows


# ═══════════════════════════════════════════════════════════════════
# SLA metrics — time-to-approve / publish / admin response
# ═══════════════════════════════════════════════════════════════════
def _hist_event_ts(order: dict, state: str) -> Optional[datetime]:
    """Return the timestamp when the order first moved TO `state`."""
    for h in order.get("status_history") or []:
        if h.get("to") == state and h.get("at"):
            return h["at"]
    return None


async def sla_metrics(
    db: AsyncIOMotorDatabase, f: Filters,
) -> dict:
    q = f.orders_query()
    q["paid_at"] = {"$exists": True, "$ne": None}
    time_to_approve_sec: list[float] = []
    time_to_publish_sec: list[float] = []
    admin_response_sec:  list[float] = []
    samples: list[dict] = []

    async for o in db.orders.find(q).limit(5000):
        paid_at = o.get("paid_at")
        approved_at = o.get("approved_at") or _hist_event_ts(o, "approved")
        scheduled_at = _hist_event_ts(o, "scheduled")
        playing_at   = _hist_event_ts(o, "playing")

        tta = tta_pub = tta_resp = None
        if paid_at and approved_at:
            tta = (approved_at - paid_at).total_seconds()
            if tta >= 0:
                time_to_approve_sec.append(tta)
                admin_response_sec.append(tta)
        publish_at = playing_at or scheduled_at
        if approved_at and publish_at:
            tta_pub = (publish_at - approved_at).total_seconds()
            if tta_pub >= 0:
                time_to_publish_sec.append(tta_pub)
        samples.append({
            "order_id": str(o["_id"]),
            "guest_email": o.get("guest_email"),
            "paid_at": paid_at,
            "approved_at": approved_at,
            "publish_at": publish_at,
            "time_to_approve_sec": tta,
            "time_to_publish_sec": tta_pub,
        })

    def stats(arr: list[float]) -> dict:
        if not arr:
            return {"count": 0, "avg_sec": None, "p50_sec": None, "p95_sec": None,
                    "min_sec": None, "max_sec": None, "insufficient_data": True}
        return {
            "count":   len(arr),
            "avg_sec": round(statistics.mean(arr), 2),
            "p50_sec": round(statistics.median(arr), 2),
            "p95_sec": round(sorted(arr)[max(0, int(len(arr) * 0.95) - 1)], 2),
            "min_sec": round(min(arr), 2),
            "max_sec": round(max(arr), 2),
            "insufficient_data": False,
        }
    return {
        "time_to_approve": stats(time_to_approve_sec),
        "time_to_publish": stats(time_to_publish_sec),
        "admin_response":  stats(admin_response_sec),
        "sample_size":     len(samples),
        "samples":         samples[:100],
    }


# ═══════════════════════════════════════════════════════════════════
# BI-ready flat listings
# ═══════════════════════════════════════════════════════════════════
async def flat_orders(db: AsyncIOMotorDatabase, f: Filters, limit: int = 5000) -> list[dict]:
    q = f.orders_query()
    rows = []
    async for o in db.orders.find(q).sort("created_at", -1).limit(limit):
        rows.append({
            "order_id": o["_id"],
            "order_number": o.get("order_number"),
            "status": o.get("status"),
            "created_at": o.get("created_at"),
            "paid_at": o.get("paid_at"),
            "approved_at": o.get("approved_at"),
            "screen_id": o.get("screen_id"),
            "screen_name": o.get("screen_name"),
            "guest_email": o.get("guest_email"),
            "guest_name":  o.get("guest_name"),
            "guest_phone": o.get("guest_phone"),
            "amount_cents": o.get("amount_cents"),
            "refunded_cents": o.get("refunded_cents", 0),
            "currency": o.get("currency"),
            "hours": o.get("hours"),
            "hourly_rate_cents": o.get("hourly_rate_cents"),
            "payment_provider": o.get("payment_provider"),
            "payment_intent_id": o.get("stripe_payment_intent_id"),
            "invoice_number": o.get("invoice_number"),
        })
    return rows


async def flat_invoices(db: AsyncIOMotorDatabase, f: Filters, limit: int = 5000) -> list[dict]:
    q = f.invoices_query()
    rows = []
    async for i in db.fin_invoices.find(q).sort("issued_at", -1).limit(limit):
        rows.append({
            "invoice_number": i.get("invoice_number") or str(i["_id"]),
            "status": i.get("status"),
            "order_id": i.get("order_id"),
            "order_number": i.get("order_number"),
            "customer_email": (i.get("customer") or {}).get("email"),
            "customer_name":  (i.get("customer") or {}).get("name"),
            "screen_name":   (i.get("screen") or {}).get("name"),
            "issued_at": i.get("issued_at"),
            "paid_at":   i.get("paid_at"),
            "subtotal_cents": i.get("subtotal_cents"),
            "tax_cents": i.get("tax_cents"),
            "total_cents": i.get("total_cents"),
            "currency": i.get("currency"),
            "payment_provider": i.get("payment_provider"),
            "payment_intent_id": i.get("payment_intent_id"),
        })
    return rows


async def flat_refunds(db: AsyncIOMotorDatabase, f: Filters, limit: int = 5000) -> list[dict]:
    q = f.refunds_query()
    rows = []
    async for r in db.refunds.find(q).sort("created_at", -1).limit(limit):
        rows.append({
            "refund_number": r.get("refund_number") or str(r["_id"]),
            "order_id": r.get("order_id"),
            "invoice_id": r.get("invoice_id"),
            "status": r.get("status"),
            "amount_cents": r.get("amount_cents"),
            "currency": r.get("currency"),
            "refund_type": r.get("refund_type"),
            "policy": r.get("policy"),
            "requires_dual_approval": r.get("requires_dual_approval"),
            "requested_by": r.get("requested_by"),
            "requested_at": r.get("requested_at"),
            "approved_by": r.get("approved_by"),
            "approved_at": r.get("approved_at"),
            "executed_at": r.get("executed_at"),
            "credit_note_number": r.get("credit_note_number"),
            "provider": r.get("provider"),
            "provider_ref": r.get("provider_ref"),
            "reason": r.get("reason"),
            "failure_message": r.get("failure_message"),
        })
    return rows


async def flat_ledger(db: AsyncIOMotorDatabase, f: Filters, limit: int = 10000) -> list[dict]:
    q = f.ledger_query()
    rows = []
    async for e in db[LEDGER_COLLECTION].find(q).sort("entry_number", -1).limit(limit):
        rows.append({
            "entry_number": e.get("entry_number"),
            "ts": e.get("ts"),
            "entry_type": e.get("entry_type"),
            "direction": e.get("direction"),
            "amount_cents": e.get("amount_cents"),
            "currency": e.get("currency"),
            "order_id": e.get("order_id"),
            "invoice_id": e.get("invoice_id"),
            "refund_id": e.get("refund_id"),
            "credit_note_id": e.get("credit_note_id"),
            "payment_intent_id": e.get("payment_intent_id"),
            "provider": e.get("provider"),
            "provider_ref": e.get("provider_ref"),
            "actor_kind": e.get("actor_kind"),
            "actor_email": e.get("actor_email"),
            "reason": e.get("reason"),
        })
    return rows
