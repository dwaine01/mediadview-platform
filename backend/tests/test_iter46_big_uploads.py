"""iter46 — el 502 al subir un menú real.

El plan del servicio tiene 512 MB para 2 workers de uvicorn. Un JPG de cámara
de 40 megapixeles, decodificado a tamaño completo, se lleva más de 300 MB: el
worker muere, el proxy devuelve 502 y el usuario ve «No pudimos procesar tu
diseño. Request failed with status code 502».

Estos tests suben archivos grandes de verdad y exigen que el backend los
procese sin explotar y sin quedarse con imágenes gigantes en memoria.
"""
import base64
import io
import os
import resource
import sys
import uuid

import pytest
import requests
from PIL import Image

sys.path.insert(0, "/app/backend")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def menu(headers):
    r = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                      json={"name": f"pytest big {uuid.uuid4().hex[:6]}"}, timeout=20)
    menu_id = r.json()["id"]
    yield menu_id
    requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)


def _big_jpeg(width, height):
    """Textura real: un color plano se comprime a nada y no prueba nada."""
    import numpy as np
    noise = np.random.randint(0, 255, (min(height, 400), min(width, 400), 3), dtype=np.uint8)
    tile = Image.fromarray(noise)
    canvas = Image.new("RGB", (width, height))
    for y in range(0, height, tile.height):
        for x in range(0, width, tile.width):
            canvas.paste(tile, (x, y))
    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


class TestBigFilesDoNotKillTheWorker:
    def test_a_40_megapixel_photo_is_handled_not_a_502(self, headers, menu):
        """7000x5800 ≈ 40 MP. Antes del fix esto mataba al worker."""
        data = _big_jpeg(7000, 5800)
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": base64.b64encode(data).decode(),
                                "content_type": "image/jpeg"}, timeout=300)
        # Nos importa que el proceso siga vivo y conteste algo razonable: 202 si
        # aceptó el archivo y arrancó el análisis, 413 si lo rechaza por tamaño.
        assert r.status_code in (202, 413), f"{r.status_code}: {r.text[:300]}"
        assert requests.get(f"{BASE_URL}/api/livez", timeout=10).json()["ok"] is True

    def test_the_stage_is_capped_so_the_tv_payload_stays_sane(self, headers, menu):
        from make_menu_design import build
        design = build("/tmp/menu_big.jpg", width=5200, height=2900)
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": base64.b64encode(open(design, "rb").read()).decode(),
                                "content_type": "image/jpeg"}, timeout=300)
        assert r.status_code == 202, r.text[:300]
        canvas = r.json()["canvas"]
        assert max(canvas["width"], canvas["height"]) <= 2400, canvas
        # y el aspecto del diseño original se respeta
        assert abs(canvas["width"] / canvas["height"] - 5200 / 2900) < 0.02

    def test_sampling_the_paper_colour_is_fast_enough_for_a_real_menu(self):
        """El muestreo corría en Python puro: segundos por campo, y un menú
        real tiene más de cien. Ahora es numpy."""
        from menu_canvas_routes import _sample_background

        image = Image.new("RGB", (2400, 1350), "#FDF6E3")
        started = resource.getrusage(resource.RUSAGE_SELF).ru_utime
        for index in range(160):
            _sample_background(image, 100 + index, 200, 320, 40)
        spent = resource.getrusage(resource.RUSAGE_SELF).ru_utime - started
        assert spent < 2.0, f"160 campos tardaron {spent:.1f}s de CPU"

    def test_an_image_over_the_pixel_budget_is_refused_cleanly(self, headers, menu):
        """Mejor un 413 con un mensaje claro que un worker muerto."""
        from menu_canvas_routes import MAX_UPLOAD_BYTES

        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": base64.b64encode(b"\x00" * (MAX_UPLOAD_BYTES + 1024)).decode(),
                                "content_type": "image/jpeg"}, timeout=120)
        assert r.status_code == 413, f"{r.status_code}: {r.text[:200]}"


class TestPdfRasterisation:
    def test_a_print_sized_pdf_does_not_blow_up_the_pixmap(self, headers, menu):
        """Un PDF A3 a 300 dpi con un 2x ciego daba un pixmap de 100+ MP."""
        pymupdf = pytest.importorskip("pymupdf")
        doc = pymupdf.open()
        page = doc.new_page(width=1191, height=842)  # A3 landscape en puntos
        page.insert_text((80, 120), "TRATTORIA PDF", fontsize=48)
        page.insert_text((80, 240), "Pizza Margherita", fontsize=28)
        page.insert_text((900, 240), "$12.50", fontsize=28)
        data = doc.tobytes()
        doc.close()

        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": base64.b64encode(data).decode(),
                                "content_type": "application/pdf"}, timeout=300)
        assert r.status_code == 202, r.text[:400]
        canvas = r.json()["canvas"]
        assert max(canvas["width"], canvas["height"]) <= 2400, canvas
        assert canvas["background_url"].startswith("/api/player/media/")

    def test_a_fake_pdf_is_refused_not_crashed(self, headers, menu):
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": base64.b64encode(b"%PDF-1.4 pero roto" * 40).decode(),
                                "content_type": "application/pdf"}, timeout=120)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:200]}"
        assert requests.get(f"{BASE_URL}/api/livez", timeout=10).json()["ok"] is True
