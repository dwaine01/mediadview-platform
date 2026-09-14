"""Verificación INDEPENDIENTE (T1) — iter67 WhatsApp channel.

Objetivo: probar contra el URL público que el canal WhatsApp está APAGADO
y que NO rompe el sistema actual (email/facturas/recordatorios/panel).
Además revisar seguridad (no filtrar secretos) y contrato de endpoints.
"""
import hashlib
import hmac
import json
import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")

# Se pega al preview público a propósito para verificar lo que el usuario ve.
BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://sprint1-signage.preview.emergentagent.com").rstrip("/")
FIN = f"{BASE_URL}/api/finance"
WA = f"{BASE_URL}/api/whatsapp"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


# ═══════════════ CANAL APAGADO NO ROMPE EL SISTEMA ACTUAL ═══════════════
class TestSistemaActualSigueEnPie:
    """Con WhatsApp apagado, todo lo que ya funcionaba tiene que seguir igual."""

    def test_email_log_sigue_respondiendo(self, headers):
        r = requests.get(f"{FIN}/email-log", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data or "logs" in data or isinstance(data, (list, dict))

    def test_generate_for_client_endpoint_no_crashea(self, headers):
        """El endpoint debe responder — NO 500 — aún con canal WhatsApp apagado.

        Lo llamamos con un client_id inexistente: si el canal apagado rompiera
        el flujo, se caería con 500 o timeout. Debe dar 404 «Client not found».
        """
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers,
                          json={"client_id": f"ghost-{uuid.uuid4().hex[:6]}",
                                "periods": ["2026-01"], "send_email": False},
                          timeout=30)
        # 404 esperado (cliente inexistente); NUNCA 500.
        assert r.status_code == 404, r.text
        assert r.status_code != 500


