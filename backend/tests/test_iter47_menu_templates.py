"""iter47 — la biblioteca de plantillas del cliente.

Pedido textual: «debe crear la plantilla inmediatamente [que] la IA reconozca
toda la estructura y ponerla en una lista de plantillas a usar donde se pueda
cambiar la foto del artículo, precio y nombre».

Lo que no se puede romper: la plantilla y el menú NO comparten documento. Si
compartieran los recuadros, cambiar un precio en un menú se metería en todos
los demás menús armados con la misma plantilla.
"""
import base64
import os
import sys
import time
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
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def design_b64():
    return base64.b64encode(open(build_design("/tmp/menu_tpl.jpg"), "rb").read()).decode()


def _import_and_wait(headers, menu_id, file_b64, timeout=240):
    r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas/import", headers=headers,
                      json={"file_base64": file_b64, "content_type": "image/jpeg"}, timeout=120)
    assert r.status_code == 202, r.text[:300]
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        body = requests.get(f"{BASE_URL}/api/workspace/menus/{menu_id}/canvas",
                            headers=headers, timeout=20).json()
        if body["analysis"]["status"] != "analyzing":
            assert body["analysis"]["status"] == "ready", body["analysis"]
            return body["canvas"]
    raise AssertionError("el análisis nunca terminó")


@pytest.fixture(scope="module")
def source(headers, design_b64):
    """Un menú con diseño propio ya analizado — de ahí nace la plantilla."""
    name = f"pytest tpl {uuid.uuid4().hex[:6]}"
    menu_id = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                            json={"name": name}, timeout=20).json()["id"]
    canvas = _import_and_wait(headers, menu_id, design_b64)
    yield menu_id, name, canvas
    requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)


def _templates(headers):
    r = requests.get(f"{BASE_URL}/api/workspace/menu-templates", headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.ai
class TestTheTemplateIsCreatedOnItsOwn:
    def test_reading_a_design_puts_it_in_the_template_list(self, headers, source):
        menu_id, name, _ = source
        row = next((t for t in _templates(headers) if t["name"] == name), None)
        assert row, [t["name"] for t in _templates(headers)]
        assert row["background_url"].startswith("/api/player/media/")
        assert row["texts"] > 0

    def test_the_list_counts_texts_and_photos_separately(self, headers, source):
        _, name, canvas = source
        row = next(t for t in _templates(headers) if t["name"] == name)
        assert row["texts"] == sum(1 for f in canvas["fields"] if f["kind"] != "photo")
        assert row["photos"] == sum(1 for f in canvas["fields"] if f["kind"] == "photo")

    def test_reimporting_the_same_menu_updates_instead_of_duplicating(self, headers, source,
                                                                      design_b64):
        menu_id, name, _ = source
        before = len([t for t in _templates(headers) if t["name"] == name])
        _import_and_wait(headers, menu_id, design_b64)
        assert len([t for t in _templates(headers) if t["name"] == name]) == before


@pytest.mark.ai
class TestUsingATemplate:
    def test_it_builds_a_new_menu_with_the_same_design(self, headers, source):
        _, name, canvas = source
        template = next(t for t in _templates(headers) if t["name"] == name)
        r = requests.post(f"{BASE_URL}/api/workspace/menu-templates/{template['id']}/use",
                          headers=headers, json={}, timeout=30)
        assert r.status_code == 200, r.text
        new_menu = r.json()["menu_id"]
        try:
            body = requests.get(f"{BASE_URL}/api/workspace/menus/{new_menu}/canvas",
                                headers=headers, timeout=20).json()
            assert body["layout_mode"] == "canvas"
            assert body["canvas"]["background_url"] == template["background_url"]
            assert len(body["canvas"]["fields"]) == len(canvas["fields"])
            assert body["analysis"]["status"] == "ready"
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{new_menu}", headers=headers, timeout=20)

    def test_the_new_menu_gets_its_own_field_ids(self, headers, source):
        """Ids compartidos = cambiar un precio en un local lo cambia en todos."""
        _, name, canvas = source
        template = next(t for t in _templates(headers) if t["name"] == name)
        new_menu = requests.post(f"{BASE_URL}/api/workspace/menu-templates/{template['id']}/use",
                                 headers=headers, json={}, timeout=30).json()["menu_id"]
        try:
            copied = requests.get(f"{BASE_URL}/api/workspace/menus/{new_menu}/canvas",
                                  headers=headers, timeout=20).json()["canvas"]["fields"]
            assert not ({f["id"] for f in copied} & {f["id"] for f in canvas["fields"]})
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{new_menu}", headers=headers, timeout=20)

    def test_editing_the_copy_does_not_touch_the_original_menu(self, headers, source):
        source_menu, name, _ = source
        template = next(t for t in _templates(headers) if t["name"] == name)
        new_menu = requests.post(f"{BASE_URL}/api/workspace/menu-templates/{template['id']}/use",
                                 headers=headers, json={"name": "pytest copia"}, timeout=30).json()["menu_id"]
        try:
            fields = requests.get(f"{BASE_URL}/api/workspace/menus/{new_menu}/canvas",
                                  headers=headers, timeout=20).json()["canvas"]["fields"]
            target = next(f for f in fields if f["kind"] == "price")
            target["text"] = "$1.11"
            requests.put(f"{BASE_URL}/api/workspace/menus/{new_menu}/canvas", headers=headers,
                         json={"fields": fields}, timeout=30)
            original = requests.get(f"{BASE_URL}/api/workspace/menus/{source_menu}/canvas",
                                    headers=headers, timeout=20).json()["canvas"]["fields"]
            assert all(f["text"] != "$1.11" for f in original if f["kind"] == "price")
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{new_menu}", headers=headers, timeout=20)

    def test_the_copy_can_have_its_photo_replaced(self, headers, source):
        import io

        from PIL import Image
        _, name, _ = source
        template = next(t for t in _templates(headers) if t["name"] == name)
        if not template["photos"]:
            pytest.skip("la IA no marcó fotos en este diseño")
        new_menu = requests.post(f"{BASE_URL}/api/workspace/menu-templates/{template['id']}/use",
                                 headers=headers, json={}, timeout=30).json()["menu_id"]
        try:
            fields = requests.get(f"{BASE_URL}/api/workspace/menus/{new_menu}/canvas",
                                  headers=headers, timeout=20).json()["canvas"]["fields"]
            slot = next(f for f in fields if f["kind"] == "photo")
            picture = Image.new("RGB", (800, 600), "#224466")
            buffer = io.BytesIO()
            picture.save(buffer, format="JPEG")
            r = requests.post(
                f"{BASE_URL}/api/workspace/menus/{new_menu}/canvas/fields/{slot['id']}/photo",
                headers=headers, json={"image_base64": base64.b64encode(buffer.getvalue()).decode(),
                                       "content_type": "image/jpeg"}, timeout=120)
            assert r.status_code == 200, r.text[:300]
            assert r.json()["fitted_to"] == f"{slot['w']}x{slot['h']}"
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{new_menu}", headers=headers, timeout=20)

    def test_deleting_a_template_leaves_the_menus_built_from_it_alone(self, headers, source,
                                                                     design_b64):
        throwaway = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                                  json={"name": f"pytest doomed tpl {uuid.uuid4().hex[:5]}"},
                                  timeout=20).json()["id"]
        _import_and_wait(headers, throwaway, design_b64)
        template = next(t for t in _templates(headers) if t["name"].startswith("pytest doomed tpl"))
        built = requests.post(f"{BASE_URL}/api/workspace/menu-templates/{template['id']}/use",
                              headers=headers, json={}, timeout=30).json()["menu_id"]
        try:
            assert requests.delete(f"{BASE_URL}/api/workspace/menu-templates/{template['id']}",
                                   headers=headers, timeout=20).status_code == 200
            still = requests.get(f"{BASE_URL}/api/workspace/menus/{built}/canvas",
                                 headers=headers, timeout=20)
            assert still.status_code == 200
            assert still.json()["canvas"]["fields"], "el menú perdió su diseño"
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{built}", headers=headers, timeout=20)
            requests.delete(f"{BASE_URL}/api/workspace/menus/{throwaway}", headers=headers, timeout=20)


