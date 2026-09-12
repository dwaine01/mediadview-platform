"""iter50 — Rediseño masivo de plantillas (Vitrina/Cine/Sereno/Tótem).

Cubre lo pedido en el review_request:
  * Catálogo de plantillas: 31 visibles, 0 con id concept-*
  * Industrias: 10 rubros
  * Preview HTML > 4000 bytes para las 31; markers de familias A/B/V
  * Plantillas viejas ocultas pero render de diseños publicados sigue vivo
  * Crear+leer+render+borrar diseños para 4 plantillas nuevas (a, b, c, v)
  * Editar producto y ver el cambio en el render + POST preview funciona
"""
import base64
import os
import re

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                     "https://sprint1-signage.preview.emergentagent.com").rstrip("/")
PIZZA = ("pizzeria@demo.com", "Pizza1234!")

TEMPLATES_TO_CREATE = [
    "pizzeria-a",
    "restaurant-b",
    "latin-venezuela-c",
    "mexican-v",
]


# ── login + sesión con el dueño ─────────────────────────────────────────
@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": PIZZA[0], "password": PIZZA[1]}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── CATÁLOGO ────────────────────────────────────────────────────────────
class TestCatalog:
    def test_31_templates_none_concept(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 31, f"Se esperaban 31 plantillas, hay {len(rows)}"
        for row in rows:
            assert not row["id"].startswith("concept-"), \
                f"El concepto {row['id']} no debería salir en el catálogo"

    def test_10_industries(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-industries", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 10, f"Se esperaban 10 rubros, hay {len(rows)}"
        # cada rubro tiene al menos 1 plantilla
        for row in rows:
            assert row["templates"] >= 1, row

    def test_new_and_hidden_templates_ids(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates", timeout=15)
        ids = {row["id"] for row in r.json()}
        for tid in TEMPLATES_TO_CREATE:
            assert tid in ids, f"Falta la nueva plantilla {tid}"
        # las viejas no deben aparecer en catálogo
        for hidden in ("pizzeria-forno-grid-16x9", "pizzeria-forno-tower-9x16"):
            assert hidden not in ids, f"{hidden} debería estar oculta"


# ── PREVIEW HTML ───────────────────────────────────────────────────────
class TestPreview:
    def test_all_previews_have_body(self, owner):
        rows = owner.get(f"{BASE}/api/workspace/signage-templates", timeout=15).json()
        undersize = []
        for row in rows:
            r = requests.get(f"{BASE}/api/signage-templates/{row['id']}/preview", timeout=25)
            assert r.status_code == 200, f"{row['id']} -> {r.status_code}"
            if len(r.text) <= 4000:
                undersize.append((row["id"], len(r.text)))
        assert not undersize, f"Previews < 4000 bytes: {undersize}"

    def test_family_a_markers(self):
        r = requests.get(f"{BASE}/api/signage-templates/pizzeria-a/preview", timeout=20)
        assert r.status_code == 200
        html = r.text
        assert 'class="blk feat' in html, "familia A: falta bloque feature"
        assert 'card-bare' in html, "familia A: falta tarjeta bare"
        assert 'disc' in html, "familia A: falta el disco de precio"

    def test_family_b_markers(self):
        r = requests.get(f"{BASE}/api/signage-templates/restaurant-b/preview", timeout=20)
        assert r.status_code == 200
        assert 'class="blk back back-left' in r.text, \
            "familia B: falta backdrop lateral"

    def test_family_v_is_1080x1920(self):
        r = requests.get(f"{BASE}/api/signage-templates/mexican-v/preview", timeout=20)
        assert r.status_code == 200
        html = r.text
        # Ver ancho/alto en la meta o en el CSS/viewport del canvas
        # Aceptamos varias formas de expresión
        w_ok = "1080" in html
        h_ok = "1920" in html
        assert w_ok and h_ok, f"familia V debe ser 1080x1920 (w={w_ok}, h={h_ok})"


# ── DISEÑOS PUBLICADOS SIGUEN VIVOS ─────────────────────────────────────
class TestExistingDesignsStillRender:
    """Un diseño ya creado sobre una plantilla ahora oculta no debe romperse."""

    def test_existing_pizzeria_design_still_renders(self, owner):
        rows = owner.get(f"{BASE}/api/workspace/designs", timeout=15).json()
        # Busca cartelera pizza publicada sobre la vieja plantilla
        target = None
        for d in rows:
            if d.get("template_id") in (
                "pizzeria-forno-grid-16x9",
                "pizzeria-forno-tower-9x16",
            ):
                target = d
                break
        if not target:
            pytest.skip("No existing design over hidden template in this org")
        did = target["id"]
        # GET workspace design → 200 y trae editor/template
        r = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r.status_code == 200, r.text[:300]
        payload = r.json()
        assert payload["template"]["id"] == target["template_id"]
        # Render público 200 + HTML no vacío
        r2 = requests.get(f"{BASE}/api/designs/{did}/render", timeout=25)
        assert r2.status_code == 200, r2.text[:200]
        assert len(r2.text) > 4000, len(r2.text)


# ── CREAR + LEER + RENDER + BORRAR ──────────────────────────────────────
class TestNewFamilyLifecycle:
    created = {}  # tid -> design_id

    @pytest.mark.parametrize("tid", TEMPLATES_TO_CREATE)
    def test_create_and_render(self, owner, tid):
        r = owner.post(f"{BASE}/api/workspace/designs",
                       json={"template_id": tid}, timeout=25)
        assert r.status_code == 200, f"{tid} -> {r.status_code} {r.text[:200]}"
        did = r.json()["design_id"]
        TestNewFamilyLifecycle.created[tid] = did

        r2 = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r2.status_code == 200
        payload = r2.json()
        design = payload["design"]
        editor = payload.get("editor") or {}
        groups = editor.get("groups") or []
        cats = editor.get("categories") or []
        assert groups, f"{tid}: no groups en editor"
        assert cats, f"{tid}: no categories en editor"

        # Reglas por familia
        if tid.endswith("-a") or tid.endswith("-v"):
            # familia A/V: bloque hero => alguna categoría con hero_kicker/hero_title
            # (según spec del review_request: «Etiqueta de la foto grande»)
            has_hero_field = False
            for g in groups:
                for f in g.get("fields", []):
                    if "hero" in f.get("path", ""):
                        has_hero_field = True
            assert has_hero_field, \
                f"{tid}: familia A/V debe tener campo hero (etiqueta de foto grande)"

        if tid.endswith("-c"):
            paths = {f["path"] for g in groups for f in g.get("fields", [])}
            assert "bindings.ticker" in paths, \
                f"{tid}: familia C debe tener 'Mensaje en movimiento' (ticker)"

        # Productos de muestra con image_url que responde 200
        products = design.get("products") or {}
        assert products, f"{tid}: sin productos de muestra"
        checked = 0
        for _pid, p in products.items():
            url = p.get("image_url") or ""
            if not url:
                continue
            resp = requests.get(f"{BASE}{url}" if url.startswith("/") else url,
                                timeout=15)
            assert resp.status_code == 200, f"{tid} image {url} -> {resp.status_code}"
            checked += 1
            if checked >= 3:
                break
        assert checked >= 1, f"{tid}: ningún producto con image_url"

        # Render público 200 y con contenido
        r3 = requests.get(f"{BASE}/api/designs/{did}/render", timeout=25)
        assert r3.status_code == 200
        assert len(r3.text) > 4000

    def test_edit_product_reaches_render_and_preview(self, owner):
        # Elegimos el diseño A (más simple con product_grid)
        tid = "pizzeria-a"
        did = TestNewFamilyLifecycle.created.get(tid)
        assert did, "El test de creación tiene que haber corrido antes"

        payload = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15).json()
        products = payload["design"]["products"]
        pid = next(iter(products.keys()))

        new_name = "TEST_iter50_pizza"
        r = owner.put(f"{BASE}/api/workspace/designs/{did}/products/{pid}",
                      json={"name": new_name, "price": 88.88}, timeout=15)
        assert r.status_code == 200, r.text[:200]

        r2 = requests.get(f"{BASE}/api/designs/{did}/render", timeout=20)
        assert r2.status_code == 200
        assert new_name in r2.text, "El cambio de nombre no llegó al render"

        # POST /preview (borrador) sigue funcionando con plantilla nueva
        r3 = owner.post(f"{BASE}/api/workspace/designs/{did}/preview",
                        json={"design": payload["design"]}, timeout=25)
        # el endpoint puede devolver 200 con HTML directo o JSON con html
        assert r3.status_code == 200, r3.text[:300]
        ct = r3.headers.get("content-type", "")
        body = r3.text if "text/html" in ct else (r3.json().get("html") or "")
        assert body and len(body) > 1000, \
            f"preview de borrador vacío ({len(body)} bytes)"

    def test_cleanup(self, owner):
        for tid, did in list(TestNewFamilyLifecycle.created.items()):
            r = owner.delete(f"{BASE}/api/workspace/designs/{did}", timeout=15)
            assert r.status_code == 200, f"{tid} delete -> {r.status_code}"
            r2 = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
            assert r2.status_code == 404
