"""iter42 — publishing a menu must actually reach the TV.

The bug: POST /api/workspace/menus/{id}/publish only stamped
`screens.active_menu_id`, a field no player endpoint reads. The player builds
its playlist from published `playlists` docs, so the user published and the TV
kept showing the old content.

These tests assert the player-facing contract, not the internals.
"""
import os
import uuid

import pytest
import requests

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
def screens(headers):
    r = requests.get(f"{BASE_URL}/api/workspace/screens", headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, "the demo org needs at least one screen"
    return rows


@pytest.fixture
def menu(headers):
    name = f"pytest tv {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                      json={"name": name}, timeout=20)
    assert r.status_code in (200, 201), r.text
    menu_id = r.json()["id"]
    requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/items", headers=headers,
                  json={"name": "Pizza pytest", "price": 9.5, "category": "Pizza"}, timeout=20)
    yield menu_id
    requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)


def _player_items(screen_id):
    r = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20)
    assert r.status_code == 200, r.text
    return r.json().get("items") or []


class TestMenuReachesTheScreen:
    def test_published_menu_appears_in_the_player_playlist(self, headers, menu, screens):
        target = screens[0]["id"]
        r = requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/publish", headers=headers,
                          json={"screen_ids": [target]}, timeout=30)
        assert r.status_code == 200, r.text
        ids = [i.get("media_id") for i in _player_items(target)]
        assert f"menu:{menu}" in ids, f"the TV never got the menu — got {ids}"

    def test_playlist_version_bumps_so_the_tv_refetches(self, headers, menu, screens):
        target = screens[0]["id"]
        before = requests.get(f"{BASE_URL}/api/player/{target}/version", timeout=20).json()
        requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/publish", headers=headers,
                      json={"screen_ids": [target]}, timeout=30)
        after = requests.get(f"{BASE_URL}/api/player/{target}/version", timeout=20).json()
        assert after["playlist_version"] > before["playlist_version"]

    def test_unpicked_screens_do_not_get_the_menu(self, headers, menu, screens):
        if len(screens) < 2:
            pytest.skip("needs two screens")
        picked, other = screens[0]["id"], screens[1]["id"]
        requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/publish", headers=headers,
                      json={"screen_ids": [picked]}, timeout=30)
        ids = [i.get("media_id") for i in _player_items(other)]
        assert f"menu:{menu}" not in ids

    def test_republishing_narrower_pulls_the_menu_off_the_dropped_screen(self, headers, menu, screens):
        if len(screens) < 2:
            pytest.skip("needs two screens")
        a, b = screens[0]["id"], screens[1]["id"]
        requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/publish", headers=headers,
                      json={"screen_ids": [a, b]}, timeout=30)
        assert f"menu:{menu}" in [i.get("media_id") for i in _player_items(b)]
        requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/publish", headers=headers,
                      json={"screen_ids": [a]}, timeout=30)
        assert f"menu:{menu}" not in [i.get("media_id") for i in _player_items(b)]
        assert f"menu:{menu}" in [i.get("media_id") for i in _player_items(a)]

    def test_menu_render_url_in_the_playlist_actually_renders(self, headers, menu, screens):
        target = screens[0]["id"]
        requests.post(f"{BASE_URL}/api/workspace/menus/{menu}/publish", headers=headers,
                      json={"screen_ids": [target]}, timeout=30)
        item = next(i for i in _player_items(target) if i.get("media_id") == f"menu:{menu}")
        page = requests.get(f"{BASE_URL}{item['media_url']}", timeout=20)
        assert page.status_code == 200, page.text[:300]
        assert "Pizza pytest" in page.text


class TestMenuPreview:
    def test_owner_gets_a_signed_preview_url_that_renders_a_draft(self, headers, menu):
        r = requests.get(f"{BASE_URL}/api/workspace/menus/{menu}/preview",
                         headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert "preview=" in url
        page = requests.get(f"{BASE_URL}{url}", timeout=20)
        assert page.status_code == 200, page.text[:300]
        assert "Pizza pytest" in page.text

    def test_draft_render_without_a_token_stays_hidden(self, menu):
        page = requests.get(f"{BASE_URL}/api/menus/{menu}/render", timeout=20)
        assert page.status_code == 404

    def test_a_tampered_token_is_rejected(self, menu):
        page = requests.get(f"{BASE_URL}/api/menus/{menu}/render?preview=abc.def", timeout=20)
        assert page.status_code == 404

    def test_preview_of_someone_elses_menu_is_404(self, headers):
        r = requests.get(f"{BASE_URL}/api/workspace/menus/{uuid.uuid4()}/preview",
                         headers=headers, timeout=20)
        assert r.status_code == 404

    def test_preview_requires_auth(self, menu):
        r = requests.get(f"{BASE_URL}/api/workspace/menus/{menu}/preview", timeout=20)
        assert r.status_code in (401, 403)