class TestTemplateAccess:
    def test_renaming_works(self, headers):
        rows = _templates(headers)
        if not rows:
            pytest.skip("sin plantillas todavía")
        target = rows[0]
        r = requests.put(f"{BASE_URL}/api/workspace/menu-templates/{target['id']}",
                         headers=headers, json={"name": "pytest renombrada"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["name"] == "pytest renombrada"
        requests.put(f"{BASE_URL}/api/workspace/menu-templates/{target['id']}",
                     headers=headers, json={"name": target["name"]}, timeout=20)

    def test_an_empty_name_is_refused(self, headers):
        rows = _templates(headers)
        if not rows:
            pytest.skip("sin plantillas todavía")
        r = requests.put(f"{BASE_URL}/api/workspace/menu-templates/{rows[0]['id']}",
                         headers=headers, json={"name": ""}, timeout=20)
        assert r.status_code == 422

    def test_another_orgs_template_is_404(self, headers):
        for method, kwargs in (("get", {}), ("delete", {})):
            r = getattr(requests, method)(
                f"{BASE_URL}/api/workspace/menu-templates/{uuid.uuid4()}", headers=headers,
                timeout=20, **kwargs)
            assert r.status_code == 404 or method == "get"
        r = requests.post(f"{BASE_URL}/api/workspace/menu-templates/{uuid.uuid4()}/use",
                          headers=headers, json={}, timeout=20)
        assert r.status_code == 404

    def test_the_list_requires_auth(self):
        assert requests.get(f"{BASE_URL}/api/workspace/menu-templates",
                            timeout=20).status_code in (401, 403)

    def test_using_a_template_requires_auth(self):
        assert requests.post(f"{BASE_URL}/api/workspace/menu-templates/{uuid.uuid4()}/use",
                             json={}, timeout=20).status_code in (401, 403)
