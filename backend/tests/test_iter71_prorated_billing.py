"""Prorrateo del primer mes: un contrato que arranca el 22 no paga el mes entero.

Antes, los tres generadores (botón «⚡ Generate This Month's Invoice», «Generate
Monthly» y el cron del 25) armaban siempre el período del día 1 al último día e
ignoraban el inicio del contrato: un cliente que firmaba el 22 de octubre
recibía octubre completo. Ahora el período se recorta con las fechas del
contrato y hay que garantizar dos cosas: que lo prorrateado salga bien y que un
contrato viejo siga dando EXACTAMENTE lo mismo de siempre.
"""
import os
import sys
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta

import pytest
import requests

sys.path.insert(0, "/app/backend")

from finance import compute_invoice_period  # noqa: E402

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"


# ------------------------------------------------------------------ unitarias
def contrato(inicio: str, fin: str = "2030-12-31") -> dict:
    return {"start_date": inicio, "end_date": fin, "screens": [
        {"units": 2, "day_price": 8.5, "model": "MAV-30540S"}]}


class TestPeriodoCalculado:
    def test_arranca_el_22_de_octubre_son_10_dias(self):
        per = compute_invoice_period(contrato("2026-10-22"), 2026, 10)
        assert per["period_start"] == date(2026, 10, 22)
        assert per["period_end"] == date(2026, 10, 31)
        assert per["days"] == 10
        assert per["prorated"] is True
        assert per["billing_month"] == "2026-10"

    def test_arranca_el_dia_1_es_el_mes_completo(self):
        per = compute_invoice_period(contrato("2026-10-01"), 2026, 10)
        assert (per["days"], per["prorated"]) == (31, False)
        assert per["period_start"] == date(2026, 10, 1)
        assert per["period_end"] == date(2026, 10, 31)

    def test_un_contrato_viejo_da_el_mes_completo_igual_que_siempre(self):
        """La regresión que no se puede romper: lo que ya funcionaba."""
        for anio, mes in ((2026, 1), (2026, 4), (2026, 10), (2026, 12)):
            per = compute_invoice_period(contrato("2024-03-15"), anio, mes)
            assert per["days"] == monthrange(anio, mes)[1]
            assert per["prorated"] is False
            assert per["period_start"] == date(anio, mes, 1)

    def test_febrero_de_28_y_de_29(self):
        assert compute_invoice_period(contrato("2026-01-01"), 2026, 2)["days"] == 28
        assert compute_invoice_period(contrato("2024-01-01"), 2024, 2)["days"] == 29
        # Y prorrateado dentro de un febrero bisiesto.
        per = compute_invoice_period(contrato("2024-02-20"), 2024, 2)
        assert (per["days"], per["period_end"]) == (10, date(2024, 2, 29))

    def test_el_mes_anterior_al_inicio_no_se_factura(self):
        assert compute_invoice_period(contrato("2026-10-22"), 2026, 9) is None
        assert compute_invoice_period(contrato("2026-10-22"), 2026, 8) is None

    def test_el_ultimo_mes_se_corta_el_dia_que_termina_el_contrato(self):
        per = compute_invoice_period(contrato("2025-01-01", "2026-10-15"), 2026, 10)
        assert (per["days"], per["prorated"]) == (15, True)
        assert per["period_end"] == date(2026, 10, 15)
        assert compute_invoice_period(contrato("2025-01-01", "2026-10-15"), 2026, 11) is None

    def test_un_contrato_de_un_solo_dia(self):
        per = compute_invoice_period(contrato("2026-10-22", "2026-10-22"), 2026, 10)
        assert per["days"] == 1

    def test_empieza_y_termina_dentro_del_mismo_mes(self):
        per = compute_invoice_period(contrato("2026-10-10", "2026-10-20"), 2026, 10)
        assert (per["days"], per["period_start"], per["period_end"]) == (
            11, date(2026, 10, 10), date(2026, 10, 20))


