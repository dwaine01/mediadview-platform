"""Publishing a menu targets the screens you pick, not every screen you own.

duarte's report: «después que creo un menú y lo guardo y quiero publicarlo en
una pantalla debería preguntarme en qué pantalla y ahí la selecciono, pero no
en todas actualizar». The panel used to publish to every screen implicitly; the
backend also left the menu active on screens that were dropped from a later,
narrower selection.
"""
import uuid

import pytest
import requests

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}


@pytest.fixture
def owner_headers(base_url):
    r = requests.post(f"{base_url}/api/auth/login", json=OWNER, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def menu_and_screens(base_url, owner_headers):
    screens = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()
    if len(screens) < 2:
        pytest.skip("se necesitan al menos 2 pantallas")
    created = requests.post(
        f"{base_url}/api/workspace/menus", headers=owner_headers,
        json={"name": f"pytest publish {uuid.uuid4().hex[:6]}"}, timeout=20)
    assert created.status_code in (200, 201), created.text
    menu_id = created.json()["id"]
    item = requests.post(
        f"{base_url}/api/workspace/menus/{menu_id}/items", headers=owner_headers,
        json={"name": "Café", "price": 2.5, "category": "Bebidas"}, timeout=20)
    assert item.status_code in (200, 201), item.text
    yield {"menu_id": menu_id, "screens": [s["id"] for s in screens[:3]]}
    requests.delete(f"{base_url}/api/workspace/menus/{menu_id}", headers=owner_headers, timeout=20)


def _active_menus(base_url, headers, screen_ids):
    all_screens = requests.get(f"{base_url}/api/workspace/screens", headers=headers, timeout=20).json()
    by_id = {s["id"]: s for s in all_screens}
    return {sid: by_id[sid].get("active_menu_id") for sid in screen_ids if sid in by_id}


class TestMenuPublishPerScreen:
    def test_publishes_only_to_the_picked_screens(self, base_url, owner_headers, menu_and_screens):
        menu_id = menu_and_screens["menu_id"]
        picked = menu_and_screens["screens"][:1]
        others = menu_and_screens["screens"][1:]

        r = requests.post(f"{base_url}/api/workspace/menus/{menu_id}/publish",
                          headers=owner_headers, json={"screen_ids": picked}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["screen_ids"] == picked

        active = _active_menus(base_url, owner_headers, picked + others)
        assert active[picked[0]] == menu_id
        for sid in others:
            assert active[sid] != menu_id, "el menú se colgó de una pantalla que no fue elegida"

    def test_republishing_narrower_removes_it_from_the_dropped_screens(
            self, base_url, owner_headers, menu_and_screens):
        menu_id = menu_and_screens["menu_id"]
        two = menu_and_screens["screens"][:2]

        requests.post(f"{base_url}/api/workspace/menus/{menu_id}/publish",
                      headers=owner_headers, json={"screen_ids": two}, timeout=20)
        assert all(v == menu_id for v in _active_menus(base_url, owner_headers, two).values())

        # Now only the first one.
        r = requests.post(f"{base_url}/api/workspace/menus/{menu_id}/publish",
                          headers=owner_headers, json={"screen_ids": two[:1]}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["removed_from"] >= 1
        active = _active_menus(base_url, owner_headers, two)
        assert active[two[0]] == menu_id
        assert active[two[1]] is None, "la pantalla descartada siguió mostrando el menú"

    def test_unknown_screen_is_rejected(self, base_url, owner_headers, menu_and_screens):
        r = requests.post(f"{base_url}/api/workspace/menus/{menu_and_screens['menu_id']}/publish",
                          headers=owner_headers,
                          json={"screen_ids": [menu_and_screens["screens"][0], "does-not-exist"]},
                          timeout=20)
        assert r.status_code == 404

    def test_empty_selection_still_falls_back_to_all_screens(
            self, base_url, owner_headers, menu_and_screens):
        """Backwards compatibility: any old caller that sends nothing keeps working."""
        r = requests.post(f"{base_url}/api/workspace/menus/{menu_and_screens['menu_id']}/publish",
                          headers=owner_headers, json={}, timeout=20)
        assert r.status_code == 200, r.text
        all_screens = requests.get(f"{base_url}/api/workspace/screens",
                                   headers=owner_headers, timeout=20).json()
        assert len(r.json()["screen_ids"]) == len(all_screens)
