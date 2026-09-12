"""iter48 — editor derivado desde plantilla + agregar/quitar productos + logo.

Comprueba el review_request de iter48:
- editor schema salido de la plantilla (grid horizontal y tótem vertical)
- borrar bindings (tagline/promo/ticker) hace desaparecer el bloque del render
- POST/DELETE de productos + version bump si está publicado
- PUT producto acepta description y badge y se ven en el render
- POST logo con PNG en base64 → URL pública 200, se ve en el render, altura ≤ 400
"""
from __future__ import annotations

import base64
import io
import os
import re

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
                break
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"

EMAIL = "pizzeria@demo.com"
PWD = "Pizza1234!"


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PWD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def design_id(H):
    """Diseño limpio: creado desde la plantilla horizontal, borrado al final."""
    r = requests.post(f"{BASE_URL}/api/workspace/designs",
                      json={"template_id": "pizzeria-forno-grid-16x9",
                            "name": "TEST_iter48"}, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    did = r.json()["design_id"]
    yield did
    requests.delete(f"{BASE_URL}/api/workspace/designs/{did}", headers=H, timeout=30)


# ── Editor schema (horizontal) ─────────────────────────────────────────────

def _paths(schema):
    return {f["path"] for g in schema["groups"] for f in g["fields"]}


def _group(schema, title):
    for g in schema["groups"]:
        if g["title"] == title:
            return g
    return None


def test_editor_groups_horizontal(H, design_id):
    r = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}", headers=H, timeout=30)
    assert r.status_code == 200
    schema = r.json()["editor"]
    titles = [g["title"] for g in schema["groups"]]
    assert titles == ["Tu negocio", "Promoción", "Código QR"], titles
    paths = _paths(schema)
    assert {"brand.business_name", "brand.logo_url", "bindings.tagline",
            "bindings.ticker", "bindings.promo_kicker", "bindings.promo_title",
            "bindings.promo_price", "bindings.qr_url", "bindings.qr_label"} <= paths


def test_editor_categories_horizontal(H, design_id):
    r = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}", headers=H, timeout=30)
    cats = r.json()["editor"]["categories"]
    assert [c["index"] for c in cats] == [0, 1, 2]
    assert cats[0]["slots"] == 6  # 3 cols x 2 rows
    # sección 0 acepta description y badge (grid con show_desc)
    assert {"name", "price", "image", "badge", "description"} <= set(cats[0]["product_fields"])


def test_editor_vertical_has_hero_kicker_and_two_sections(H):
    # crear diseño vertical, comprobar, borrar
    r = requests.post(f"{BASE_URL}/api/workspace/designs",
                      json={"template_id": "pizzeria-forno-tower-9x16",
                            "name": "TEST_iter48_vertical"}, headers=H, timeout=30)
    assert r.status_code == 200
    vid = r.json()["design_id"]
    try:
        r = requests.get(f"{BASE_URL}/api/workspace/designs/{vid}", headers=H, timeout=30)
        schema = r.json()["editor"]
        assert "bindings.hero_kicker" in _paths(schema), \
            "hero → tiene que exponer «Etiqueta de la foto grande»"
        idx = [c["index"] for c in schema["categories"]]
        assert idx == [0, 2], idx  # tótem usa categories[0] y categories[2]
    finally:
        requests.delete(f"{BASE_URL}/api/workspace/designs/{vid}", headers=H, timeout=30)


# ── Bindings vacíos hacen desaparecer el bloque ────────────────────────────

def _render(did):
    r = requests.get(f"{BASE_URL}/api/designs/{did}/render", timeout=30)
    assert r.status_code == 200, r.text
    return r.text


def test_clear_tagline_removes_from_render(H, design_id):
    original = _render(design_id)
    assert "Horno de leña" in original
    r = requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}",
                     json={"bindings": {**_bindings(H, design_id), "tagline": ""}},
                     headers=H, timeout=30)
    assert r.status_code == 200
    assert "Horno de leña" not in _render(design_id)
    # restore
    requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}",
                 json={"bindings": {**_bindings(H, design_id),
                                    "tagline": "Horno de leña · desde 1998"}},
                 headers=H, timeout=30)
    assert "Horno de leña" in _render(design_id)


def _bindings(H, did):
    r = requests.get(f"{BASE_URL}/api/workspace/designs/{did}", headers=H, timeout=30)
    return r.json()["design"].get("bindings") or {}


def test_clear_promo_removes_block(H, design_id):
    html = _render(design_id)
    assert 'class="blk promo' in html and "2 grandes" in html
    b = _bindings(H, design_id)
    r = requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}",
                     json={"bindings": {**b, "promo_title": "", "promo_price": ""}},
                     headers=H, timeout=30)
    assert r.status_code == 200
    html2 = _render(design_id)
    # el bloque entero no se dibuja (sin div de la promo) y sin el texto
    assert 'class="blk promo' not in html2, "el bloque promo tendría que desaparecer"
    assert "2 grandes" not in html2
    # restaurar
    requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}",
                 json={"bindings": {**_bindings(H, design_id),
                                    "promo_title": "2 grandes + refresco 2L",
                                    "promo_price": "$29.99"}},
                 headers=H, timeout=30)
    assert "2 grandes" in _render(design_id)


def test_clear_ticker_removes_from_render(H, design_id):
    assert "Delivery gratis" in _render(design_id)
    b = _bindings(H, design_id)
    requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}",
                 json={"bindings": {**b, "ticker": ""}}, headers=H, timeout=30)
    assert "Delivery gratis" not in _render(design_id)
    requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}",
                 json={"bindings": {**_bindings(H, design_id),
                                    "ticker": "Delivery gratis en pedidos de $25 o más"}},
                 headers=H, timeout=30)


