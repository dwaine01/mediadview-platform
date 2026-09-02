# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Reports HTTP routes (Fase 5 · Sprint 1 · Etapa C4).

Endpoints (all require `reports:read`, exports require `reports:export`):

  Dashboard
    GET  /api/admin/reports/dashboard
    GET  /api/admin/reports/revenue/by-screen
    GET  /api/admin/reports/revenue/by-city
    GET  /api/admin/reports/revenue/by-client
    GET  /api/admin/reports/revenue/timeseries
    GET  /api/admin/reports/occupancy
    GET  /api/admin/reports/sla

  BI-ready flat listings
    GET  /api/admin/reports/bi/orders
    GET  /api/admin/reports/bi/invoices
    GET  /api/admin/reports/bi/refunds
    GET  /api/admin/reports/bi/ledger

  Exports (format ∈ csv | xlsx | pdf, report ∈ orders | invoices | refunds | ledger | dashboard | occupancy)
    GET  /api/admin/reports/export/{report}.{format}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from permissions import require_permission
from reports_exports import (
    CT_CSV,
    CT_PDF,
    CT_XLSX,
    to_csv,
    to_pdf,
    to_xlsx,
)
from reports_service import (
    Filters,
    executive_dashboard,
    flat_invoices,
    flat_ledger,
    flat_orders,
    flat_refunds,
    revenue_by_city,
    revenue_by_client,
    revenue_by_screen,
    revenue_timeseries,
    screen_occupancy,
    sla_metrics,
)

log = logging.getLogger("reports_routes")


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try ISO format
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(400, f"invalid date: {s!r} (use YYYY-MM-DD)")


