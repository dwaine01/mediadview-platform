"""iter43 — «Mi propio diseño»: el menú diseñado del cliente se vuelve editable.

El restaurante sube su JPG/PNG/PDF ya diseñado. La IA marca nombres, precios y
fotos; el dueño cambia el contenido y el diseño no se mueve. Estos tests cubren
el contrato que usa el panel y lo que termina viendo el TV.

Los tests que llaman a la IA están marcados `ai` porque pegan al modelo real y
tardan ~15 s.
"""
import base64
import io
import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))
from make_menu_design import build as build_design  # noqa: E402

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def design_b64():
    return base64.b64encode(open(build_design("/tmp/menu_design_test.jpg"), "rb").read()).decode()


@pytest.fixture
def menu(headers):
    r = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                      json={"name": f"pytest canvas {uuid.uuid4().hex[:6]}"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    menu_id = r.json()["id"]
    yield menu_id
    requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)


@pytest.fixture
def imported(headers, menu, design_b64):
    r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                      json={"file_base64": design_b64, "content_type": "image/jpeg"}, timeout=240)
    assert r.status_code == 200, r.text[:500]
    return menu, r.json()["canvas"]


def _preview_html(headers, menu_id):
    url = requests.get(f"{BASE_URL}/api/workspace/menus/{menu_id}/preview",
                       headers=headers, timeout=20).json()["url"]
    page = requests.get(f"{BASE_URL}{url}", timeout=30)
    assert page.status_code == 200, page.text[:300]
    return page.text


@pytest.mark.ai
class TestImport:
    def test_it_finds_the_names_prices_and_photos(self, imported):
        _, canvas = imported
        kinds = [f["kind"] for f in canvas["fields"]]
        assert kinds.count("name") >= 4, kinds
        assert kinds.count("price") >= 4, kinds
        assert canvas["width"] == 1600 and canvas["height"] == 900

    def test_boxes_land_on_the_design_not_in_the_void(self, imported):
        _, canvas = imported
        pizza = next(f for f in canvas["fields"] if "Pizza" in f["text"])
        # El texto se dibuja en (300, 255) con cuerpo 40 -> ancho ~316, alto ~37
        assert abs(pizza["x"] - 300) < 30, pizza
        assert abs(pizza["y"] - 263) < 30, pizza
        assert 250 < pizza["w"] < 400, pizza
        assert 20 < pizza["h"] < 60, pizza

    def test_it_recovers_the_font_size_from_the_box(self, imported):
        _, canvas = imported
        pizza = next(f for f in canvas["fields"] if "Pizza" in f["text"])
        assert 34 <= pizza["font_size"] <= 46, pizza["font_size"]

    def test_the_mask_colour_is_sampled_from_the_paper_not_guessed(self, imported):
        _, canvas = imported
        pizza = next(f for f in canvas["fields"] if "Pizza" in f["text"])
        # El fondo del diseño es #FDF6E3.
        r, g, b = (int(pizza["bg_color"][i:i + 2], 16) for i in (1, 3, 5))
        assert abs(r - 0xFD) < 12 and abs(g - 0xF6) < 12 and abs(b - 0xE3) < 14, pizza["bg_color"]

    def test_every_field_keeps_its_original_text(self, imported):
        _, canvas = imported
        for field in canvas["fields"]:
            if field["kind"] != "photo":
                assert field["original_text"] == field["text"]

    def test_it_flips_the_menu_into_canvas_mode(self, headers, imported):
        menu_id, _ = imported
        doc = requests.get(f"{BASE_URL}/api/workspace/menus/{menu_id}",
                           headers=headers, timeout=20).json()
        assert doc["layout_mode"] == "canvas"
        assert doc["canvas"]["background_url"].startswith("/api/player/media/")


class TestImportValidation:
    def test_a_garbage_file_is_rejected(self, headers, menu):
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": base64.b64encode(b"not an image at all" * 4).decode(),
                                "content_type": "image/png"}, timeout=60)
        assert r.status_code == 400, r.text[:300]

    def test_an_unsupported_type_is_rejected(self, headers, menu, design_b64):
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import", headers=headers,
                          json={"file_base64": design_b64, "content_type": "image/gif"}, timeout=60)
        assert r.status_code == 400

    def test_someone_elses_menu_is_404(self, headers, design_b64):
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{uuid.uuid4()}/canvas/import",
                          headers=headers,
                          json={"file_base64": design_b64, "content_type": "image/jpeg"}, timeout=60)
        assert r.status_code == 404

    def test_import_requires_auth(self, menu, design_b64):
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/canvas/import",
                          json={"file_base64": design_b64, "content_type": "image/jpeg"}, timeout=60)
        assert r.status_code in (401, 403)

    def test_a_menu_without_a_design_has_no_canvas(self, headers, menu):
        r = requests.get(f"{BASE_URL}/api/workspace/menus/{menu}/canvas", headers=headers, timeout=20)
        assert r.status_code == 404


