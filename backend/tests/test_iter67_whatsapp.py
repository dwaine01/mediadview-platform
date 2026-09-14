"""Canal WhatsApp (Meta Cloud API) — MediaView Communication System.

Pedido del dueño: «cuando MediaView genere una factura → Email + WhatsApp con el
PDF → seguimiento de entregado/leído → recordatorios automáticos si no paga →
detener recordatorios cuando pague». El correo NO se toca.

En este entorno NO hay credenciales de Meta: el canal está apagado a propósito.
Lo que se fija acá es el contrato del módulo (que apagado no rompa nada, las
reglas de negocio, el webhook y la seguridad), no el envío real.
"""
import hashlib
import hmac
import json
import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"
WA = f"{BASE_URL}/api/whatsapp"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


class TestNumeroDeTelefono:
    """El dueño carga «(614) 555-1234» y el código aparte; Meta quiere dígitos."""

    def test_limpia_y_agrega_el_codigo_de_pais(self):
        from whatsapp import normalize_phone
        assert normalize_phone("(614) 555-1234", "1") == "16145551234"
        assert normalize_phone("+1 614-555-1234", "1") == "16145551234"
        assert normalize_phone("6145551234") == "16145551234"      # EE.UU. por defecto
        assert normalize_phone("16145551234", "1") == "16145551234", "no duplica el código"
        assert normalize_phone("", "1") == ""
        assert normalize_phone("809 555 1234", "1") == "18095551234"  # Rep. Dominicana

    def test_cae_al_telefono_comun_si_no_hay_whatsapp(self):
        from whatsapp import client_whatsapp
        assert client_whatsapp({"phone": "614-555-1234"}) == "16145551234"
        assert client_whatsapp({"whatsapp": "614-555-9999",
                                "phone": "614-555-1234"}) == "16145559999"
        assert client_whatsapp({}) == ""


class TestInterruptoresPorCliente:
    """ON por defecto para todo cliente con número; se apaga uno por uno."""

    def test_on_por_defecto_y_se_puede_apagar(self):
        from whatsapp import wants
        con_numero = {"phone": "614-555-1234"}
        assert wants(con_numero, "invoice") is True
        assert wants(con_numero, "reminder") is True
        assert wants({**con_numero, "wa_invoice_notify": False}, "invoice") is False
        assert wants({**con_numero, "wa_reminder_notify": False}, "reminder") is False
        # apagar las facturas no apaga los recordatorios
        assert wants({**con_numero, "wa_invoice_notify": False}, "reminder") is True

    def test_sin_numero_nunca_manda(self):
        from whatsapp import wants
        assert wants({"wa_invoice_notify": True}, "invoice") is False


class TestApagadoNoRompeNada:
    """Sin credenciales el sistema sigue igual: el correo manda y WhatsApp avisa."""

    def test_is_configured_es_falso_y_explica_que_falta(self):
        import whatsapp as wa
        assert wa.is_configured() is False
        motivo = wa.missing_config()
        assert "Phone Number ID" in motivo and "Token" in motivo

    def test_enviar_factura_devuelve_el_motivo_sin_explotar(self):
        import asyncio

        import whatsapp as wa
        res = asyncio.run(wa.send_invoice_whatsapp(
            None, {"id": "i1", "invoice_number": "OH1", "total": 100},
            {"id": "c1", "phone": "614-555-1234"}))
        assert res["ok"] is False and res["skipped"] is True
        assert "no está conectado" in res["reason"]

    def test_el_endpoint_de_prueba_avisa_que_falta_configurar(self, headers):
        r = requests.post(f"{FIN}/whatsapp/test", headers=headers,
                          json={"to": "6145551234"}, timeout=30)
        assert r.status_code == 400
        assert "no está conectado" in r.json()["detail"]


class TestNoMandarSiYaPago:
    """Regla que no se puede romper: nunca un recordatorio de una factura pagada."""

    @pytest.mark.parametrize("factura", [
        {"status": "paid", "balance": 0},
        {"status": "cancelled", "balance": 500},
        {"status": "overdue", "balance": 0},
    ])
    def test_factura_pagada_o_anulada_corta_el_recordatorio(self, factura):
        import asyncio

        import whatsapp as wa
        res = asyncio.run(wa.send_reminder_whatsapp(
            None, {"id": "i1", "invoice_number": "OH1", **factura},
            {"id": "c1", "phone": "614-555-1234"}, "late_7", "7 días"))
        assert res["skipped"] is True
        assert "pagada o anulada" in res["reason"]