# ═══════════════ SEGURIDAD: no filtrar secretos ═══════════════
class TestNoSeFiltranSecretos:
    def test_status_no_expone_ningun_secreto(self, headers):
        r = requests.get(f"{FIN}/whatsapp/status", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        raw = r.text
        data = r.json()

        # ningún campo puede llamarse token/secret con valor de string
        for k, v in data.items():
            if k in ("has_token", "has_app_secret", "webhook_ready", "connected"):
                assert isinstance(v, bool)
            if any(bad in k.lower() for bad in ("token", "secret", "password", "api_key")):
                # sólo permitidos los booleanos has_*
                assert isinstance(v, bool), f"Campo secreto expuesto: {k}={v!r}"

        # no debe aparecer ningún valor real que pareciera un token de Meta
        assert "EAA" not in raw, "un token Meta arranca con EAA"

        # los 4 templates deben venir
        assert set(data["templates"]) == {
            "mediaview_invoice_created", "mediaview_invoice_due",
            "mediaview_invoice_overdue", "mediaview_payment_received"}
        assert data["webhook_url"].endswith("/api/whatsapp/webhook")
        assert data["connected"] is False
        assert data["has_token"] is False
        assert data["has_app_secret"] is False

    def test_status_pide_sesion(self):
        r = requests.get(f"{FIN}/whatsapp/status", timeout=30)
        assert r.status_code in (401, 403)


# ═══════════════ ENDPOINTS: sin credenciales dan 400, nunca 500 ═══════════════
class TestEndpointsSinCredenciales:
    def test_whatsapp_test_da_400_no_500(self, headers):
        r = requests.post(f"{FIN}/whatsapp/test", headers=headers,
                          json={"to": "6145551234"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "conectado" in r.json().get("detail", "").lower()

    def test_send_invoice_whatsapp_id_inexistente_da_404(self, headers):
        r = requests.post(f"{FIN}/invoices/does-not-exist-xyz/whatsapp",
                          headers=headers, timeout=30)
        assert r.status_code == 404, r.text

    def test_send_invoice_whatsapp_con_factura_real_da_400(self, headers):
        # crear cliente y factura reales para probar el 400 del canal apagado
        tag = uuid.uuid4().hex[:6]
        cli = requests.post(f"{FIN}/clients", headers=headers, json={
            "business_name": f"TEST_iter67_snd {tag}",
            "representative": "QA",
            "email": f"snd.{tag}@example.com",
            "phone": "614-555-0101",
            "address_line1": "1", "city": "Columbus",
            "state": "OH", "zip": "43205",
        }, timeout=30).json()
        try:
            inv = requests.post(f"{FIN}/invoices", headers=headers, json={
                "client_id": cli["id"], "invoice_number": f"TEST-{tag}",
                "invoice_date": "2026-01-01", "due_date": "2026-01-31",
                "line_items": [{"description": "svc", "quantity": 1, "rate": 50}],
                "total": 50,
            }, timeout=30)
            if inv.status_code not in (200, 201):
                pytest.skip(f"no se pudo crear factura: {inv.status_code} {inv.text}")
            invoice_id = inv.json().get("id") or inv.json().get("invoice", {}).get("id")
            if not invoice_id:
                pytest.skip("factura sin id en respuesta")
            r = requests.post(f"{FIN}/invoices/{invoice_id}/whatsapp",
                              headers=headers, timeout=30)
            assert r.status_code == 400, r.text
            assert "conectado" in r.json().get("detail", "").lower() or \
                   "whatsapp" in r.json().get("detail", "").lower()
        finally:
            requests.delete(f"{FIN}/clients/{cli['id']}/purge", headers=headers,
                            params={"confirm_name": cli["business_name"],
                                    "force": "true"}, timeout=30)


# ═══════════════ /communications: dos canales ═══════════════
class TestCommunicationsInsertadoManual:
    def test_devuelve_email_y_whatsapp_insertados(self, headers):
        """Insertamos filas a mano en fin_email_log y wa_messages y se leen."""
        import asyncio

        from motor.motor_asyncio import AsyncIOMotorClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "mediaview_db")
        invoice_id = f"TEST_iter67_comm_{uuid.uuid4().hex[:6]}"

        async def seed():
            cli = AsyncIOMotorClient(mongo_url)
            try:
                d = cli[db_name]
                await d.fin_email_log.insert_one({
                    "id": f"emailrow-{invoice_id}", "invoice_id": invoice_id,
                    "to": "test@x.com", "status": "sent",
                    "sent_at": "2026-01-10T00:00:00"})
                await d.wa_messages.insert_one({
                    "id": f"warow-{invoice_id}", "invoice_id": invoice_id,
                    "to": "16145551234", "kind": "invoice_created", "ok": True,
                    "status": "delivered", "sent_at": "2026-01-10T00:01:00",
                    "template": "mediaview_invoice_created",
                    "message_id": "wamid.TEST"})
            finally:
                cli.close()

        async def cleanup():
            cli = AsyncIOMotorClient(mongo_url)
            try:
                d = cli[db_name]
                await d.fin_email_log.delete_one({"id": f"emailrow-{invoice_id}"})
                await d.wa_messages.delete_one({"id": f"warow-{invoice_id}"})
            finally:
                cli.close()

        try:
            asyncio.run(seed())
            r = requests.get(f"{FIN}/invoices/{invoice_id}/communications",
                             headers=headers, timeout=30)
            assert r.status_code == 200, r.text
            data = r.json()
            assert "email" in data and "whatsapp" in data
            assert len(data["email"]) == 1
            assert len(data["whatsapp"]) == 1
            assert data["email"][0]["to"] == "test@x.com"
            assert data["whatsapp"][0]["to"] == "16145551234"
            assert data["whatsapp"][0]["message_id"] == "wamid.TEST"
            assert "_id" not in data["email"][0]
            assert "_id" not in data["whatsapp"][0]
        finally:
            asyncio.run(cleanup())


# ═══════════════ Webhook Meta ═══════════════
class TestWebhookMeta:
    def test_get_verify_fail(self):
        r = requests.get(f"{WA}/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "wrong_token",
            "hub.challenge": "999"}, timeout=30)
        assert r.status_code == 403

    def test_post_statuses_responde_200(self):
        payload = {"object": "whatsapp_business_account", "entry": [
            {"changes": [{"field": "messages", "value": {"statuses": [
                {"id": "wamid.T1", "status": "read"}]}}]}]}
        r = requests.post(f"{WA}/webhook", json=payload, timeout=30)
        assert r.status_code == 200

    def test_firma_valida_sobre_body_crudo(self):
        """Si se re-serializa el JSON los bytes cambian y la firma falla."""
        import whatsapp as wa
        raw = b'{"a":1,"b":2}'
        secret = "test_secret_xyz"
        firma = "sha256=" + hmac.new(
            secret.encode(), raw, hashlib.sha256).hexdigest()
        orig = wa.APP_SECRET
        try:
            wa.APP_SECRET = secret
            assert wa.valid_signature(raw, firma) is True
            # cualquier byte extra rompe
            assert wa.valid_signature(raw + b"\n", firma) is False
            # y si re-serializamos con json.dumps cambia el espaciado
            reser = json.dumps(json.loads(raw), separators=(",", ":")).encode()
            # aún si es igual la firma es la misma; pero con space cambia:
            reser2 = json.dumps(json.loads(raw)).encode()  # default con espacios
            if reser2 != raw:
                assert wa.valid_signature(reser2, firma) is False
        finally:
            wa.APP_SECRET = orig


# ═══════════════ Cliente: campos WhatsApp ═══════════════
class TestClienteCamposWhatsApp:
    def test_crea_con_whatsapp_y_apaga_solo_uno(self, headers):
        tag = uuid.uuid4().hex[:6]
        cli = requests.post(f"{FIN}/clients", headers=headers, json={
            "business_name": f"TEST_iter67_cli {tag}",
            "representative": "QA",
            "email": f"cli.{tag}@example.com",
            "phone": "614-555-1234",
            "address_line1": "1", "city": "Columbus",
            "state": "OH", "zip": "43205",
            "whatsapp": "614-555-9999", "country_code": "52",
        }, timeout=30)
        assert cli.status_code in (200, 201), cli.text
        c = cli.json()
        try:
            assert c["whatsapp"] == "614-555-9999"
            assert c["country_code"] == "52"
            assert c["wa_invoice_notify"] is True, "ON por defecto"
            assert c["wa_reminder_notify"] is True, "ON por defecto"

            # apagar sólo recordatorios y cambiar language
            upd = requests.put(f"{FIN}/clients/{c['id']}", headers=headers, json={
                "wa_reminder_notify": False, "language": "en"}, timeout=30)
            assert upd.status_code in (200, 204), upd.text
            g = requests.get(f"{FIN}/clients/{c['id']}", headers=headers, timeout=30).json()
            assert g["wa_reminder_notify"] is False
            assert g["wa_invoice_notify"] is True, "no debe apagar los dos"
            assert g["language"] == "en"
        finally:
            requests.delete(f"{FIN}/clients/{c['id']}/purge", headers=headers,
                            params={"confirm_name": c["business_name"],
                                    "force": "true"}, timeout=30)