@pytest.mark.ai
class TestEditing:
    def test_saving_clamps_boxes_inside_the_design(self, headers, imported):
        menu_id, canvas = imported
        fields = canvas["fields"]
        fields[0] = {**fields[0], "x": 99999, "y": -50, "w": 99999, "h": 2}
        r = requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas", headers=headers,
                         json={"fields": fields}, timeout=60)
        assert r.status_code == 200, r.text
        saved = r.json()["fields"][0]
        assert 0 <= saved["x"] <= canvas["width"]
        assert saved["y"] >= 0
        assert saved["x"] + saved["w"] <= canvas["width"]
        assert saved["h"] >= 8

    def test_an_untouched_field_is_not_painted_over(self, headers, imported):
        menu_id, _ = imported
        html = _preview_html(headers, menu_id)
        # Nada editado -> cero overlays de texto, el diseño se ve tal cual.
        assert 'class="f"' not in html
        assert "/api/player/media/" in html

    def test_an_edited_price_is_painted_over_the_old_one(self, headers, imported):
        menu_id, canvas = imported
        fields = [dict(f) for f in canvas["fields"]]
        price = next(f for f in fields if f["kind"] == "price")
        price["text"] = "$99.99"
        requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas", headers=headers,
                     json={"fields": fields}, timeout=60)
        html = _preview_html(headers, menu_id)
        assert "$99.99" in html
        assert 'class="f"' in html
        # el parche tiene el color del papel para tapar el precio impreso
        assert price["bg_color"] in html

    def test_a_replaced_photo_is_cropped_to_the_existing_hole(self, headers, imported):
        from PIL import Image
        menu_id, canvas = imported
        photo = next((f for f in canvas["fields"] if f["kind"] == "photo"), None)
        if not photo:
            pytest.skip("la IA no marcó fotos en este diseño")
        wide = Image.new("RGB", (1200, 300), "#123456")
        for x in range(0, 1200, 40):  # textura real, no un color plano
            for y in range(0, 300, 40):
                wide.putpixel((x, y), (250, 200, 30))
        buffer = io.BytesIO()
        wide.save(buffer, format="JPEG")
        r = requests.post(
            f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas/fields/{photo['id']}/photo",
            headers=headers,
            json={"image_base64": base64.b64encode(buffer.getvalue()).decode(),
                  "content_type": "image/jpeg"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["fitted_to"] == f"{photo['w']}x{photo['h']}"
        stored = requests.get(f"{BASE_URL}{r.json()['image_url']}", timeout=30)
        assert stored.status_code == 200
        got = Image.open(io.BytesIO(stored.content))
        # mismo aspecto que el recuadro, sin estirar
        assert abs(got.width / got.height - photo["w"] / photo["h"]) < 0.05

    def test_replacing_a_photo_on_a_missing_field_is_404(self, headers, imported):
        menu_id, _ = imported
        r = requests.post(
            f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas/fields/{uuid.uuid4()}/photo",
            headers=headers, json={"image_base64": base64.b64encode(b"x" * 64).decode(),
                                   "content_type": "image/jpeg"}, timeout=30)
        assert r.status_code == 404

    def test_dropping_the_design_returns_to_the_template(self, headers, imported):
        menu_id, _ = imported
        r = requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas",
                            headers=headers, timeout=20)
        assert r.status_code == 200
        doc = requests.get(f"{BASE_URL}/api/workspace/menus/{menu_id}",
                           headers=headers, timeout=20).json()
        assert doc["layout_mode"] == "template"
        assert "canvas" not in doc


@pytest.mark.ai
class TestItReachesTheTv:
    def test_publishing_a_canvas_menu_sends_the_design_to_the_screen(self, headers, imported):
        menu_id, _ = imported
        screens = requests.get(f"{BASE_URL}/api/workspace/screens", headers=headers, timeout=20).json()
        assert screens, "the demo org needs a screen"
        target = screens[0]["id"]
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/publish", headers=headers,
                          json={"screen_ids": [target]}, timeout=60)
        assert r.status_code == 200, r.text
        playlist = requests.get(f"{BASE_URL}/api/player/{target}/playlist", timeout=20).json()
        item = next((i for i in playlist["items"] if i["media_id"] == f"menu:{menu_id}"), None)
        assert item, [i["media_id"] for i in playlist["items"]]
        page = requests.get(f"{BASE_URL}{item['media_url']}", timeout=30)
        assert page.status_code == 200
        assert 'id="stage"' in page.text, "el TV no recibió el diseño propio"
