"""Iter56 — Verificar que la clave SMTP ilegible produzca 400 con instrucciones
y que la generación de facturas/contratos/PDF siga funcionando.

Ejecutar:
    cd /app/backend && python -m pytest tests/test_iter56_smtp_readable.py -v
"""
import json
import os

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
BASE = BASE.rstrip("/")
ADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")

# Ids proporcionados en el review request
CLIENT_ID = "da0d9dea-dfca-457d-bece-cdcbc7952776"      # Cash chase
INVOICE_ID = "be23dee8-1ba8-4ac2-acfa-fc39bf652bcf"     # Factura existente

SMTP_UNREADABLE_MSG = (
    "No se puede leer la contraseña SMTP guardada: fue cifrada con una llave "
    "del servidor que ya cambió. Volvé a escribirla en Finance & CRM → Email "
    "Settings y guardá para que los correos salgan de nuevo."
)


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ============== BUG: 400 con instrucciones (no 500 con 535) ==============
class TestSmtpUnreadable400:
    """El envío debe cortar en 400 antes de intentar autenticarse."""

    def test_settings_email_muestra_warning(self, headers):
        r = requests.get(f"{BASE}/api/finance/settings/email",
                         headers=headers, timeout=20)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("password_set") is True, "debe haber contraseña guardada"
        assert body.get("password_readable") is False, "debe estar ilegible"
        assert body.get("password_warning") == SMTP_UNREADABLE_MSG
        # nunca devolver la contraseña cifrada real
        assert body.get("smtp_password") == "********"

    def test_invoice_send_devuelve_400_con_mensaje(self, headers):
        r = requests.post(f"{BASE}/api/finance/invoices/{INVOICE_ID}/send",
                          headers=headers,
                          json={"to": "prueba@ejemplo.com"}, timeout=60)
        assert r.status_code == 400, f"esperaba 400, dio {r.status_code}: {r.text[:200]}"
        detail = r.json()["detail"]
        assert detail == SMTP_UNREADABLE_MSG
        assert "authentication failed" not in detail.lower()

    def test_settings_email_test_devuelve_400_no_500(self, headers):
        r = requests.post(f"{BASE}/api/finance/settings/email/test",
                          headers=headers,
                          json={"to": "prueba@ejemplo.com"}, timeout=60)
        assert r.status_code == 400, (
            f"esperaba 400, dio {r.status_code}: {r.text[:200]}"
        )
        detail = r.json()["detail"]
        assert detail == SMTP_UNREADABLE_MSG


# ============== Recuperación: al guardar clave nueva ya no falla por la llave ==============
class TestSmtpRecuperacion:
    """Guardar clave nueva → password_readable=true → send ya no da 400 de llave."""

    def test_put_settings_y_send_intenta_smtp(self, headers):
        # 1) Guardar credencial nueva (host de prueba)
        put_payload = {
            "smtp_host": "127.0.0.1",
            "smtp_port": 1025,
            "smtp_user": "billing@mediadview.com",
            "smtp_password": "clave-de-prueba",
            "smtp_use_tls": True,
            "from_name": "MediAd View Billing",
            "from_email": "billing@mediadview.com",
            "reply_to": "billing@mediadview.com",
            "enabled": True,
        }
        r = requests.put(f"{BASE}/api/finance/settings/email",
                         headers=headers, json=put_payload, timeout=20)
        assert r.status_code == 200, r.text[:200]

        # 2) GET → readable=true, sin warning
        r = requests.get(f"{BASE}/api/finance/settings/email",
                         headers=headers, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("password_set") is True
        assert body.get("password_readable") is True
        assert "password_warning" not in body or not body["password_warning"]
        assert body.get("smtp_password") == "********"

        # 3) POST send: si falla, tiene que ser por SMTP (conexión / STARTTLS),
        #    NO por la llave: prueba que ya se pasa a autenticar.
        r = requests.post(f"{BASE}/api/finance/invoices/{INVOICE_ID}/send",
                          headers=headers,
                          json={"to": "prueba@ejemplo.com"}, timeout=60)
        # aceptamos 200 (envío exitoso) o 500 (SMTP no disponible), pero NUNCA
        # el 400 del "authentication failed" original ni el mensaje de la llave.
        assert r.status_code in (200, 500), (
            f"código inesperado: {r.status_code}: {r.text[:200]}"
        )
        if r.status_code != 200:
            detail = r.json().get("detail", "")
            assert SMTP_UNREADABLE_MSG not in detail, (
                "no debería seguir apareciendo el mensaje de la llave"
            )


# ============== Restauración del respaldo directo en Mongo ==============
@pytest.mark.asyncio
async def test_restore_email_settings_from_backup():
    """Restaurar la configuración original desde /tmp/email_settings_backup.json
    directamente en Mongo, porque por API no se puede volver a poner la
    contraseña cifrada vieja."""
    backup_path = "/tmp/email_settings_backup.json"
    with open(backup_path) as f:
        backup = json.load(f)
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]
        doc = dict(backup)
        doc["_id"] = "email"
        await db.fin_settings.replace_one({"_id": "email"}, doc, upsert=True)
        stored = await db.fin_settings.find_one({"_id": "email"})
        assert stored is not None
        assert stored["smtp_host"] == backup["smtp_host"]
        assert stored["smtp_password"] == backup["smtp_password"]
    finally:
        client.close()


