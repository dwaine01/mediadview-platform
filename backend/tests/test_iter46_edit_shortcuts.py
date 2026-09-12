"""
Iteración 46 — Los 3 accesos rápidos al editor:
1. /api/workspace/now-playing devuelve now_playing.edit_kind + edit_id + editables
2. Regresión: rama de menús sigue igual
3. PUT /workspace/designs/{id}/products/{pid} sube versión del playlist y cambia checksum
   sin llamar a /publish
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"

EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def now_playing(headers):
    r = requests.get(f"{BASE_URL}/api/workspace/now-playing", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. now-playing devuelve edit_kind + edit_id + editables ────────────────
class TestNowPlayingEditTargets:

    def test_response_is_list(self, now_playing):
        assert isinstance(now_playing, list)
        assert len(now_playing) >= 1

    def test_screens_have_editables_field(self, now_playing):
        for s in now_playing:
            assert "editables" in s, f"screen {s.get('screen_name')} missing editables"
            assert isinstance(s["editables"], list)

    def test_editables_no_duplicates(self, now_playing):
        for s in now_playing:
            ids = [e["edit_id"] for e in s["editables"]]
            assert len(ids) == len(set(ids)), f"duplicated editables in {s['screen_name']}"

    def test_expected_edit_kinds_per_screen(self, now_playing):
        """Mostrador/Sala/PRUEBA 2B-5 TV Box -> menu; Vitrina -> design."""
        expectations = {
            "Mostrador": "menu",
            "Sala": "menu",
            "Vitrina": "design",
        }
        by_name = {s["screen_name"]: s for s in now_playing}
        for name, expected_kind in expectations.items():
            if name not in by_name:
                pytest.skip(f"Screen {name} not present in demo org")
            editables = by_name[name]["editables"]
            assert any(e["edit_kind"] == expected_kind for e in editables), (
                f"{name} should have an editable of kind {expected_kind}, got {editables}"
            )
            np = by_name[name].get("now_playing")
            if np and np.get("kind") in ("menu",) and expected_kind == "menu":
                # If a menu is on air right now, edit_kind/edit_id must be set
                assert np.get("edit_kind") == "menu", f"{name} now_playing missing edit_kind"
                assert np.get("edit_id"), f"{name} now_playing missing edit_id"
            if np and expected_kind == "design":
                # For Vitrina (design), whatever is now_playing is the design widget
                assert np.get("edit_kind") == "design", f"{name} now_playing.edit_kind={np.get('edit_kind')}"
                assert np.get("edit_id"), f"{name} now_playing missing edit_id"

    def test_prueba_2b5_is_menu(self, now_playing):
        prueba = next((s for s in now_playing if "PRUEBA 2B-5" in (s.get("screen_name") or "")), None)
        if not prueba:
            pytest.skip("PRUEBA 2B-5 screen not present")
        assert any(e["edit_kind"] == "menu" for e in prueba["editables"]), prueba["editables"]

    def test_screen_without_content_empty_editables(self, headers, now_playing):
        """A screen with no content should return editables=[] and now_playing=null."""
        # Create a brand-new empty screen for this assertion
        r = requests.post(
            f"{BASE_URL}/api/workspace/screens",
            headers=headers,
            json={"name": "TEST_IT46_empty_screen"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        sid = r.json()["id"]
        try:
            rr = requests.get(f"{BASE_URL}/api/workspace/now-playing", headers=headers, timeout=30)
            assert rr.status_code == 200
            row = next((s for s in rr.json() if s["screen_id"] == sid), None)
            assert row is not None
            assert row["editables"] == []
            assert row["now_playing"] is None
        finally:
            requests.delete(f"{BASE_URL}/api/workspace/screens/{sid}", headers=headers, timeout=15)


# ── 2. Regresión: rama menú de now-playing ─────────────────────────────────
class TestNowPlayingMenuRegression:

    def test_menu_now_playing_has_expected_fields(self, now_playing):
        for s in now_playing:
            np = s.get("now_playing")
            if np and np.get("kind") == "menu":
                for field in ("title", "kind", "thumb_url", "seconds_left", "playlist_name"):
                    assert field in np, f"{s['screen_name']} menu now_playing missing {field}"
                assert np["kind"] == "menu"
                return
        pytest.skip("No menu currently on air")

    def test_screens_endpoint_unchanged(self, headers):
        r = requests.get(f"{BASE_URL}/api/workspace/screens", headers=headers, timeout=15)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 1
        s = arr[0]
        for f in ("id", "name", "organization_id", "status"):
            assert f in s

    def test_player_playlist_contract(self, headers, now_playing):
        sid = now_playing[0]["screen_id"]
        r = requests.get(f"{BASE_URL}/api/player/{sid}/playlist", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # basic contract: playlist_version + items
        assert "playlist_version" in data
        assert "items" in data
        assert isinstance(data["items"], list)


# ── 3. Editar producto de diseño publicado sube versión + cambia checksum ──
class TestDesignEditReachesTV:

    def test_edit_published_design_bumps_version_and_checksum(self, headers, now_playing):
        # Locate Vitrina (design)
        vitrina = next((s for s in now_playing if s.get("screen_name") == "Vitrina"), None)
        if not vitrina:
            pytest.skip("Vitrina screen not in demo org")
        editable = next((e for e in vitrina["editables"] if e["edit_kind"] == "design"), None)
        assert editable, "Vitrina should have a design editable"
        design_id = editable["edit_id"]

        # Snapshot 1
        p0 = requests.get(f"{BASE_URL}/api/player/{vitrina['screen_id']}/playlist", timeout=15).json()
        v0 = p0["playlist_version"]
        items0 = p0.get("items", [])
        design_item0 = next((i for i in items0 if design_id in str(i.get("media_id", "")) or design_id in str(i.get("media_url", ""))), None)
        assert design_item0, f"design {design_id} not found in playlist items"
        checksum0 = design_item0.get("checksum")
        assert checksum0

        # Fetch design + first product
        d = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}", headers=headers, timeout=15)
        assert d.status_code == 200, d.text
        design = d.json()["design"]
        products = design.get("products") or {}
        assert products, "design has no products"
        pid, product = next(iter(products.items()))
        original_price = product.get("price")

        # Edit product price (no /publish call!)
        new_price = float(original_price or 10) + 1.23
        r = requests.put(
            f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
            headers=headers,
            json={"price": new_price},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        # Give backend a moment
        time.sleep(1.0)

        # Snapshot 2
        p1 = requests.get(f"{BASE_URL}/api/player/{vitrina['screen_id']}/playlist", timeout=15).json()
        v1 = p1["playlist_version"]
        items1 = p1.get("items", [])
        design_item1 = next((i for i in items1 if design_id in str(i.get("media_id", "")) or design_id in str(i.get("media_url", ""))), None)
        assert design_item1, "design item disappeared after edit"
        checksum1 = design_item1.get("checksum")

        try:
            assert v1 > v0, f"playlist version did not bump: v0={v0} v1={v1}"
            assert checksum1 != checksum0, f"checksum did not change: {checksum0} == {checksum1}"

            # Confirm status stayed 'published' (we did NOT re-publish)
            d2 = requests.get(f"{BASE_URL}/api/workspace/designs/{design_id}", headers=headers, timeout=15).json()
            assert d2["design"]["status"] == "published"
        finally:
            # Restore original price
            if original_price is not None:
                requests.put(
                    f"{BASE_URL}/api/workspace/designs/{design_id}/products/{pid}",
                    headers=headers, json={"price": original_price}, timeout=20,
                )
