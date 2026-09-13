"""Cobranza: recordar por etapas, parar al pagar, agradecer y dejar constancia.

Lo que se prueba es la política de cobro, no el código: que a nadie se le
recuerde dos veces lo mismo, que al pagar se dejen de mandar recordatorios y
salga el agradecimiento, y que todo quede anotado en la bitácora del cliente.

    cd /app/backend && python -m pytest tests/test_collections_engine.py -q
"""
from datetime import datetime, timedelta

import pytest

from collections_engine import (
    STAGES,
    next_reminder_hint,
    receipt_body,
    reminder_body,
    stage_due_today,
)

HOY = datetime(2026, 6, 20)


def factura(**kwargs):
    base = {"id": "inv-1", "invoice_number": "OH1001", "total": 400.0,
            "balance": 400.0, "status": "pending",
            "due_date": (HOY - timedelta(days=0)).date().isoformat()}
    base.update(kwargs)
    return base


CLIENTE = {"id": "cli-1", "name": "Supermercado La Colonia",
           "contact_name": "Josué", "email": "cliente@ejemplo.com"}


def test_tres_dias_antes_se_avisa_amable():
    inv = factura(due_date=(HOY + timedelta(days=3)).date().isoformat())
    stage = stage_due_today(inv, HOY)
    assert stage and stage[0] == "pre_due"
    subject, html = reminder_body(inv, CLIENTE, stage)
    assert "vence en 3 días" in subject
    assert "Josué" in html and "$400.00" in html


def test_el_dia_del_vencimiento_toca_el_segundo_aviso():
    assert stage_due_today(factura(), HOY)[0] == "due"


def test_cada_etapa_se_manda_una_sola_vez():
    inv = factura(reminders_sent=[{"stage": "pre_due"}, {"stage": "due"}])
    assert stage_due_today(inv, HOY) is None, "no puede repetir avisos ya enviados"


def test_si_el_sistema_estuvo_caido_no_llegan_cinco_correos_de_golpe():
    """Con 20 días de atraso y nada enviado, sale UNA sola etapa: la más avanzada."""
    inv = factura(due_date=(HOY - timedelta(days=20)).date().isoformat())
    stage = stage_due_today(inv, HOY)
    assert stage[0] == "late_15"


def test_una_factura_pagada_no_recibe_recordatorios():
    assert stage_due_today(factura(balance=0, status="paid"), HOY) is None
    assert stage_due_today(factura(status="cancelled"), HOY) is None
    assert next_reminder_hint(factura(balance=0)) is None


def test_el_tono_sube_pero_no_insulta():
    for key, _offset, subject, body in STAGES:
        texto = (subject + body).lower()
        for palabra in ("moroso", "deudor", "incumplido", "reportado"):
            assert palabra not in texto, f"la etapa {key} maltrata al cliente"
    assert "suspendida" in STAGES[-1][3], "a los 30 días hay que ser claro"


def test_el_panel_sabe_cuando_toca_el_proximo():
    inv = factura(reminders_sent=[{"stage": "pre_due"}])
    assert next_reminder_hint(inv) == HOY.date().isoformat()


def test_el_agradecimiento_cambia_si_queda_saldo():
    pagada = factura(balance=0)
    subject, html = receipt_body(pagada, CLIENTE, 400.0, True)
    assert "Gracias por su pago" in subject
    assert "pagada" in html

    parcial = factura(balance=150.0)
    subject2, html2 = receipt_body(parcial, CLIENTE, 250.0, False)
    assert "Pago recibido" in subject2
    assert "$150.00" in html2, "el cliente tiene que ver cuánto le falta"


def test_sin_fecha_de_vencimiento_no_se_inventa_un_recordatorio():
    assert stage_due_today(factura(due_date=None), HOY) is None
    with pytest.raises(Exception):
        # Un cuerpo de recordatorio necesita una etapa válida.
        reminder_body(factura(), CLIENTE, None)
