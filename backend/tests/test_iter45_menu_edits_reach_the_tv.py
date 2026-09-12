"""iter45 — la causa real de «cambié el precio y la tele no cambia».

El player Kotlin decide si recargar comparando una firma de la playlist:
`media_id:checksum:duration:rotation:display_mode` (PlayerModels.kt:98). Un
ítem de menú es una URL, así que editar un precio no cambiaba NADA de esa
firma y el WebView seguía mostrando el precio viejo para siempre. Encima el
panel sólo subía `playlist_version` cuando se marcaba «agotado».

Estos tests fijan las dos condiciones que hacen que el cambio llegue:
  · la firma del ítem cambia cuando el menú se edita,
  · `playlist_version` sube con cualquier edición, no sólo con «agotado».

Contrato del APK que NO se puede romper: `checksum` tiene que seguir siendo
sha256 de 64 hex (PlayerModels.kt:68 lo descarta si no matchea) y la forma del
JSON no cambia.
"""
import os
import re
import uuid

import pytest
import requests

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def screen_id(headers):
    rows = requests.get(f"{BASE_URL}/api/workspace/screens", headers=headers, timeout=20).json()
    assert rows, "the demo org needs a screen"
    return rows[0]["id"]


@pytest.fixture
def published(headers, screen_id):
    r = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                      json={"name": f"pytest live {uuid.uuid4().hex[:6]}"}, timeout=20)
    menu_id = r.json()["id"]
    item = requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/items", headers=headers,
                         json={"name": "Plato pytest", "price": 10.0}, timeout=20).json()
    requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/publish", headers=headers,
                  json={"screen_ids": [screen_id]}, timeout=30)
    yield menu_id, (item.get("item") or item).get("id") or item.get("item_id")
    requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)


def signature(screen_id, menu_id):
    """La misma firma que calcula el player."""
    items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
    item = next(i for i in items if i["media_id"] == f"menu:{menu_id}")
    return f"{item['media_id']}:{item['checksum']}:{item['duration']}:{item['rotation']}:{item['display_mode']}"


def version(screen_id):
    return requests.get(f"{BASE_URL}/api/player/{screen_id}/version", timeout=20).json()["playlist_version"]


class TestThePlayerSeesTheChange:
    def test_the_menu_item_carries_a_real_sha256_checksum(self, headers, screen_id, published):
        menu_id, _ = published
        items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
        item = next(i for i in items if i["media_id"] == f"menu:{menu_id}")
        assert SHA256.match(item["checksum"] or ""), item["checksum"]

    def test_changing_a_price_changes_the_playlist_signature(self, headers, screen_id, published):
        menu_id, item_id = published
        before = signature(screen_id, menu_id)
        r = requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/items/{item_id}",
                         headers=headers, json={"price": 77.7}, timeout=20)
        assert r.status_code == 200, r.text
        assert signature(screen_id, menu_id) != before, "el player no se enteraría del cambio"

    def test_changing_a_name_changes_the_playlist_signature(self, headers, screen_id, published):
        menu_id, item_id = published
        before = signature(screen_id, menu_id)
        requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/items/{item_id}",
                     headers=headers, json={"name": "Plato renombrado"}, timeout=20)
        assert signature(screen_id, menu_id) != before

    def test_the_render_url_is_cache_busted(self, headers, screen_id, published):
        menu_id, item_id = published
        items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
        before = next(i for i in items if i["media_id"] == f"menu:{menu_id}")["media_url"]
        assert "?v=" in before, before
        requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/items/{item_id}",
                     headers=headers, json={"price": 88.8}, timeout=20)
        items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
        after = next(i for i in items if i["media_id"] == f"menu:{menu_id}")["media_url"]
        assert after != before

    def test_the_render_is_never_cached_by_the_webview(self, headers, screen_id, published):
        menu_id, _ = published
        url = requests.get(f"{BASE_URL}/api/workspace/menus/{menu_id}/preview",
                           headers=headers, timeout=20).json()["url"]
        page = requests.get(f"{BASE_URL}{url}", timeout=30)
        assert "no-store" in page.headers.get("Cache-Control", "")

    def test_the_json_shape_the_apk_parses_did_not_change(self, headers, screen_id, published):
        menu_id, _ = published
        items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
        item = next(i for i in items if i["media_id"] == f"menu:{menu_id}")
        for key in ("media_id", "filename", "content_type", "duration", "rotation",
                    "display_mode", "media_url", "download_url", "checksum"):
            assert key in item, key
        assert item["content_type"] == "widget"
        assert isinstance(item["checksum"], str)


