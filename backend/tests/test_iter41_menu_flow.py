"""Iter41 — end-to-end backend for the menu flow:
   AI import -> publish on a specific screen -> update prices/photos.

Focus of this review:
  * POST /api/workspace/menus/{id}/publish with empty screen_ids
    (current backend: empty falls back to ALL screens — legacy behaviour).
    We ALSO assert what the endpoint does when the panel now guards against
    that, so callers know both branches.
  * PUT price update reflects on GET.
  * AI photo generation for an item (may return 200 with image_url, or a
    handled 500 if EMERGENT_LLM_KEY isn't functional) — we assert the
    endpoint exists and never crashes without a clear detail.
  * AI menu import (photo-based) endpoint exists and rejects bogus payloads
    cleanly.
"""
import base64
import io
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
def menu(base_url, owner_headers):
    r = requests.post(
        f"{base_url}/api/workspace/menus", headers=owner_headers,
        json={"name": f"iter41 {uuid.uuid4().hex[:6]}"}, timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    menu_id = r.json()["id"]
    it = requests.post(
        f"{base_url}/api/workspace/menus/{menu_id}/items", headers=owner_headers,
        json={"name": "Pizza Margherita", "price": 9.5, "category": "Pizza"}, timeout=20,
    )
    assert it.status_code in (200, 201), it.text
    yield {"menu_id": menu_id, "item_id": it.json()["id"]}
    requests.delete(f"{base_url}/api/workspace/menus/{menu_id}", headers=owner_headers, timeout=20)


class TestPublishValidation:
    def test_publish_empty_screen_ids_falls_back_to_all(self, base_url, owner_headers, menu):
        """Backwards compatibility: empty payload publishes to every org screen."""
        r = requests.post(
            f"{base_url}/api/workspace/menus/{menu['menu_id']}/publish",
            headers=owner_headers, json={"screen_ids": []}, timeout=20,
        )
        assert r.status_code == 200, r.text
        all_screens = requests.get(f"{base_url}/api/workspace/screens",
                                   headers=owner_headers, timeout=20).json()
        # response contains screen_ids of every owned screen
        assert len(r.json()["screen_ids"]) == len(all_screens)

    def test_publish_one_screen_updates_only_that_one(self, base_url, owner_headers, menu):
        screens = requests.get(f"{base_url}/api/workspace/screens",
                               headers=owner_headers, timeout=20).json()
        if len(screens) < 2:
            pytest.skip("need >=2 screens")
        picked = [screens[0]["id"]]
        r = requests.post(
            f"{base_url}/api/workspace/menus/{menu['menu_id']}/publish",
            headers=owner_headers, json={"screen_ids": picked}, timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["screen_ids"] == picked

        after = requests.get(f"{base_url}/api/workspace/screens",
                             headers=owner_headers, timeout=20).json()
        by_id = {s["id"]: s for s in after}
        assert by_id[picked[0]].get("active_menu_id") == menu["menu_id"]
        for s in screens[1:]:
            assert by_id[s["id"]].get("active_menu_id") != menu["menu_id"]

    def test_publish_unauthorized_is_401_or_403(self, base_url, menu):
        r = requests.post(
            f"{base_url}/api/workspace/menus/{menu['menu_id']}/publish",
            json={"screen_ids": []}, timeout=20,
        )
        assert r.status_code in (401, 403), r.text


class TestItemPriceUpdate:
    def test_update_price_persists_on_get(self, base_url, owner_headers, menu):
        new_price = 12.75
        r = requests.put(
            f"{base_url}/api/workspace/menus/{menu['menu_id']}/items/{menu['item_id']}",
            headers=owner_headers, json={"price": new_price}, timeout=20,
        )
        assert r.status_code in (200, 204), r.text

        got = requests.get(f"{base_url}/api/workspace/menus/{menu['menu_id']}",
                           headers=owner_headers, timeout=20).json()
        target = next(i for i in got["items"] if i["id"] == menu["item_id"])
        assert float(target["price"]) == new_price


class TestAiPhotoEndpoint:
    def test_ai_photo_returns_result_or_clear_error(self, base_url, owner_headers, menu):
        """AI photo endpoint must never return a raw 500 without detail.

        Whether the emergent LLM key delivers an image is out of our scope,
        but the endpoint must either return {image_url} or a JSON error
        with a meaningful `detail` string (400/422/502/503 acceptable).
        """
        r = requests.post(
            f"{base_url}/api/workspace/menus/{menu['menu_id']}/items/{menu['item_id']}/ai-photo",
            headers=owner_headers, json={}, timeout=180,
        )
        assert r.status_code != 404, "endpoint should exist"
        if r.status_code == 200:
            body = r.json()
            assert "image_url" in body, body
        else:
            # Must be JSON with meaningful detail
            try:
                body = r.json()
            except ValueError:
                pytest.fail(f"non-JSON error body: {r.text[:400]}")
            assert body.get("detail"), f"empty error detail (status={r.status_code})"


class TestAiImportEndpoint:
    def test_ai_import_endpoint_exists_and_validates_input(self, base_url, owner_headers):
        # Empty payload -> validation error, NOT 500
        r = requests.post(
            f"{base_url}/api/workspace/menus/ai-import",
            headers=owner_headers, json={}, timeout=30,
        )
        assert r.status_code in (400, 422), f"unexpected status {r.status_code}: {r.text[:400]}"

    def test_ai_import_tiny_image_returns_json_never_raw_500(self, base_url, owner_headers):
        # 1x1 PNG base64, expected to yield either an empty list or a graceful error
        tiny_png = base64.b64encode(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944"
                "415478da63f8cfc0000000030001005e01c0d40000000049454e44ae426082"
            )
        ).decode()
        r = requests.post(
            f"{base_url}/api/workspace/menus/ai-import",
            headers=owner_headers,
            json={"image_base64": tiny_png, "content_type": "image/png"},
            timeout=180,
        )
        assert r.status_code != 404
        try:
            body = r.json()
        except ValueError:
            pytest.fail(f"non-JSON body: {r.text[:400]}")
        if r.status_code == 200:
            assert "items" in body, body
        else:
            assert body.get("detail"), f"no detail on error (status={r.status_code}): {body}"