class TestEstadoDeLaConexion:
    def test_no_expone_el_token_ni_el_app_secret(self, headers):
        r = requests.get(f"{FIN}/whatsapp/status", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # No puede viajar NINGÚN valor secreto (los nombres de campo
        # `has_token`/`has_app_secret` son booleanos, esos sí están permitidos).
        import whatsapp as wa
        crudo = json.dumps(data)
        for secreto in (wa.ACCESS_TOKEN, wa.APP_SECRET, wa.VERIFY_TOKEN):
            if secreto:
                assert secreto not in crudo, "el panel no puede ver los secretos"
        assert "EAA" not in crudo, "un token de Meta arranca con EAA"
        assert data["has_token"] is False and data["has_app_secret"] is False
        assert data["connected"] is False
        assert data["templates"] == ["mediaview_invoice_created", "mediaview_invoice_due",
                                     "mediaview_invoice_overdue", "mediaview_payment_received"]
        assert data["webhook_url"].endswith("/api/whatsapp/webhook")

    def test_pide_sesion(self):
        assert requests.get(f"{FIN}/whatsapp/status", timeout=30).status_code in (401, 403)


class TestWebhook:
    def test_la_verificacion_falla_sin_el_token_correcto(self):
        r = requests.get(f"{WA}/webhook", timeout=30, params={
            "hub.mode": "subscribe", "hub.verify_token": "cualquiera",
            "hub.challenge": "12345"})
        assert r.status_code == 403

    def test_acepta_el_aviso_de_meta_y_responde_200(self):
        """Si no se responde 200 rápido, Meta reintenta el webhook por días."""
        r = requests.post(f"{WA}/webhook", timeout=30, json={
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": {"statuses": [
                {"id": "wamid.TEST", "status": "delivered"}]}}]}]})
        assert r.status_code == 200

    def test_la_firma_se_calcula_sobre_el_body_crudo(self):
        """Parsear y re-serializar el JSON rompe la firma: por eso se valida
        sobre los bytes tal como llegan."""
        import whatsapp as wa
        raw = b'{"entry":[{"id":"1"}]}'
        secreto = "s3cr3t"
        firma = "sha256=" + hmac.new(secreto.encode(), raw, hashlib.sha256).hexdigest()
        original = wa.APP_SECRET
        try:
            wa.APP_SECRET = secreto
            assert wa.valid_signature(raw, firma) is True
            assert wa.valid_signature(raw + b" ", firma) is False
            assert wa.valid_signature(raw, "sha256=abc") is False
            assert wa.valid_signature(raw, "") is False
        finally:
            wa.APP_SECRET = original


class TestHistorialDeComunicacion:
    def test_devuelve_los_dos_canales(self, headers):
        """Es lo que se mira cuando el cliente dice «no me llegó la factura»."""
        r = requests.get(f"{FIN}/invoices/cualquiera/communications", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"email": [], "whatsapp": []}


class TestCamposDelCliente:
    def test_se_guardan_los_datos_y_los_interruptores(self, headers):
        import uuid
        tag = uuid.uuid4().hex[:6]
        cl = requests.post(f"{FIN}/clients", headers=headers, json={
            "business_name": f"TEST_wa {tag}", "representative": "Josue",
            "email": f"wa.{tag}@example.com", "phone": "614-555-1234",
            "address_line1": "1", "city": "Columbus", "state": "OH", "zip": "43205",
            "whatsapp": "614-555-9999", "country_code": "1",
        }, timeout=30).json()
        assert cl["whatsapp"] == "614-555-9999"
        assert cl["wa_invoice_notify"] is True, "ON por defecto"
        assert cl["wa_reminder_notify"] is True

        requests.put(f"{FIN}/clients/{cl['id']}", headers=headers, json={
            "wa_invoice_notify": False, "language": "en"}, timeout=30)
        upd = requests.get(f"{FIN}/clients/{cl['id']}", headers=headers, timeout=30).json()
        assert upd["wa_invoice_notify"] is False
        assert upd["wa_reminder_notify"] is True
        assert upd["language"] == "en"

        requests.delete(f"{FIN}/clients/{cl['id']}/purge", headers=headers,
                        params={"confirm_name": cl["business_name"], "force": "true"}, timeout=30)


class TestSinDuplicados:
    def test_la_clave_de_deduplicacion_es_por_factura_plantilla_y_numero(self):
        """Un reintento del cron o un doble clic no puede mandar dos veces."""
        import inspect

        import whatsapp as wa
        src = inspect.getsource(wa.send_invoice_whatsapp)
        assert 'dedupe = f"{kind}:{invoice.get(\'id\')}:{to}"' in src
        assert "already_sent(db, dedupe)" in src
        src_rem = inspect.getsource(wa.send_reminder_whatsapp)
        assert "already_sent(db, dedupe)" in src_rem
        assert "stage" in src_rem, "la etapa forma parte de la clave"


class TestIntegracionConElCobro:
    def test_el_cron_manda_whatsapp_despues_del_correo(self):
        import inspect

        import finance_scheduler
        src = inspect.getsource(finance_scheduler.monthly_billing_job)
        assert "send_invoice_whatsapp" in src
        assert src.index("_send_invoice_email") < src.index("send_invoice_whatsapp"), \
            "el correo va primero: WhatsApp es canal adicional"

    def test_los_recordatorios_y_el_recibo_tambien_salen_por_whatsapp(self):
        import inspect

        import finance_scheduler
        assert "send_reminder_whatsapp" in inspect.getsource(finance_scheduler.overdue_reminder_job)
        assert "send_payment_received_whatsapp" in inspect.getsource(
            finance_scheduler.send_payment_receipt)

    def test_un_fallo_de_whatsapp_no_frena_la_facturacion(self):
        import inspect

        import finance_scheduler
        src = inspect.getsource(finance_scheduler.monthly_billing_job)
        bloque = src[src.index("send_invoice_whatsapp"):]
        assert "except Exception" in bloque, \
            "si WhatsApp falla, la factura ya salió por correo y el cobro no puede caerse"
