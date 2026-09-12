"""Iter 51 — Ofertas flash + rubros Gomería y Farmacia.

Contratos que se validan aquí:
1. Los 8 IDs nuevos (offers-flash-*, tires-*, pharmacy-*) responden 200 en
   /api/signage-templates/{id}/preview y NUNCA co-existen class="disc" +
   class="feat-price" en el mismo HTML (ese era el bug del precio tapando el
   nombre).
2. En pharmacy-a y pharmacy-c NO hay class="card-mono" como atributo (todas
   las tarjetas tienen foto real). La regla del monograma queda como CSS
   fallback pero sin uso.
3. Catálogo autenticado devuelve 13 rubros con offers=4, tires=2, pharmacy=2
   y 39 plantillas visibles (ninguna concept-*).
4. Ciclo completo con offers-flash-precio: crear diseño, render 200 con
   nombre y precio de muestra, borrar.

    cd /app/backend && python -m pytest tests/test_iter51_offers_flash_and_new_industries.py -v
"""
import os
import re

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                      "https://sprint1-signage.preview.emergentagent.com").rstrip("/")

PIZZA_EMAIL = "pizzeria@demo.com"
PIZZA_PASS = "Pizza1234!"

NEW_IDS = [
    "offers-flash-cine", "offers-flash-claro",
    "offers-flash-totem", "offers-flash-precio",
    "tires-a", "tires-b",
    "pharmacy-a", "pharmacy-c",
]


@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": PIZZA_EMAIL, "password": PIZZA_PASS}, timeout=20)
    if r.status_code == 429:
        pytest.skip("Rate limited. Skip auth-dependent tests.")
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, r.json()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ─── Preview público de los 8 IDs nuevos ──────────────────────────────
class TestPreviewNewIds:
    @pytest.mark.parametrize("tpl_id", NEW_IDS)
    def test_preview_returns_200(self, tpl_id):
        r = requests.get(f"{BASE}/api/signage-templates/{tpl_id}/preview", timeout=20)
        assert r.status_code == 200, r.text[:200]
        assert "text/html" in r.headers.get("content-type", "")
        assert len(r.text) > 4000, f"HTML muy corto: {len(r.text)} bytes"

    @pytest.mark.parametrize("tpl_id", NEW_IDS)
    def test_price_disc_and_inline_never_together(self, tpl_id):
        """Regla: en el mismo tablero, el precio va en disco o inline — nunca los dos."""
        r = requests.get(f"{BASE}/api/signage-templates/{tpl_id}/preview", timeout=20)
        html = r.text
        # buscamos atributos de clase reales, no la definición de CSS
        has_disc = bool(re.search(r'class="[^"]*\bdisc\b[^"]*"', html))
        has_feat = bool(re.search(r'class="[^"]*\bfeat-price\b[^"]*"', html))
        assert not (has_disc and has_feat), (
            f"{tpl_id}: precio duplicado — disc={has_disc} feat_price={has_feat}"
        )


# ─── Farmacia: fotos reales, sin card-mono como atributo ──────────────
class TestPharmacyPhotos:
    @pytest.mark.parametrize("tpl_id", ["pharmacy-a", "pharmacy-c"])
    def test_photos_are_real_imgs(self, tpl_id):
        r = requests.get(f"{BASE}/api/signage-templates/{tpl_id}/preview", timeout=20)
        html = r.text
        imgs = re.findall(r'<img[^>]*src="([^"]+)"', html)
        # muestras: mascarillas, alcohol, curitas al menos
        needed = ["mascarillas", "alcohol", "curitas"]
        for n in needed:
            assert any(n in u for u in imgs), f"{tpl_id}: falta foto de {n}. imgs={imgs}"

    @pytest.mark.parametrize("tpl_id", ["pharmacy-a", "pharmacy-c"])
    def test_no_card_mono_attribute(self, tpl_id):
        """La CSS puede definir .card-mono como fallback, pero ningún elemento debe usarla."""
        r = requests.get(f"{BASE}/api/signage-templates/{tpl_id}/preview", timeout=20)
        html = r.text
        uses = re.findall(r'class="card-mono[^"]*"', html)
        assert not uses, f"{tpl_id}: card-mono usado como atributo: {uses}"


# ─── Catálogo autenticado ─────────────────────────────────────────────
class TestCatalog:
    def test_industries_count(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-industries", timeout=15)
        assert r.status_code == 200, r.text[:200]
        rows = r.json()
        assert len(rows) == 13, f"Esperaba 13 rubros, obtuve {len(rows)}: {[x['industry'] for x in rows]}"
        by_ind = {row["industry"]: row for row in rows}
        assert by_ind.get("offers", {}).get("templates") == 4, by_ind.get("offers")
        assert by_ind.get("tires", {}).get("templates") == 2, by_ind.get("tires")
        assert by_ind.get("pharmacy", {}).get("templates") == 2, by_ind.get("pharmacy")

    def test_templates_count_and_no_concept(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 39, f"Esperaba 39 plantillas visibles, obtuve {len(rows)}"
        for row in rows:
            assert not str(row["id"]).startswith("concept-"), f"leaked concept: {row['id']}"
        ids = {row["id"] for row in rows}
        for new_id in NEW_IDS:
            assert new_id in ids, f"{new_id} no está en el catálogo"


# ─── Ciclo completo con offers-flash-precio ───────────────────────────
class TestOfferFlashLifecycle:
    def test_create_render_delete(self, owner):
        # 1. crear diseño
        r = owner.post(f"{BASE}/api/workspace/designs",
                       json={"template_id": "offers-flash-precio"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        did = r.json().get("design_id")
        assert did

        try:
            # 2. render público 200 con nombre y precio
            rr = requests.get(f"{BASE}/api/designs/{did}/render", timeout=20)
            assert rr.status_code == 200, rr.text[:200]
            html = rr.text
            assert len(html) > 4000, f"HTML muy corto: {len(html)}"

            # el diseño arrastra el sample; verificamos que al menos un producto y un precio salgan
            # sample de offers viene con $ y nombres
            assert "$" in html, "El render no contiene ningún precio"
            # el nombre del primer producto de la muestra debería aparecer
            payload = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15).json()
            products = payload["design"].get("products") or {}
            assert products, "El diseño no trae productos"
            first = next(iter(products.values()))
            assert first["name"] in html, f"Falta nombre {first['name']!r} en el render"
        finally:
            # 3. borrar (idempotencia + no dejar basura)
            d = owner.delete(f"{BASE}/api/workspace/designs/{did}", timeout=15)
            assert d.status_code == 200, d.text[:200]
            g = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
            assert g.status_code == 404
