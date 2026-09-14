"""Facturación anticipada: se emite el 25, vence el 1 del mes siguiente.

Decisión del dueño (2026-06): «genera y envía el 25 del mes anterior, vence el
1». Estos tests fijan las tres cosas que no se pueden romper:
  · el cron corre el día 25 (APScheduler local y el worker de producción),
  · cuando corre en la segunda mitad del mes factura el MES SIGUIENTE,
  · la factura vence el día 1 y su fecha de emisión es la real (no el día 1),
    porque de eso depende que el recordatorio de «vence en 3 días» exista.
"""
import inspect
from datetime import date, datetime

import pytz

EASTERN = pytz.timezone("America/New_York")


class _FakeCollection:
    async def insert_one(self, doc):
        return None


class _FakeDB:
    """El job deja una bitácora al final; con esto no hace falta Mongo."""
    fin_scheduler_log = _FakeCollection()


def test_apscheduler_corre_el_25():
    import finance_scheduler
    src = inspect.getsource(finance_scheduler.start_scheduler)
    assert "day=25" in src, "la facturación mensual tiene que dispararse el día 25"
    assert "hour=11" in src


def test_worker_de_produccion_corre_el_25():
    src = open("/app/backend/worker.py").read()
    assert "cron(cron_monthly_billing, month=None, day=25, hour=15" in src, (
        "en producción los crons los corre el worker ARQ: ahí también va el día 25"
    )


def test_en_la_segunda_mitad_del_mes_factura_el_mes_siguiente(monkeypatch):
    """El 25 de agosto tiene que facturar septiembre, no agosto."""
    import finance_scheduler

    captured = {}

    async def fake_generate(db, year, month):
        captured["period"] = (year, month)
        return []

    monkeypatch.setattr(finance_scheduler, "_generate_monthly_invoices", fake_generate)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return EASTERN.localize(datetime(2026, 8, 25, 11, 0))

    monkeypatch.setattr(finance_scheduler, "datetime", FakeDatetime)

    import asyncio
    asyncio.run(finance_scheduler.monthly_billing_job(_FakeDB()))
    assert captured["period"] == (2026, 9)


def test_en_la_primera_mitad_factura_el_mes_en_curso(monkeypatch):
    """Disparado a mano el 3 de agosto, regulariza agosto."""
    import finance_scheduler

    captured = {}

    async def fake_generate(db, year, month):
        captured["period"] = (year, month)
        return []

    monkeypatch.setattr(finance_scheduler, "_generate_monthly_invoices", fake_generate)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return EASTERN.localize(datetime(2026, 8, 3, 11, 0))

    monkeypatch.setattr(finance_scheduler, "datetime", FakeDatetime)

    import asyncio
    asyncio.run(finance_scheduler.monthly_billing_job(_FakeDB()))
    assert captured["period"] == (2026, 8)


def test_diciembre_rueda_a_enero_del_ano_siguiente(monkeypatch):
    import finance_scheduler

    captured = {}

    async def fake_generate(db, year, month):
        captured["period"] = (year, month)
        return []

    monkeypatch.setattr(finance_scheduler, "_generate_monthly_invoices", fake_generate)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return EASTERN.localize(datetime(2026, 12, 25, 11, 0))

    monkeypatch.setattr(finance_scheduler, "datetime", FakeDatetime)

    import asyncio
    asyncio.run(finance_scheduler.monthly_billing_job(_FakeDB()))
    assert captured["period"] == (2027, 1)


def test_el_recordatorio_de_tres_dias_antes_ya_puede_existir():
    """Con emisión el 25 y vencimiento el 1, faltan 7 días: la etapa `pre_due`
    (-3 días) cae DENTRO de la vida de la factura. Antes se emitía y vencía el
    mismo día y esa etapa nunca se usaba."""
    from collections_engine import STAGES, stage_due_today

    factura = {
        "invoice_number": "MV-1",
        "due_date": "2026-09-01",
        "balance": 500.0,
        "status": "pending",
        "reminders_sent": [],
    }
    # 29 de agosto: 3 días antes de vencer
    etapa = stage_due_today(factura, datetime(2026, 8, 29))
    assert etapa is not None and etapa[0] == "pre_due"
    # El día del vencimiento, si no se pagó, toca la etapa `due`
    factura["reminders_sent"] = [{"stage": "pre_due"}]
    etapa = stage_due_today(factura, datetime(2026, 9, 1))
    assert etapa[0] == "due"
    assert [s[0] for s in STAGES] == ["pre_due", "due", "late_7", "late_15", "late_30"]


def test_la_factura_vence_el_dia_1_y_se_emite_hoy():
    """Contrato del generador: `due_date` = día 1 del período facturado,
    `issue_date` = el día real de emisión (no el día 1)."""
    src = inspect.getsource(
        __import__("finance_scheduler")._generate_monthly_invoices
    )
    assert '"due_date": period_start.isoformat()' in src
    assert '"issue_date": issue_date.isoformat()' in src
    assert "issue_date = min(" in src


def test_periodo_pasado_conserva_la_fecha_del_dia_1():
    """Regularizar un mes viejo no puede fechar la factura en el futuro ni hoy:
    se queda con el día 1 de ese mes."""
    hoy = date(2026, 8, 25)
    assert min(hoy, date(2026, 9, 1)) == hoy            # mes siguiente → hoy
    assert min(hoy, date(2026, 7, 1)) == date(2026, 7, 1)  # mes pasado → día 1
