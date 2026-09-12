"""Iter47 — Vista previa viva (POST /preview) y foto propia (POST /photo).

Cubre P1 del review_request:
- POST /api/workspace/designs/{id}/preview: HTML 200 con los valores del
  borrador; NO modifica la base ni sube playlist_version; brand.business_name
  aparece en el HTML; diseño ajeno -> 404; sin token -> 401/403.
- POST /api/workspace/designs/{id}/products/{pid}/photo: JPEG/PNG/WebP OK;
  la URL responde 200 sin token; imagen recortada a 4:3 y ancho <=900 px;
  image/gif -> 400; base64 corrupto -> 400; diseño ajeno -> 404; si el diseño
  está publicado bumpea playlist_version y cambia el checksum.
"""
from __future__ import annotations

import base64
import io
import os
import uuid

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
OTHER = ("testws@test.com", "Test1234!")


# ── helpers ────────────────────────────────────────────────────────────────
def _login(email: str, password: str) -> str:
    resp = requests.post(f"{BASE_URL}/api/auth/login",
                         json={"email": email, "password": password}, timeout=15)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _jpeg(w: int = 2000, h: int = 1500, color=(220, 60, 40)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _png(w: int = 800, h: int = 600) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (20, 200, 80)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _webp(w: int = 800, h: int = 600) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 100, 220)).save(buf, format="WEBP", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _gif(w: int = 200, h: int = 200) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 10, 10)).save(buf, format="GIF")
    return base64.b64encode(buf.getvalue()).decode()


# ── fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def owner_token() -> str:
    return _login(*OWNER)


@pytest.fixture(scope="module")
def other_token() -> str:
    return _login(*OTHER)


@pytest.fixture(scope="module")
def pizzeria_design(owner_token: str):
    """Cartelera Pizzería (publicada en Vitrina)."""
    resp = requests.get(f"{BASE_URL}/api/workspace/designs",
                        headers=_headers(owner_token), timeout=15)
    assert resp.status_code == 200, resp.text
    rows = [d for d in resp.json() if d.get("name") == "Cartelera Pizzería"]
    assert rows, "El diseño semilla 'Cartelera Pizzería' no está presente"
    design_id = rows[0]["id"]
    full = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}",
                        headers=_headers(owner_token), timeout=15).json()
    return {"id": design_id, "full": full}


@pytest.fixture(scope="module")
def sample_product(pizzeria_design):
    products = pizzeria_design["full"]["design"].get("products") or {}
    assert products, "El diseño no tiene productos"
    # Elegimos uno estable para poder guardar/restaurar
    pid, product = next(iter(products.items()))
    return {"id": pid, "product": product}


@pytest.fixture(scope="module")
def screen_id(owner_token: str, pizzeria_design):
    return (pizzeria_design["full"]["design"].get("screen_ids") or [None])[0]


# ── PREVIEW ────────────────────────────────────────────────────────────────
class TestPreviewLive:
    """POST /workspace/designs/{id}/preview — no toca la base ni el playlist."""

    def test_preview_reflects_draft_without_persisting(
            self, owner_token, pizzeria_design, sample_product, screen_id):
        design_id = pizzeria_design["id"]
        pid = sample_product["id"]
        original_price = sample_product["product"].get("price")
        original_variants = sample_product["product"].get("variants")

        # Snapshot antes: producto + playlist_version del reproductor
        before = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}",
                              headers=_headers(owner_token), timeout=15).json()
        before_product = before["design"]["products"][pid]

        before_version = None
        if screen_id:
            r = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=15)
            if r.status_code == 200:
                before_version = r.json().get("playlist_version")

        marker_name = f"TEST_PREVIEW_{uuid.uuid4().hex[:6]}"
        marker_price = "77.77"
        product_patch: dict = {"name": marker_name}
        if original_variants:
            # respetamos la forma con variantes
            product_patch["variants"] = [{**v, "price": marker_price}
                                         for v in original_variants]
        else:
            product_patch["price"] = marker_price
        patch = {"products": {pid: product_patch}}
        preview = requests.post(f"{BASE_URL}/api/workspace/designs/{design_id}/preview",
                                json=patch, headers=_headers(owner_token), timeout=15)
        assert preview.status_code == 200, preview.text
        assert "text/html" in preview.headers.get("content-type", "").lower()
        assert marker_name in preview.text
        assert marker_price in preview.text or marker_price.replace(".", ",") in preview.text

        # NO se debe haber guardado nada
        after = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}",
                             headers=_headers(owner_token), timeout=15).json()
        after_product = after["design"]["products"][pid]
        assert after_product.get("name") == before_product.get("name")
        assert after_product.get("price") == before_product.get("price")
        assert after_product.get("price") == original_price
        assert after_product.get("variants") == original_variants

        # Y el playlist NO subió versión
        if screen_id and before_version is not None:
            r2 = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=15)
            assert r2.status_code == 200
            assert r2.json().get("playlist_version") == before_version

    def test_preview_reflects_brand_name(self, owner_token, pizzeria_design):
        marker = f"TEST_BRAND_{uuid.uuid4().hex[:6]}"
        preview = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}/preview",
            json={"brand": {"business_name": marker}},
            headers=_headers(owner_token), timeout=15)
        assert preview.status_code == 200
        assert marker in preview.text

    def test_preview_returns_404_for_foreign_design(self, other_token, pizzeria_design):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}/preview",
            json={}, headers=_headers(other_token), timeout=15)
        assert resp.status_code == 404

    def test_preview_requires_token(self, pizzeria_design):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}/preview",
            json={}, timeout=15)
        assert resp.status_code in (401, 403)