def _filters_from_query(
    date_from:      Optional[str] = None,
    date_to:        Optional[str] = None,
    screen_id:      Optional[str] = None,
    guest_email:    Optional[str] = None,
    city:           Optional[str] = None,
    country:        Optional[str] = None,
    currency:       Optional[str] = None,
    order_status:   Optional[str] = None,
    invoice_status: Optional[str] = None,
    refund_status:  Optional[str] = None,
    provider:       Optional[str] = None,
) -> Filters:
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    # If a date is provided as a bare day, expand to full day
    if dt and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        dt = dt + timedelta(hours=23, minutes=59, seconds=59)
    return Filters(
        date_from=df, date_to=dt,
        screen_id=screen_id, guest_email=(guest_email or None),
        city=city, country=country, currency=currency,
        order_status=order_status, invoice_status=invoice_status,
        refund_status=refund_status, provider=provider,
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def build_reports_router(db: AsyncIOMotorDatabase) -> APIRouter:
    router = APIRouter(prefix="/api/admin/reports", tags=["admin_reports"])
    read_dep   = require_permission("reports:read")
    export_dep = require_permission("reports:export")

    # ═══════════════════════════════════════════════════════════════
    # Dashboard
    # ═══════════════════════════════════════════════════════════════
    @router.get("/dashboard")
    async def dashboard(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency:  Optional[str] = None, screen_id: Optional[str] = None,
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                currency=currency, screen_id=screen_id)
        return await executive_dashboard(db, f)

    @router.get("/revenue/by-screen")
    async def rev_by_screen(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency:  Optional[str] = None, city: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=500),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                currency=currency, city=city)
        rows = await revenue_by_screen(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/revenue/by-city")
    async def rev_by_city(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency:  Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=500),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to, currency=currency)
        rows = await revenue_by_city(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/revenue/by-client")
    async def rev_by_client(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency:  Optional[str] = None, guest_email: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=500),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                currency=currency, guest_email=guest_email)
        rows = await revenue_by_client(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/revenue/timeseries")
    async def rev_timeseries(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency:  Optional[str] = None,
        granularity: str = Query(default="day", pattern="^(day|week|month|year)$"),
        _u=Depends(read_dep),
    ):
        # Default range: last 30 days if not provided
        f = _filters_from_query(date_from=date_from, date_to=date_to, currency=currency)
        if not f.date_from and not f.date_to:
            f.date_to = datetime.now(timezone.utc)
            f.date_from = f.date_to - timedelta(days=30)
        rows = await revenue_timeseries(db, f, granularity=granularity)
        return {"items": rows, "granularity": granularity, "count": len(rows)}

    @router.get("/occupancy")
    async def occupancy(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        screen_id: Optional[str] = None,
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                screen_id=screen_id)
        rows = await screen_occupancy(db, f)
        return {"items": rows, "count": len(rows)}

    @router.get("/sla")
    async def sla(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        screen_id: Optional[str] = None,
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                screen_id=screen_id)
        return await sla_metrics(db, f)

    # ═══════════════════════════════════════════════════════════════
    # BI-ready flat endpoints (for Power BI / Tableau / Looker)
    # ═══════════════════════════════════════════════════════════════
    @router.get("/bi/orders")
    async def bi_orders(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        screen_id: Optional[str] = None, guest_email: Optional[str] = None,
        currency: Optional[str] = None, order_status: Optional[str] = None,
        limit: int = Query(default=5000, ge=1, le=50000),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                screen_id=screen_id, guest_email=guest_email,
                                currency=currency, order_status=order_status)
        rows = await flat_orders(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/bi/invoices")
    async def bi_invoices(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency: Optional[str] = None, invoice_status: Optional[str] = None,
        limit: int = Query(default=5000, ge=1, le=50000),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                currency=currency, invoice_status=invoice_status)
        rows = await flat_invoices(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/bi/refunds")
    async def bi_refunds(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency: Optional[str] = None, refund_status: Optional[str] = None,
        limit: int = Query(default=5000, ge=1, le=50000),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to,
                                currency=currency, refund_status=refund_status)
        rows = await flat_refunds(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/bi/ledger")
    async def bi_ledger(
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        currency: Optional[str] = None,
        limit: int = Query(default=10000, ge=1, le=100000),
        _u=Depends(read_dep),
    ):
        f = _filters_from_query(date_from=date_from, date_to=date_to, currency=currency)
        rows = await flat_ledger(db, f, limit=limit)
        return {"items": rows, "count": len(rows)}

    # ═══════════════════════════════════════════════════════════════
    # Exports
    # ═══════════════════════════════════════════════════════════════
    async def _resolve_report(report: str, f: Filters) -> tuple[list[dict], list[str], str]:
        """Return (rows, columns, human_title) for a given report id."""
        if report == "orders":
            rows = await flat_orders(db, f, limit=50000)
            cols = ["order_id","order_number","status","created_at","paid_at",
                    "approved_at","screen_id","screen_name","guest_email","guest_name",
                    "guest_phone","amount_cents","refunded_cents","currency","hours",
                    "hourly_rate_cents","payment_provider","payment_intent_id","invoice_number"]
            return rows, cols, "Orders"
        if report == "invoices":
            rows = await flat_invoices(db, f, limit=50000)
            cols = ["invoice_number","status","order_id","order_number","customer_email",
                    "customer_name","screen_name","issued_at","paid_at","subtotal_cents",
                    "tax_cents","total_cents","currency","payment_provider","payment_intent_id"]
            return rows, cols, "Invoices"
        if report == "refunds":
            rows = await flat_refunds(db, f, limit=50000)
            cols = ["refund_number","order_id","invoice_id","status","amount_cents",
                    "currency","refund_type","policy","requires_dual_approval",
                    "requested_by","requested_at","approved_by","approved_at","executed_at",
                    "credit_note_number","provider","provider_ref","reason","failure_message"]
            return rows, cols, "Refunds"
        if report == "ledger":
            rows = await flat_ledger(db, f, limit=100000)
            cols = ["entry_number","ts","entry_type","direction","amount_cents","currency",
                    "order_id","invoice_id","refund_id","credit_note_id","payment_intent_id",
                    "provider","provider_ref","actor_kind","actor_email","reason"]
            return rows, cols, "Financial Ledger"
        if report == "occupancy":
            rows = await screen_occupancy(db, f)
            cols = ["screen_id","screen_name","city","currency","hours_sold",
                    "hours_available","occupancy_pct","orders_count","revenue_cents",
                    "avg_hourly_rate_cents","operating_hours_per_day","days_in_period"]
            return rows, cols, "Screen Occupancy"
        if report == "revenue_by_screen":
            rows = await revenue_by_screen(db, f, limit=500)
            cols = ["screen_id","screen_name","city","country","currency",
                    "revenue_cents","orders_count"]
            return rows, cols, "Revenue by Screen"
        if report == "revenue_by_city":
            rows = await revenue_by_city(db, f, limit=500)
            cols = ["city","country","currency","revenue_cents","orders_count"]
            return rows, cols, "Revenue by City"
        if report == "revenue_by_client":
            rows = await revenue_by_client(db, f, limit=500)
            cols = ["email","name","currency","revenue_cents","orders_count"]
            return rows, cols, "Revenue by Client"
        raise HTTPException(400, f"unknown report {report!r}")

    @router.get("/export/{report}.{fmt}")
    async def export_report(
        report: str, fmt: str,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        screen_id: Optional[str] = None, guest_email: Optional[str] = None,
        city: Optional[str] = None, currency: Optional[str] = None,
        order_status: Optional[str] = None, invoice_status: Optional[str] = None,
        refund_status: Optional[str] = None, provider: Optional[str] = None,
        _u=Depends(export_dep),
    ):
        f = _filters_from_query(
            date_from=date_from, date_to=date_to, screen_id=screen_id,
            guest_email=guest_email, city=city, currency=currency,
            order_status=order_status, invoice_status=invoice_status,
            refund_status=refund_status, provider=provider,
        )
        rows, cols, title = await _resolve_report(report, f)
        fname_base = f"mediadview-{report}-{_timestamp()}"

        if fmt == "csv":
            data = to_csv(rows, cols)
            return Response(content=data, media_type=CT_CSV, headers={
                "Content-Disposition": f'attachment; filename="{fname_base}.csv"'})
        if fmt == "xlsx":
            data = to_xlsx([{"name": title, "rows": rows, "columns": cols}])
            return Response(content=data, media_type=CT_XLSX, headers={
                "Content-Disposition": f'attachment; filename="{fname_base}.xlsx"'})
        if fmt == "pdf":
            subtitle_parts = []
            if f.date_from: subtitle_parts.append(f"From {f.date_from.strftime('%Y-%m-%d')}")
            if f.date_to:   subtitle_parts.append(f"To {f.date_to.strftime('%Y-%m-%d')}")
            if f.currency:  subtitle_parts.append(f"Currency {f.currency.upper()}")
            subtitle = " · ".join(subtitle_parts) or f"Generated {_timestamp()}"
            data = to_pdf(title=title, subtitle=subtitle,
                          sections=[{"heading": title, "rows": rows,
                                     "columns": cols, "column_titles": cols}])
            return Response(content=data, media_type=CT_PDF, headers={
                "Content-Disposition": f'inline; filename="{fname_base}.pdf"'})
        raise HTTPException(400, f"unknown format {fmt!r} (use csv|xlsx|pdf)")

    return router