# ------------------------------------------------------------- de punta a punta
@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture
def cliente_con_contrato(headers, mongo_db):
    """Cliente y contrato de prueba; al final se borra todo lo que se creó."""
    creados = {"clients": [], "contracts": []}

    def crear(start_date: str, end_date: str = "2030-12-31",
              units: int = 2, day_price: float = 8.5):
        nombre = f"TEST prorrateo {uuid.uuid4().hex[:6]}"
        cl = requests.post(f"{FIN}/clients", headers=headers, timeout=30, json={
            "business_name": nombre, "representative": "Prueba",
            "email": f"{uuid.uuid4().hex[:8]}@example.com", "phone": "6145550000",
            "address_line1": "1 Test St", "city": "Columbus", "state": "OH",
            "zip": "43215", "country": "USA"}).json()
        ct = {
            "id": str(uuid.uuid4()), "contract_number": f"TEST-{uuid.uuid4().hex[:5]}",
            "client_id": cl["id"], "start_date": start_date, "end_date": end_date,
            "status": "active", "screens": [
                {"units": units, "day_price": day_price, "model": "MAV-30540S",
                 "install_location": "Test"}],
            "created_at": datetime.utcnow().isoformat(),
        }
        mongo_db.fin_contracts.insert_one(dict(ct))
        creados["clients"].append(cl["id"])
        creados["contracts"].append(ct["id"])
        return cl, ct

    yield crear

    for cid in creados["contracts"]:
        mongo_db.fin_invoices.delete_many({"contract_id": cid})
        mongo_db.fin_contracts.delete_many({"id": cid})
    for cid in creados["clients"]:
        mongo_db.fin_deposits.delete_many({"client_id": cid})
        mongo_db.fin_clients.delete_many({"id": cid})


class TestFacturaDeUnClic:
    def test_el_primer_mes_sale_prorrateado(self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        if hoy.day == 1:
            pytest.skip("El día 1 el prorrateo coincide con el mes completo")
        cl, ct = cliente_con_contrato(hoy.isoformat())
        dias_esperados = monthrange(hoy.year, hoy.month)[1] - hoy.day + 1

        r = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice",
                          headers=headers, json={}, timeout=30)
        assert r.status_code == 200, r.text
        inv = r.json()["invoice"]
        assert inv["period_start"] == hoy.isoformat()
        assert inv["items"][0]["days"] == dias_esperados
        assert inv["total"] == round(2 * 8.5 * dias_esperados, 2)
        assert inv["prorated"] is True
        assert inv["billing_month"] == f"{hoy.year}-{hoy.month:02d}"
        assert inv["issue_date"] == hoy.isoformat()
        assert inv["due_date"] == hoy.isoformat(), "la parte del mes en curso se cobra ya"

    def test_un_contrato_que_venia_de_antes_cobra_el_mes_completo(
            self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato("2024-01-01")
        inv = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                            json={}, timeout=30).json()["invoice"]
        dias_mes = monthrange(hoy.year, hoy.month)[1]
        assert inv["items"][0]["days"] == dias_mes
        assert inv["total"] == round(2 * 8.5 * dias_mes, 2)
        assert inv["prorated"] is False
        assert inv["period_start"] == date(hoy.year, hoy.month, 1).isoformat()
        assert inv["issue_date"] == date(hoy.year, hoy.month, 1).isoformat(), \
            "lo que ya funcionaba no cambia: se emite y vence el día 1"
        assert inv["due_date"] == date(hoy.year, hoy.month, 1).isoformat()

    def test_repetir_el_boton_no_duplica(self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        uno = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                            json={}, timeout=30).json()
        dos = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                            json={}, timeout=30).json()
        assert dos["duplicate"] is True
        assert dos["invoice"]["id"] == uno["invoice"]["id"]
        assert requests.get(f"{FIN}/invoices?client_id={cl['id']}", headers=headers,
                            timeout=30).json().__len__() == 1

    def test_tambien_el_mes_siguiente_crea_dos_facturas_separadas(
            self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        r = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                          json={"include_next_month": True}, timeout=30).json()
        assert len(r["invoices"]) == 2
        actual, prox = r["invoices"]
        mes_prox = (date(hoy.year, hoy.month, 1) + timedelta(days=31)).replace(day=1)
        assert prox["billing_month"] == f"{mes_prox.year}-{mes_prox.month:02d}"
        assert prox["id"] != actual["id"]
        assert prox["invoice_number"] != actual["invoice_number"]
        assert prox["items"][0]["days"] == monthrange(mes_prox.year, mes_prox.month)[1]
        assert prox["prorated"] is False
        assert prox["issue_date"] == hoy.isoformat(), "se emite hoy"
        assert prox["due_date"] == mes_prox.isoformat(), "vence el día 1 del mes siguiente"

    def test_pedir_el_mes_siguiente_dos_veces_no_duplica(
            self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                      json={"include_next_month": True}, timeout=30)
        r = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                          json={"include_next_month": True}, timeout=30).json()
        assert len(r["invoices"]) == 2
        facturas = requests.get(f"{FIN}/invoices?client_id={cl['id']}", headers=headers,
                                timeout=30).json()
        assert len(facturas) == 2, "siguen siendo dos, no cuatro"

    def test_un_contrato_que_empieza_el_mes_que_viene_no_factura_este_mes(
            self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        prox = (date(hoy.year, hoy.month, 1) + timedelta(days=31)).replace(day=1)
        cl, ct = cliente_con_contrato(prox.isoformat())
        r = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                          json={}, timeout=30)
        assert r.status_code == 400
        assert "vigente" in r.json()["detail"]


