"""Borrar y editar lo que se cargó por error.

Pedido del dueño: «tienen que crear la parte para poder eliminar contratos que
se generaron pero ya no se van a usar y facturas que se cancelaron; y si es
posible que se pueda editar el contrato desde la raíz».

Lo que se fija acá:
  · el contrato se puede editar completo (fechas, plazo, pantallas, cargos) y
    los totales se recalculan solos, conservando el número de contrato;
  · un contrato con pagos aplicados NO se puede borrar (sería tapar un cobro);
  · con facturas sin cobrar avisa y pide confirmación (`force=true`);
  · la factura anulada/errada se borra de verdad, pero nunca una con pagos.
"""
import os
import uuid
from datetime import date

import pytest
import requests

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


def _nuevo_cliente(headers):
    tag = uuid.uuid4().hex[:6]
    r = requests.post(f"{FIN}/clients", headers=headers, json={
        "business_name": f"Borrar Test {tag}", "representative": "Test",
        "email": f"borrar.{tag}@example.com", "phone": "614-555-0001",
        "address_line1": "1 Test St", "city": "Columbus", "state": "OH", "zip": "43205",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _nuevo_contrato(headers, client_id, day_price=8.5, units=1):
    r = requests.post(f"{FIN}/contracts", headers=headers, json={
        "client_id": client_id,
        "start_date": f"{date.today().year}-01-01",
        "term_months": 12,
        "screens": [{"model": "MAV-30540S", "units": units, "day_price": day_price,
                     "location": "Test", "description": "LED"}],
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return body["contract"] if "contract" in body else body


class TestEditarContratoDesdeLaRaiz:
    def test_cambiar_pantallas_y_plazo_recalcula_todo(self, headers):
        cl = _nuevo_cliente(headers)
        ct = _nuevo_contrato(headers, cl["id"], day_price=8.5, units=1)
        assert ct["monthly_total"] == pytest.approx(8.5 * 30)

        r = requests.put(f"{FIN}/contracts/{ct['id']}/full", headers=headers, json={
            "start_date": f"{date.today().year}-03-01",
            "term_months": 24,
            "screens": [
                {"model": "MAV-30540S", "units": 2, "day_price": 10.0, "location": "A"},
                {"model": "MAV-30540S", "units": 1, "day_price": 5.0, "location": "B"},
            ],
            "security_deposit_per_screen": 300,
        }, timeout=30)
        assert r.status_code == 200, r.text
        upd = r.json()["contract"]
        assert upd["contract_number"] == ct["contract_number"], "el número no cambia"
        assert upd["total_units"] == 3
        assert upd["monthly_total"] == pytest.approx(2 * 10.0 * 30 + 1 * 5.0 * 30)
        assert upd["security_deposit"] == pytest.approx(3 * 300)
        assert upd["end_date"] == f"{date.today().year + 2}-03-01", upd["end_date"]

    def test_el_recibo_de_deposito_pendiente_se_actualiza(self, headers):
        cl = _nuevo_cliente(headers)
        ct = _nuevo_contrato(headers, cl["id"])
        r = requests.put(f"{FIN}/contracts/{ct['id']}/full", headers=headers, json={
            "screens": [{"model": "MAV-30540S", "units": 4, "day_price": 8.5, "location": "A"}],
            "security_deposit_per_screen": 250,
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["deposit_updated"] is True
        deps = requests.get(f"{FIN}/deposits?client_id={cl['id']}", headers=headers,
                            timeout=30).json()
        assert deps and deps[0]["total"] == pytest.approx(4 * 250)

    def test_no_deja_un_contrato_sin_pantallas(self, headers):
        cl = _nuevo_cliente(headers)
        ct = _nuevo_contrato(headers, cl["id"])
        r = requests.put(f"{FIN}/contracts/{ct['id']}/full", headers=headers,
                         json={"screens": []}, timeout=30)
        assert r.status_code == 400

    def test_contrato_inexistente_da_404(self, headers):
        r = requests.put(f"{FIN}/contracts/no-existe/full", headers=headers,
                         json={"term_months": 6}, timeout=30)
        assert r.status_code == 404


class TestBorrarContrato:
    def test_contrato_sin_facturas_se_borra_directo(self, headers):
        cl = _nuevo_cliente(headers)
        ct = _nuevo_contrato(headers, cl["id"])
        r = requests.delete(f"{FIN}/contracts/{ct['id']}", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["invoices_deleted"] == 0
        assert requests.get(f"{FIN}/contracts/{ct['id']}", headers=headers,
                            timeout=30).status_code == 404

    def test_con_facturas_sin_cobrar_pide_confirmacion_y_despues_borra_todo(self, headers):
        cl = _nuevo_cliente(headers)
        ct = _nuevo_contrato(headers, cl["id"])
        hoy = date.today()
        gen = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": cl["id"], "periods": [f"{hoy.year}-{hoy.month:02d}"],
            "send_email": False}, timeout=60)
        assert gen.status_code == 200 and gen.json()["created"] == 1, gen.text

        r = requests.delete(f"{FIN}/contracts/{ct['id']}", headers=headers, timeout=30)
        assert r.status_code == 409, r.text
        assert "sin cobrar" in r.json()["detail"]

        r = requests.delete(f"{FIN}/contracts/{ct['id']}?force=true", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["invoices_deleted"] == 1
        restantes = [i for i in requests.get(f"{FIN}/invoices", headers=headers, timeout=30).json()
                     if i.get("client_id") == cl["id"]]
        assert restantes == [], "las facturas del contrato borrado no pueden quedar huérfanas"

    def test_con_pagos_aplicados_no_se_borra_ni_con_force(self, headers):
        cl = _nuevo_cliente(headers)
        ct = _nuevo_contrato(headers, cl["id"])
        hoy = date.today()
        gen = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": cl["id"], "periods": [f"{hoy.year}-{hoy.month:02d}"],
            "send_email": False}, timeout=60)
        inv_id = [x for x in gen.json()["results"] if x["status"] == "created"][0]["invoice_id"]
        pay = requests.post(f"{FIN}/payments", headers=headers, json={
            "invoice_id": inv_id, "client_id": cl["id"], "amount": 50.0,
            "method": "cash"}, timeout=30)
        assert pay.status_code in (200, 201), pay.text

        for url in (f"{FIN}/contracts/{ct['id']}", f"{FIN}/contracts/{ct['id']}?force=true"):
            r = requests.delete(url, headers=headers, timeout=30)
            assert r.status_code == 400, r.text
            assert "pagos aplicados" in r.json()["detail"]
        assert requests.get(f"{FIN}/contracts/{ct['id']}", headers=headers,
                            timeout=30).status_code == 200

    def test_contrato_inexistente_da_404(self, headers):
        r = requests.delete(f"{FIN}/contracts/no-existe", headers=headers, timeout=30)
        assert r.status_code == 404


class TestBorrarFactura:
    def test_una_factura_anulada_se_borra_de_verdad(self, headers):
        cl = _nuevo_cliente(headers)
        _nuevo_contrato(headers, cl["id"])
        hoy = date.today()
        gen = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": cl["id"], "periods": [f"{hoy.year}-{hoy.month:02d}"],
            "send_email": False}, timeout=60)
        inv = [x for x in gen.json()["results"] if x["status"] == "created"][0]

        # se anula (es lo que hace el botón Cancel) y después se elimina
        requests.delete(f"{FIN}/invoices/{inv['invoice_id']}", headers=headers, timeout=30)
        r = requests.delete(f"{FIN}/invoices/{inv['invoice_id']}/purge", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["invoice_number"] == inv["invoice_number"]
        assert requests.get(f"{FIN}/invoices/{inv['invoice_id']}", headers=headers,
                            timeout=30).status_code == 404

    def test_una_factura_con_pagos_no_se_borra(self, headers):
        cl = _nuevo_cliente(headers)
        _nuevo_contrato(headers, cl["id"])
        hoy = date.today()
        gen = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": cl["id"], "periods": [f"{hoy.year}-{hoy.month:02d}"],
            "send_email": False}, timeout=60)
        inv_id = [x for x in gen.json()["results"] if x["status"] == "created"][0]["invoice_id"]
        requests.post(f"{FIN}/payments", headers=headers, json={
            "invoice_id": inv_id, "client_id": cl["id"], "amount": 25.0,
            "method": "cash"}, timeout=30)

        r = requests.delete(f"{FIN}/invoices/{inv_id}/purge", headers=headers, timeout=30)
        assert r.status_code == 400
        assert "cobrados" in r.json()["detail"]
        assert requests.get(f"{FIN}/invoices/{inv_id}", headers=headers,
                            timeout=30).status_code == 200

    def test_el_historial_conserva_el_numero_de_la_factura_borrada(self, headers):
        """La constancia del correo enviado no se puede perder al borrar la factura."""
        from datetime import datetime

        from dotenv import load_dotenv
        from pymongo import MongoClient
        load_dotenv("/app/backend/.env")
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

        cl = _nuevo_cliente(headers)
        _nuevo_contrato(headers, cl["id"])
        hoy = date.today()
        gen = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": cl["id"], "periods": [f"{hoy.year}-{hoy.month:02d}"],
            "send_email": False}, timeout=60)
        inv = [x for x in gen.json()["results"] if x["status"] == "created"][0]
        marca = uuid.uuid4().hex[:8]
        db.fin_email_log.insert_one({
            "id": str(uuid.uuid4()), "client_id": cl["id"], "invoice_id": inv["invoice_id"],
            "kind": "invoice", "to": cl["email"], "subject": f"{marca} envio",
            "ok": True, "error": "", "sent_at": datetime.utcnow().isoformat()})
        try:
            requests.delete(f"{FIN}/invoices/{inv['invoice_id']}/purge", headers=headers, timeout=30)
            rows = requests.get(f"{FIN}/email-log?limit=300&client_id={cl['id']}",
                                headers=headers, timeout=30).json()["rows"]
            fila = [x for x in rows if marca in (x.get("subject") or "")]
            assert fila, "el movimiento no puede desaparecer del historial"
            assert fila[0]["invoice_number"] == inv["invoice_number"]
        finally:
            db.fin_email_log.delete_many({"subject": {"$regex": marca}})

    def test_factura_inexistente_da_404(self, headers):
        r = requests.delete(f"{FIN}/invoices/no-existe/purge", headers=headers, timeout=30)
        assert r.status_code == 404


class TestPanelNoSeQuedaCacheado:
    def test_el_html_del_panel_pide_revalidar(self):
        """El dueño publicaba y seguía viendo la versión vieja: el navegador
        cacheaba el HTML, y los `?v=` nuevos de los scripts viven dentro de ese
        HTML. Tiene que salir con `no-cache`."""
        r = requests.get(f"{BASE_URL}/api/dashboard", timeout=30)
        assert r.status_code == 200
        assert "no-cache" in r.headers.get("cache-control", "").lower()
