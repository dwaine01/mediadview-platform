"""Idioma de las plantillas: Meta rechaza (132001) si no es el exacto aprobado.

El dueño creó las plantillas en el Administrador de WhatsApp y Meta las guardó
con una variante de español (`es`, `es_MX` o `es_ES`). Si el servidor manda otra
variante, el envío falla aunque la plantilla exista y esté aprobada. Acá se fija
que el idioma salga del listado real del WABA.
"""
import asyncio
import sys

import pytest

sys.path.insert(0, "/app/backend")

import whatsapp as wa  # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def sin_cache():
    wa._TPL_CACHE.update(at=0.0, rows=[])
    yield
    wa._TPL_CACHE.update(at=0.0, rows=[])


def fingir(rows, monkeypatch):
    async def falso(force=False):
        return rows
    monkeypatch.setattr(wa, "list_templates", falso)


TPL = "mediaview_invoice_created"


def test_usa_la_variante_aprobada_cuando_no_existe_el_es_generico(monkeypatch):
    fingir([{"name": TPL, "language": "es_MX", "status": "APPROVED"}], monkeypatch)
    assert corre(wa.resolve_lang(TPL, "es")) == "es_MX"


def test_si_el_es_generico_esta_aprobado_se_respeta(monkeypatch):
    fingir([{"name": TPL, "language": "es", "status": "APPROVED"},
            {"name": TPL, "language": "es_MX", "status": "APPROVED"}], monkeypatch)
    assert corre(wa.resolve_lang(TPL, "es")) == "es"


def test_ingles_no_se_reemplaza_por_una_variante_de_español(monkeypatch):
    fingir([{"name": TPL, "language": "es_MX", "status": "APPROVED"},
            {"name": TPL, "language": "en_US", "status": "APPROVED"}], monkeypatch)
    assert corre(wa.resolve_lang(TPL, "en")) == "en_US"


def test_una_plantilla_pendiente_no_cuenta_como_aprobada(monkeypatch):
    fingir([{"name": TPL, "language": "es_MX", "status": "PENDING"}], monkeypatch)
    assert corre(wa.resolve_lang(TPL, "es")) == "es", \
        "si no hay ninguna aprobada se manda el idioma pedido y Meta explica el motivo"


def test_otra_plantilla_aprobada_no_se_usa_por_error(monkeypatch):
    fingir([{"name": "mediaview_invoice_due", "language": "es_MX",
             "status": "APPROVED"}], monkeypatch)
    assert corre(wa.resolve_lang(TPL, "es")) == "es"


def test_si_meta_no_responde_el_envio_sigue_intentando(monkeypatch):
    async def explota(force=False):
        raise wa.WhatsAppError(500, {"error": {"message": "Meta caído"}})
    monkeypatch.setattr(wa, "list_templates", explota)
    assert corre(wa.resolve_lang(TPL, "es")) == "es", \
        "un problema al listar plantillas no puede frenar la factura"


def test_sin_credenciales_no_llama_a_meta():
    assert corre(wa.list_templates()) == []


def test_el_listado_se_cachea_para_no_pegarle_a_meta_en_cada_factura(monkeypatch):
    llamadas = {"n": 0}

    async def falso_graph(method, url, **kw):
        llamadas["n"] += 1
        return {"data": [{"name": TPL, "language": "es_MX", "status": "APPROVED"}]}

    monkeypatch.setattr(wa, "graph", falso_graph)
    monkeypatch.setattr(wa, "WABA_ID", "1805330937165591")
    monkeypatch.setattr(wa, "ACCESS_TOKEN", "EAAtest")
    corre(wa.list_templates())
    corre(wa.list_templates())
    assert llamadas["n"] == 1
    corre(wa.list_templates(force=True))
    assert llamadas["n"] == 2, "el panel puede pedir el listado fresco"