class TestResumenPrevio:
    def test_muestra_los_dias_y_el_monto_antes_de_crear(self, headers,
                                                        cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        p = requests.get(f"{FIN}/contracts/{ct['id']}/invoice-preview", headers=headers,
                         timeout=30).json()
        dias = monthrange(hoy.year, hoy.month)[1] - hoy.day + 1
        assert p["current"]["days"] == dias
        assert p["current"]["total"] == round(2 * 8.5 * dias, 2)
        assert p["current"]["days_in_month"] == monthrange(hoy.year, hoy.month)[1]
        assert p["current"]["already_exists"] is False
        assert p["next"]["prorated"] is False
        # No crea nada: es sólo una vista previa.
        assert requests.get(f"{FIN}/invoices?client_id={cl['id']}", headers=headers,
                            timeout=30).json() == []

    def test_avisa_cuando_la_factura_del_mes_ya_existe(self, headers,
                                                       cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        inv = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                            json={}, timeout=30).json()["invoice"]
        p = requests.get(f"{FIN}/contracts/{ct['id']}/invoice-preview", headers=headers,
                         timeout=30).json()
        assert p["current"]["already_exists"] is True
        assert p["current"]["existing_invoice_number"] == inv["invoice_number"]

    def test_pide_sesion(self, headers, cliente_con_contrato):
        cl, ct = cliente_con_contrato("2026-10-22")
        assert requests.get(f"{FIN}/contracts/{ct['id']}/invoice-preview",
                            timeout=30).status_code in (401, 403)


class TestGeneradorMensualYCron:
    def test_el_generador_mensual_prorratea_el_primer_mes(self, headers,
                                                          cliente_con_contrato):
        hoy = datetime.utcnow().date()
        if hoy.day == 1:
            pytest.skip("El día 1 el prorrateo coincide con el mes completo")
        cl, ct = cliente_con_contrato(hoy.isoformat())
        r = requests.post(f"{FIN}/invoices/generate-monthly",
                          headers=headers, timeout=60,
                          params={"period_year": hoy.year, "period_month": hoy.month})
        assert r.status_code == 200, r.text
        mias = [i for i in r.json()["invoices"] if i["contract_id"] == ct["id"]]
        assert len(mias) == 1
        dias = monthrange(hoy.year, hoy.month)[1] - hoy.day + 1
        assert mias[0]["items"][0]["days"] == dias
        assert mias[0]["billing_month"] == f"{hoy.year}-{hoy.month:02d}"
        # Y correrlo de nuevo no crea otra.
        r2 = requests.post(f"{FIN}/invoices/generate-monthly", headers=headers, timeout=60,
                           params={"period_year": hoy.year, "period_month": hoy.month})
        assert [i for i in r2.json()["invoices"] if i["contract_id"] == ct["id"]] == []

    def test_no_factura_meses_anteriores_al_inicio(self, headers, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        anterior = (date(hoy.year, hoy.month, 1) - timedelta(days=1))
        r = requests.post(f"{FIN}/invoices/generate-monthly", headers=headers, timeout=60,
                          params={"period_year": anterior.year,
                                  "period_month": anterior.month})
        assert [i for i in r.json()["invoices"] if i["contract_id"] == ct["id"]] == []

    def test_la_factura_vieja_sin_billing_month_tampoco_se_duplica(
            self, headers, cliente_con_contrato, mongo_db):
        """Las facturas que ya están en la base no tienen `billing_month`: la
        deduplicación sigue mirando también el período del día 1."""
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato("2024-01-01")
        mongo_db.fin_invoices.insert_one({
            "id": str(uuid.uuid4()), "invoice_number": "OLD-TEST",
            "contract_id": ct["id"], "client_id": cl["id"],
            "period_start": date(hoy.year, hoy.month, 1).isoformat(),
            "period_end": date(hoy.year, hoy.month,
                               monthrange(hoy.year, hoy.month)[1]).isoformat(),
            "issue_date": hoy.isoformat(), "due_date": hoy.isoformat(),
            "items": [], "subtotal": 100.0, "tax": 0.0, "total": 100.0,
            "amount_paid": 0.0, "balance": 100.0, "status": "pending",
            "created_at": datetime.utcnow().isoformat()})
        r = requests.post(f"{FIN}/contracts/{ct['id']}/quick-invoice", headers=headers,
                          json={}, timeout=30).json()
        assert r["duplicate"] is True
        assert r["invoice"]["invoice_number"] == "OLD-TEST"


class TestCronDelDia25:
    """El cron usa `_generate_monthly_invoices`, el tercer generador."""

    def correr(self, year, month, client_id):
        import asyncio

        from motor.motor_asyncio import AsyncIOMotorClient

        import finance_scheduler as fs
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return asyncio.run(fs._generate_monthly_invoices(
                cli[os.environ["DB_NAME"]], year, month, client_id=client_id))
        finally:
            cli.close()

    def test_prorratea_el_primer_mes_y_no_duplica(self, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        if hoy.day == 1:
            pytest.skip("El día 1 el prorrateo coincide con el mes completo")
        cl, ct = cliente_con_contrato(hoy.isoformat())
        creadas = self.correr(hoy.year, hoy.month, cl["id"])
        assert len(creadas) == 1
        dias = monthrange(hoy.year, hoy.month)[1] - hoy.day + 1
        assert creadas[0]["items"][0]["days"] == dias
        assert creadas[0]["prorated"] is True
        assert creadas[0]["due_date"] == hoy.isoformat()
        assert self.correr(hoy.year, hoy.month, cl["id"]) == [], "no repite"

    def test_un_contrato_viejo_sigue_dando_el_mes_completo(self, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato("2024-01-01")
        creadas = self.correr(hoy.year, hoy.month, cl["id"])
        assert len(creadas) == 1
        assert creadas[0]["items"][0]["days"] == monthrange(hoy.year, hoy.month)[1]
        assert creadas[0]["period_start"] == date(hoy.year, hoy.month, 1).isoformat()
        assert creadas[0]["due_date"] == date(hoy.year, hoy.month, 1).isoformat(), \
            "facturación anticipada: vence el día 1, como siempre"

    def test_no_crea_nada_para_un_mes_anterior_al_contrato(self, cliente_con_contrato):
        hoy = datetime.utcnow().date()
        cl, ct = cliente_con_contrato(hoy.isoformat())
        anterior = date(hoy.year, hoy.month, 1) - timedelta(days=1)
        assert self.correr(anterior.year, anterior.month, cl["id"]) == []