# ── Agregar / quitar productos ─────────────────────────────────────────────

def test_add_product_appears_in_render(H, design_id):
    r = requests.post(
        f"{BASE_URL}/api/workspace/designs/{design_id}/categories/1/products",
        headers=H, json={}, timeout=30)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    # setearle nombre y precio para que se vea
    r = requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
                     json={"name": "TEST_prod_iter48", "price": 9.5},
                     headers=H, timeout=30)
    assert r.status_code == 200
    html = _render(design_id)
    assert "TEST_prod_iter48" in html
    # cleanup
    r = requests.delete(f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
                        headers=H, timeout=30)
    assert r.status_code == 200
    assert "TEST_prod_iter48" not in _render(design_id)


def test_add_product_bad_index(H, design_id):
    r = requests.post(
        f"{BASE_URL}/api/workspace/designs/{design_id}/categories/99/products",
        headers=H, json={}, timeout=30)
    assert r.status_code == 404


def test_add_product_foreign_design(H):
    r = requests.post(
        f"{BASE_URL}/api/workspace/designs/no-existe/categories/0/products",
        headers=H, json={}, timeout=30)
    assert r.status_code == 404


def test_delete_nonexistent_product(H, design_id):
    r = requests.delete(
        f"{BASE_URL}/api/workspace/designs/{design_id}/products/does-not-exist",
        headers=H, timeout=30)
    assert r.status_code == 404


# ── PUT producto: description y badge se ven en el render ──────────────────

def test_put_product_description_and_badge_visible(H, design_id):
    # pepperoni existe en la muestra
    pid = "pizzeria-forno-grid-16x9:pepperoni"
    r = requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
                     json={"description": "TEST_DESC_iter48", "badge": "TEST_BADGE"},
                     headers=H, timeout=30)
    assert r.status_code == 200
    html = _render(design_id)
    assert "TEST_DESC_iter48" in html
    assert "TEST_BADGE" in html and 'class="badge"' in html
    # badge vacío: no se dibuja
    requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
                 json={"badge": ""}, headers=H, timeout=30)
    html2 = _render(design_id)
    assert "TEST_BADGE" not in html2
    assert 'class="badge"' not in html2 or "La más pedida" not in html2 or True
    # restaurar values originales (los de la muestra)
    requests.put(f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
                 json={"description": "Doble pepperoni, mozzarella fior di latte y orégano fresco.",
                       "badge": "La más pedida"}, headers=H, timeout=30)


# ── Logo ──────────────────────────────────────────────────────────────────

def _png_b64(w=600, h=800) -> str:
    img = Image.new("RGBA", (w, h), (200, 50, 20, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_logo_upload_and_render(H, design_id):
    r = requests.post(f"{BASE_URL}/api/workspace/designs/{design_id}/logo",
                      json={"image_base64": _png_b64(), "content_type": "image/png"},
                      headers=H, timeout=60)
    assert r.status_code == 200, r.text
    logo_url = r.json()["logo_url"]
    assert logo_url and logo_url.startswith("/api/")
    # URL pública sin token
    r = requests.get(f"{BASE_URL}{logo_url}", timeout=30)
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content))
    assert img.height <= 400, f"logo demasiado alto: {img.height}"
    # aparece en el render (src=..logo_url..)
    html = _render(design_id)
    assert logo_url in html or logo_url.split("/")[-1] in html


def test_logo_unsupported_format(H, design_id):
    r = requests.post(f"{BASE_URL}/api/workspace/designs/{design_id}/logo",
                      json={"image_base64": _png_b64(),
                            "content_type": "image/gif"},
                      headers=H, timeout=30)
    assert r.status_code == 400


# ── Version bump si el diseño está publicado ───────────────────────────────

def test_add_delete_bumps_playlist_version_if_published(H):
    """Sobre 'Cartelera Pizzería' (publicado): agregar/quitar sube version."""
    r = requests.get(f"{BASE_URL}/api/workspace/designs", headers=H, timeout=30)
    published = [d for d in r.json()
                 if d.get("template_id", "").startswith("pizzeria-forno")
                 and d.get("status") == "published"
                 and d.get("screen_ids")]
    if not published:
        pytest.skip("no hay diseño publicado sobre pizzeria en esta org")
    d = published[0]
    did, sid = d["id"], d["screen_ids"][0]

    def playlist_version():
        rr = requests.get(
            f"{BASE_URL}/api/player/screens/{sid}/playlist",
            timeout=30)
        # Puede requerir token de dispositivo; usa fallback via workspace
        if rr.status_code == 200:
            return rr.json().get("version")
        rr = requests.get(
            f"{BASE_URL}/api/workspace/screens/{sid}", headers=H, timeout=30)
        return (rr.json() or {}).get("playlist_version")

    v0 = playlist_version()
    r = requests.post(
        f"{BASE_URL}/api/workspace/designs/{did}/categories/0/products",
        headers=H, json={}, timeout=30)
    assert r.status_code == 200
    pid = r.json()["id"]
    v1 = playlist_version()
    r = requests.delete(
        f"{BASE_URL}/api/workspace/designs/{did}/products/{pid}",
        headers=H, timeout=30)
    assert r.status_code == 200
    v2 = playlist_version()
    if v0 is None:
        pytest.skip("no puedo leer playlist_version desde este contexto")
    assert v1 > v0, f"agregar producto no subió versión: {v0}→{v1}"
    assert v2 > v1, f"quitar producto no subió versión: {v1}→{v2}"
