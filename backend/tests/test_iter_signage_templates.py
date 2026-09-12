"""Backend tests for F1: Premium Signage Templates (Pizzeria).

Covers: catalog, industries, preview, design create/list/get/update, product edit,
publish, player playlist contract, checksum change on edit, delete, and ownership
error paths.
"""
import hashlib
import os
import re
import time

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://sprint1-signage.preview.emergentagent.com").rstrip("/")

PIZZA_EMAIL = "pizzeria@demo.com"
PIZZA_PASS = "Pizza1234!"

LANDSCAPE_ID = "pizzeria-forno-grid-16x9"
PORTRAIT_ID = "pizzeria-forno-tower-9x16"


# ── Session with auth for the owner ─────────────────────────────────────
@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email": PIZZA_EMAIL, "password": PIZZA_PASS}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in response: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def org_screens(owner):
    r = owner.get(f"{BASE}/api/workspace/screens", timeout=15)
    assert r.status_code == 200, r.text[:200]
    screens = r.json()
    assert len(screens) >= 1, "org needs at least one screen"
    return screens


@pytest.fixture(scope="module")
def other_org_session():
    """A second workspace login for cross-org 404 checks."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email": "testws@test.com", "password": "Test1234!"}, timeout=20)
    if r.status_code != 200:
        pytest.skip("Second org login not available")
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── Catálogo ────────────────────────────────────────────────────────────
class TestCatalog:
    def test_list_templates_returns_both_pizza(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        ids = {row["id"] for row in rows}
        assert LANDSCAPE_ID in ids and PORTRAIT_ID in ids
        for row in rows:
            if row["id"] == LANDSCAPE_ID:
                assert row["orientation"] == "landscape"
                assert row["industry"] == "pizzeria"
            if row["id"] == PORTRAIT_ID:
                assert row["orientation"] == "portrait"

    def test_filter_industry_pizzeria(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates?industry=pizzeria", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        assert all(row["industry"] == "pizzeria" for row in rows)

    def test_filter_orientation_landscape(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates?orientation=landscape", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert any(row["id"] == LANDSCAPE_ID for row in rows)
        assert all(row["orientation"] == "landscape" for row in rows)

    def test_filter_orientation_portrait(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-templates?orientation=portrait", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert any(row["id"] == PORTRAIT_ID for row in rows)

    def test_industries_pizzeria_count(self, owner):
        r = owner.get(f"{BASE}/api/workspace/signage-industries", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        pizza = next((row for row in rows if row["industry"] == "pizzeria"), None)
        assert pizza is not None
        assert pizza["templates"] == 2

    def test_preview_public_landscape(self):
        r = requests.get(f"{BASE}/api/signage-templates/{LANDSCAPE_ID}/preview", timeout=20)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "Trattoria Forno" in r.text or "Forno" in r.text

    def test_preview_public_portrait(self):
        r = requests.get(f"{BASE}/api/signage-templates/{PORTRAIT_ID}/preview", timeout=20)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")


# ── Diseño: crear, listar, obtener, actualizar ─────────────────────────
class TestDesignLifecycle:
    design_id = None

    def test_create_design_from_landscape(self, owner):
        r = owner.post(f"{BASE}/api/workspace/designs",
                       json={"template_id": LANDSCAPE_ID}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["template_id"] == LANDSCAPE_ID
        assert data.get("design_id")
        TestDesignLifecycle.design_id = data["design_id"]

    def test_get_design_has_15_products_and_sample_urls(self, owner):
        did = TestDesignLifecycle.design_id
        r = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r.status_code == 200
        payload = r.json()
        design = payload["design"]
        template = payload["template"]
        assert template["id"] == LANDSCAPE_ID
        products = design.get("products") or {}
        assert len(products) == 15, f"Expected 15 sample products, got {len(products)}"
        # All image_url should be /api/static/template-samples/pizzeria/*.jpg and return 200
        checked = 0
        for pid, p in products.items():
            url = p.get("image_url", "")
            assert url.startswith("/api/static/template-samples/pizzeria/"), url
            resp = requests.get(f"{BASE}{url}", timeout=15)
            assert resp.status_code == 200, f"{url} -> {resp.status_code}"
            checked += 1
            if checked >= 5:
                break

    def test_list_designs_includes_created(self, owner):
        r = owner.get(f"{BASE}/api/workspace/designs", timeout=15)
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert TestDesignLifecycle.design_id in ids

    def test_put_business_name_persists(self, owner):
        did = TestDesignLifecycle.design_id
        r = owner.put(f"{BASE}/api/workspace/designs/{did}",
                      json={"brand": {"business_name": "TEST_Pizzería Del Barrio", "logo_url": None}},
                      timeout=15)
        assert r.status_code == 200, r.text[:200]
        r2 = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r2.json()["design"]["brand"]["business_name"] == "TEST_Pizzería Del Barrio"

    def test_put_product_updates_render_and_checksum(self, owner):
        did = TestDesignLifecycle.design_id
        # get first product id
        payload = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15).json()
        products = payload["design"]["products"]
        pid = next(iter(products.keys()))
        # Snapshot render + checksum (via playlist item helper isn't public; use render HTML)
        r0 = requests.get(f"{BASE}/api/designs/{did}/render", timeout=20)
        assert r0.status_code == 200
        html_before = r0.text

        new_name = "TEST_PizzaÚnica"
        new_price = 99.77
        r = owner.put(f"{BASE}/api/workspace/designs/{did}/products/{pid}",
                      json={"name": new_name, "price": new_price,
                            "variants": [{"label": "XL", "price": new_price}]}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        merged = r.json()
        assert merged["name"] == new_name
        assert merged["price"] == new_price

        time.sleep(1)
        r1 = requests.get(f"{BASE}/api/designs/{did}/render", timeout=20)
        assert r1.status_code == 200
        assert new_name in r1.text, "New name should appear in rendered HTML"
        assert html_before != r1.text, "Render HTML should change after edit"


# ── Publish + player contract ──────────────────────────────────────────
class TestPublishAndPlayerContract:
    def test_publish_requires_screen_ids(self, owner):
        did = TestDesignLifecycle.design_id
        r = owner.post(f"{BASE}/api/workspace/designs/{did}/publish", json={}, timeout=15)
        assert r.status_code == 400

    def test_publish_rejects_unknown_screen(self, owner):
        did = TestDesignLifecycle.design_id
        r = owner.post(f"{BASE}/api/workspace/designs/{did}/publish",
                       json={"screen_ids": ["not-a-real-screen-id-xxx"]}, timeout=15)
        assert r.status_code == 404

    def test_publish_success_and_player_playlist(self, owner, org_screens):
        did = TestDesignLifecycle.design_id
        screen_id = org_screens[0]["id"]
        r = owner.post(f"{BASE}/api/workspace/designs/{did}/publish",
                       json={"screen_ids": [screen_id], "duration": 45}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["published_to"] == 1

        # Player contract endpoint (same as APK): /api/player/{screen_id}/playlist
        time.sleep(1)
        r2 = requests.get(f"{BASE}/api/player/{screen_id}/playlist", timeout=20)
        assert r2.status_code == 200, r2.text[:200]
        data = r2.json()
        items = data.get("items") or []
        design_items = [it for it in items if it.get("media_id") == f"design:{did}"]
        assert design_items, f"Design item not found in playlist. Items: {items}"
        item = design_items[0]
        assert item["content_type"] == "widget"
        assert re.search(rf"/api/designs/{re.escape(did)}/render(\?v=\d+)?", item["media_url"])
        checksum = item.get("checksum") or ""
        assert re.fullmatch(r"[0-9a-f]{64}", checksum), f"Bad checksum: {checksum}"
        TestPublishAndPlayerContract._prev_checksum = checksum
        TestPublishAndPlayerContract._screen_id = screen_id

    def test_price_edit_changes_checksum(self, owner):
        did = TestDesignLifecycle.design_id
        screen_id = TestPublishAndPlayerContract._screen_id
        # Modify another product price
        payload = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15).json()
        pids = list(payload["design"]["products"].keys())
        pid = pids[1]
        time.sleep(1.2)  # ensure updated_at moves at least 1s
        r = owner.put(f"{BASE}/api/workspace/designs/{did}/products/{pid}",
                      json={"price": 42.42}, timeout=15)
        assert r.status_code == 200
        time.sleep(1)
        r2 = requests.get(f"{BASE}/api/player/{screen_id}/playlist", timeout=20)
        assert r2.status_code == 200
        items = [it for it in r2.json().get("items") or [] if it.get("media_id") == f"design:{did}"]
        assert items
        new_checksum = items[0]["checksum"]
        assert re.fullmatch(r"[0-9a-f]{64}", new_checksum)
        assert new_checksum != TestPublishAndPlayerContract._prev_checksum, \
            "Checksum must change after product edit"


# ── Cross-org 404 ──────────────────────────────────────────────────────
class TestCrossOrgIsolation:
    def test_other_org_cannot_get_design(self, other_org_session):
        did = TestDesignLifecycle.design_id
        r = other_org_session.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r.status_code == 404

    def test_other_org_cannot_edit_design(self, other_org_session):
        did = TestDesignLifecycle.design_id
        r = other_org_session.put(f"{BASE}/api/workspace/designs/{did}",
                                  json={"name": "hack"}, timeout=15)
        assert r.status_code == 404


# ── Delete cleans design + playlist ────────────────────────────────────
class TestDelete:
    def test_delete_removes_design_and_playlist(self, owner):
        did = TestDesignLifecycle.design_id
        r = owner.delete(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r.status_code == 200
        # After delete, GET returns 404
        r2 = owner.get(f"{BASE}/api/workspace/designs/{did}", timeout=15)
        assert r2.status_code == 404
        # Player playlist no longer contains the design item
        screen_id = TestPublishAndPlayerContract._screen_id
        r3 = requests.get(f"{BASE}/api/player/{screen_id}/playlist", timeout=15)
        assert r3.status_code == 200
        items = r3.json().get("items") or []
        assert not any(it.get("media_id") == f"design:{did}" for it in items), \
            "Design item must be gone from playlist after delete"