# ── PHOTO UPLOAD ───────────────────────────────────────────────────────────
class TestPhotoUpload:
    """POST /workspace/designs/{id}/products/{pid}/photo."""

    def test_jpeg_uploads_and_url_public(
            self, owner_token, pizzeria_design, sample_product):
        design_id = pizzeria_design["id"]
        pid = sample_product["id"]
        original_url = sample_product["product"].get("image_url")

        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}/photo",
            json={"image_base64": _jpeg(2000, 1500), "content_type": "image/jpeg"},
            headers=_headers(owner_token), timeout=45)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("image_url"), "image_url ausente"
        new_url = data["image_url"]
        assert new_url != original_url

        # URL pública (sin token — la usa el WebView del TV)
        public = requests.get(f"{BASE_URL}{new_url}", timeout=15)
        assert public.status_code == 200, public.text
        assert "image" in public.headers.get("content-type", "").lower()

        # 4:3 y ancho <=900
        img = Image.open(io.BytesIO(public.content))
        assert img.width <= 900, f"ancho {img.width} > 900"
        ratio = img.width / img.height
        assert abs(ratio - 4 / 3) < 0.02, f"aspecto {ratio:.3f} no es 4:3"

        # dejar cargada foto de muestra al final: se restaura en test_restore
        pytest.upload_new_url = new_url  # type: ignore[attr-defined]

    def test_png_accepted(self, owner_token, pizzeria_design, sample_product):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}/photo",
            json={"image_base64": _png(), "content_type": "image/png"},
            headers=_headers(owner_token), timeout=45)
        assert resp.status_code == 200, resp.text

    def test_webp_accepted(self, owner_token, pizzeria_design, sample_product):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}/photo",
            json={"image_base64": _webp(), "content_type": "image/webp"},
            headers=_headers(owner_token), timeout=45)
        assert resp.status_code == 200, resp.text

    def test_gif_rejected(self, owner_token, pizzeria_design, sample_product):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}/photo",
            json={"image_base64": _gif(), "content_type": "image/gif"},
            headers=_headers(owner_token), timeout=15)
        assert resp.status_code == 400, resp.text

    def test_corrupt_base64_rejected(self, owner_token, pizzeria_design, sample_product):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}/photo",
            json={"image_base64": "###not-base64###",
                  "content_type": "image/jpeg"},
            headers=_headers(owner_token), timeout=15)
        assert resp.status_code == 400, resp.text

    def test_foreign_design_returns_404(self, other_token, pizzeria_design, sample_product):
        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}/photo",
            json={"image_base64": _jpeg(400, 300), "content_type": "image/jpeg"},
            headers=_headers(other_token), timeout=15)
        assert resp.status_code == 404, resp.text

    def test_photo_bumps_playlist_version_and_checksum(
            self, owner_token, pizzeria_design, sample_product, screen_id):
        if not screen_id:
            pytest.skip("Diseño no publicado — nada que bumpear")
        before = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=15)
        assert before.status_code == 200, before.text
        before_version = before.json().get("playlist_version")
        before_items = before.json().get("items") or []
        before_ck = next((i.get("checksum") for i in before_items
                          if str(i.get("media_id", "")).startswith("design:")), None)

        resp = requests.post(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}/photo",
            json={"image_base64": _jpeg(1600, 1200, color=(20, 20, 20)),
                  "content_type": "image/jpeg"},
            headers=_headers(owner_token), timeout=45)
        assert resp.status_code == 200, resp.text

        after = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=15)
        assert after.status_code == 200
        after_version = after.json().get("playlist_version")
        after_items = after.json().get("items") or []
        after_ck = next((i.get("checksum") for i in after_items
                         if str(i.get("media_id", "")).startswith("design:")), None)

        assert after_version and before_version and after_version > before_version, \
            f"version no subió: {before_version} -> {after_version}"
        assert before_ck and after_ck and before_ck != after_ck, \
            "checksum del ítem no cambió"

    def test_restore_sample_image(
            self, owner_token, pizzeria_design, sample_product):
        """Deja el producto con la foto de muestra original (limpieza)."""
        original_url = sample_product["product"].get("image_url")
        if not original_url:
            pytest.skip("Producto sin image_url original")
        r = requests.put(
            f"{BASE_URL}/api/workspace/designs/{pizzeria_design['id']}"
            f"/products/{sample_product['id']}",
            json={"image_url": original_url},
            headers=_headers(owner_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("image_url") == original_url
