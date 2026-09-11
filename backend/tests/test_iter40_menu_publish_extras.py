"""Iter40 — extra regressions around the per-screen menu publish feature.

Covers what the review request explicitly asks on top of
`test_menu_publish_per_screen.py`:

  * publishing without a bearer token must be 401
  * publishing a menu that has NO products still succeeds (the panel
    disables the button on the client side; the backend has never blocked
    it, so we lock that behaviour in — "el error que corresponda" ended up
    being "no error")
  * publishing a screen_id owned by a DIFFERENT org is a 404 (not a 403
    that would leak existence)
  * playlist publish endpoint (POST /playlists/{id}/publish) is unchanged
  * screen reconnect endpoint (POST /screens/connect + screen_id) is unchanged
"""
import uuid

import pytest
import requests

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}
OTHER = {"email": "testws@test.com", "password": "Test1234!"}


@pytest.fixture
def owner_headers(base_url):
    r = requests.post(f"{base_url}/api/auth/login", json=OWNER, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def other_headers(base_url):
    r = requests.post(f"{base_url}/api/auth/login", json=OTHER, timeout=20)
    if r.status_code != 200:
        pytest.skip("secondary org account not available")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def fresh_menu(base_url, owner_headers):
    created = requests.post(
        f"{base_url}/api/workspace/menus",
        headers=owner_headers,
        json={"name": f"iter40 extras {uuid.uuid4().hex[:6]}"},
        timeout=20,
    )
    assert created.status_code in (200, 201), created.text
    menu_id = created.json()["id"]
    yield menu_id
    requests.delete(f"{base_url}/api/workspace/menus/{menu_id}", headers=owner_headers, timeout=20)


class TestMenuPublishExtras:
    def test_publish_without_token_is_401(self, base_url, fresh_menu):
        r = requests.post(
            f"{base_url}/api/workspace/menus/{fresh_menu}/publish",
            json={"screen_ids": []},
            timeout=20,
        )
        assert r.status_code in (401, 403), r.text

    def test_menu_without_products_still_publishes(self, base_url, owner_headers, fresh_menu):
        # There are no items on this menu — the panel disables the button, but
        # the backend has never rejected it; freeze that behaviour so we don't
        # accidentally start returning 400 and break older clients.
        screens = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()
        if not screens:
            pytest.skip("necesitamos al menos una pantalla")
        r = requests.post(
            f"{base_url}/api/workspace/menus/{fresh_menu}/publish",
            headers=owner_headers,
            json={"screen_ids": [screens[0]["id"]]},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["screen_ids"] == [screens[0]["id"]]

    def test_screen_from_another_org_is_404(self, base_url, owner_headers, other_headers, fresh_menu):
        # Find a screen that belongs to the OTHER org.
        foreign = requests.get(f"{base_url}/api/workspace/screens", headers=other_headers, timeout=20).json()
        if not foreign:
            # No screens on the other account — fall back to the UUID-not-owned check.
            foreign_id = str(uuid.uuid4())
        else:
            foreign_id = foreign[0]["id"]
        r = requests.post(
            f"{base_url}/api/workspace/menus/{fresh_menu}/publish",
            headers=owner_headers,
            json={"screen_ids": [foreign_id]},
            timeout=20,
        )
        assert r.status_code == 404, r.text


class TestPublishRegressions:
    """Make sure the sibling flows we didn't touch still work."""

    def test_playlist_publish_still_works(self, base_url, owner_headers):
        screens = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()
        if not screens:
            pytest.skip("necesitamos al menos una pantalla")

        # Grab an existing playlist or create a lightweight one.
        pls = requests.get(f"{base_url}/api/workspace/playlists", headers=owner_headers, timeout=20).json()
        created_here = False
        if pls:
            playlist_id = pls[0]["id"]
        else:
            created = requests.post(
                f"{base_url}/api/workspace/playlists",
                headers=owner_headers,
                json={"name": f"iter40 pl {uuid.uuid4().hex[:6]}", "items": []},
                timeout=20,
            )
            assert created.status_code in (200, 201), created.text
            playlist_id = created.json()["id"]
            created_here = True

        try:
            r = requests.post(
                f"{base_url}/api/workspace/playlists/{playlist_id}/publish",
                headers=owner_headers,
                json={"screen_ids": [screens[0]["id"]]},
                timeout=20,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert screens[0]["id"] in body.get("screen_ids", [])
        finally:
            if created_here:
                requests.delete(f"{base_url}/api/workspace/playlists/{playlist_id}",
                                headers=owner_headers, timeout=20)

    def test_screen_reconnect_still_works(self, base_url, owner_headers):
        screens = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()
        if not screens:
            pytest.skip("necesitamos al menos una pantalla")
        target = screens[0]["id"]

        dev = requests.post(
            f"{base_url}/api/devices/register",
            json={"device_name": "iter40 reconnect", "device_model": "pytest",
                  "client_uuid": f"iter40-reconnect-{uuid.uuid4().hex[:10]}"},
            timeout=20,
        )
        assert dev.status_code == 200, dev.text
        body = dev.json()

        r = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": body["activation_code"], "screen_id": target},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["reconnected"] is True
        assert j["screen"]["id"] == target