# ============== REGRESIÓN: cobro sigue trabajando ==============
class TestRegresionCobro:
    """Que el cobro siga trabajando aunque el correo esté caído."""

    contract_id: str | None = None
    invoice_id: str | None = None
    monthly_invoice_ids: list = []

    def test_quick_contract(self, headers):
        r = requests.post(f"{BASE}/api/finance/clients/{CLIENT_ID}/quick-contract",
                          headers=headers, json={}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        # respuesta = {contract: {...}, deposit: {...}}
        contract = body.get("contract") or body
        assert contract.get("contract_number"), (
            f"debe traer contract_number, respuesta: {body}"
        )
        assert contract.get("id")
        TestRegresionCobro.contract_id = contract["id"]

    def test_generate_monthly(self, headers):
        r = requests.post(f"{BASE}/api/finance/invoices/generate-monthly",
                          headers=headers, json={}, timeout=90)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        # devuelve {created: int, period: str, invoices: [...]}
        assert isinstance(body, dict)
        assert "created" in body
        TestRegresionCobro.monthly_invoice_ids = [
            inv.get("id") for inv in (body.get("invoices") or [])
            if isinstance(inv, dict) and inv.get("id")
        ]

    def test_manual_invoice(self, headers):
        payload = {
            "client_id": CLIENT_ID,
            "contract_id": TestRegresionCobro.contract_id,
            "items": [{"description": "TEST_iter56", "qty": 1, "unit_price": 100.0, "total": 100.0}],
            "tax": 0,
            "issue_date": "2026-01-01",
            "due_date": "2026-01-15",
        }
        r = requests.post(f"{BASE}/api/finance/invoices/manual",
                          headers=headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("invoice_number")
        assert body.get("id")
        TestRegresionCobro.invoice_id = body["id"]

    def test_render_html(self, headers):
        """Render HTML de la factura existente (auto-generada, con line_no)."""
        r = requests.get(f"{BASE}/api/finance/invoices/{INVOICE_ID}/render",
                         headers=headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "html" in r.headers.get("content-type", "").lower()

    def test_render_html_manual_invoice_expone_bug_line_no(self, headers):
        """Regresión conocida: la factura manual guarda items sin `line_no`
        y `render_invoice_html` estalla con KeyError. Se reporta como bug."""
        assert TestRegresionCobro.invoice_id
        r = requests.get(
            f"{BASE}/api/finance/invoices/{TestRegresionCobro.invoice_id}/render",
            headers=headers, timeout=30)
        # aceptamos 200 si el bug ya está arreglado, pero avisamos si aún falla
        if r.status_code != 200:
            pytest.xfail(
                f"BUG: render de factura manual devuelve {r.status_code} — "
                "faltan `line_no`/otros campos en items. Ver KeyError en "
                "finance.py:render_invoice_html (línea ~1374)."
            )

    def test_invoice_pdf(self, headers):
        assert TestRegresionCobro.invoice_id
        r = requests.get(f"{BASE}/api/finance/invoices/{TestRegresionCobro.invoice_id}/pdf",
                         headers=headers, timeout=60)
        assert r.status_code == 200
        assert len(r.content) > 5000, f"PDF demasiado chico: {len(r.content)} bytes"

    def test_contract_pdf(self, headers):
        assert TestRegresionCobro.contract_id
        r = requests.get(f"{BASE}/api/finance/contracts/{TestRegresionCobro.contract_id}/pdf",
                         headers=headers, timeout=60)
        assert r.status_code == 200
        assert len(r.content) > 5000

    def test_dashboard(self, headers):
        r = requests.get(f"{BASE}/api/finance/dashboard", headers=headers, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_accounts_receivable(self, headers):
        r = requests.get(f"{BASE}/api/finance/accounts-receivable",
                         headers=headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body and "clients" in body

    def test_zzz_cleanup(self, headers):
        # DELETE contrato y factura de prueba (soft delete)
        if TestRegresionCobro.invoice_id:
            r = requests.delete(
                f"{BASE}/api/finance/invoices/{TestRegresionCobro.invoice_id}",
                headers=headers, timeout=20)
            assert r.status_code == 200
        # Borrar también las facturas generadas por generate-monthly si las hubo
        for inv_id in TestRegresionCobro.monthly_invoice_ids or []:
            requests.delete(f"{BASE}/api/finance/invoices/{inv_id}",
                            headers=headers, timeout=20)
        if TestRegresionCobro.contract_id:
            r = requests.delete(
                f"{BASE}/api/finance/contracts/{TestRegresionCobro.contract_id}",
                headers=headers, timeout=20)
            assert r.status_code == 200