class TestVersionBumps:
    def test_editing_a_price_bumps_the_screen_version(self, headers, screen_id, published):
        menu_id, item_id = published
        before = version(screen_id)
        requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/items/{item_id}",
                     headers=headers, json={"price": 21.0}, timeout=20)
        assert version(screen_id) > before

    def test_renaming_the_menu_bumps_the_screen_version(self, headers, screen_id, published):
        menu_id, _ = published
        before = version(screen_id)
        requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers,
                     json={"name": "pytest renombrado"}, timeout=20)
        assert version(screen_id) > before

    def test_adding_an_item_bumps_the_screen_version(self, headers, screen_id, published):
        menu_id, _ = published
        before = version(screen_id)
        requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/items", headers=headers,
                      json={"name": "Postre pytest", "price": 4.0}, timeout=20)
        assert version(screen_id) > before

    def test_removing_an_item_bumps_the_screen_version(self, headers, screen_id, published):
        menu_id, item_id = published
        before = version(screen_id)
        requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}/items/{item_id}",
                        headers=headers, timeout=20)
        assert version(screen_id) > before

    def test_marking_sold_out_still_bumps(self, headers, screen_id, published):
        menu_id, item_id = published
        before = version(screen_id)
        requests.put(f"{BASE_URL}/api/workspace/menus/{menu_id}/items/{item_id}",
                     headers=headers, json={"available": False}, timeout=20)
        assert version(screen_id) > before


class TestADeletedMenuDoesNotBlackOutTheScreen:
    """El playlist que nace al publicar un menú muere con el menú.

    Si queda publicado, gana el desempate por prioridad, no renderiza nada y
    la pantalla se va a negro. Además el builder ahora cae al siguiente
    contendiente cuando el ganador no produce ítems.
    """

    def test_deleting_the_menu_removes_its_playlist(self, headers, screen_id, published):
        menu_id, _ = published
        assert any(i["media_id"] == f"menu:{menu_id}" for i in
                   requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"])
        requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)
        items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
        assert not any(i["media_id"] == f"menu:{menu_id}" for i in items)

    def test_the_screen_keeps_showing_the_other_content(self, headers, screen_id):
        """Borrar un menú no puede dejar la pantalla vacía si hay otro contenido."""
        other = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                              json={"name": f"pytest survivor {uuid.uuid4().hex[:6]}"}, timeout=20).json()["id"]
        requests.post(f"{BASE_URL}/api/workspace/menus/{other}/items", headers=headers,
                      json={"name": "Sobreviviente", "price": 3.0}, timeout=20)
        requests.post(f"{BASE_URL}/api/workspace/menus/{other}/publish", headers=headers,
                      json={"screen_ids": [screen_id]}, timeout=30)
        doomed = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                               json={"name": f"pytest doomed {uuid.uuid4().hex[:6]}"}, timeout=20).json()["id"]
        requests.post(f"{BASE_URL}/api/workspace/menus/{doomed}/items", headers=headers,
                      json={"name": "Condenado", "price": 9.0}, timeout=20)
        requests.post(f"{BASE_URL}/api/workspace/menus/{doomed}/publish", headers=headers,
                      json={"screen_ids": [screen_id]}, timeout=30)
        try:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{doomed}", headers=headers, timeout=20)
            items = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()["items"]
            assert items, "la pantalla quedó en negro después de borrar un menú"
            assert any(i["media_id"] == f"menu:{other}" for i in items), [i["media_id"] for i in items]
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/menus/{other}", headers=headers, timeout=20)
