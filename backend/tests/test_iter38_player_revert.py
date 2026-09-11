"""iter38 — Regression suite for the player contract revert (bug user duarte).

Focus:
  1) /api/devices/{id}/check payload is frozen (no `server_url`) in both pending
     and active states.
  2) /api/admin/player-server (GET & POST) is gone → 404 / non-200.
  3) End-to-end player flow: register → check (pending) → connect → check (active)
     → playlist. Every playlist item MUST have non-empty media_id and download_url
     (otherwise the Kotlin parser silently drops the item and «no llega contenido»).
  4) R2 media chain: /api/player/media/{id} redirects 302; /api/media/serve?key=…
     returns 200 without auth.
"""
import uuid

import pytest
import requests

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}
ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}

BASE_KEYS_PENDING = {"device_id", "activation_code", "status", "screen_id",
                     "screen_name", "activated_at"}
KEYS_ACTIVE = BASE_KEYS_PENDING | {"screen_resolution"}


def _token(base_url, creds):
    r = requests.post(f"{base_url}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def owner_headers(base_url):
    return {"Authorization": f"Bearer {_token(base_url, OWNER)}"}


@pytest.fixture
def admin_headers(base_url):
    return {"Authorization": f"Bearer {_token(base_url, ADMIN)}"}


@pytest.fixture
def registered_device(base_url):
    client_uuid = f"pytest-iter38-{uuid.uuid4().hex[:10]}"
    r = requests.post(
        f"{base_url}/api/devices/register",
        json={"device_name": "iter38 TV", "device_model": "iter38", "client_uuid": client_uuid},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return {
        "device_id": data["device_id"],
        "device_token": data["device_token"],
        "activation_code": data["activation_code"],
        "client_uuid": client_uuid,
    }


@pytest.fixture
def paired(base_url, owner_headers, registered_device):
    conn = requests.post(
        f"{base_url}/api/workspace/screens/connect",
        headers=owner_headers,
        json={"activation_code": registered_device["activation_code"],
              "screen_name": f"iter38 {uuid.uuid4().hex[:6]}"},
        timeout=20,
    )
    assert conn.status_code == 200, conn.text
    screen_id = conn.json()["screen"]["id"]
    yield {**registered_device, "screen_id": screen_id}
    requests.delete(f"{base_url}/api/workspace/screens/{screen_id}",
                    headers=owner_headers, timeout=20)


# ─── 1. /check payload contract ───────────────────────────────────────────
class TestCheckContract:
    def test_pending_has_exactly_6_keys_no_server_url(self, base_url, registered_device):
        r = requests.get(f"{base_url}/api/devices/{registered_device['device_id']}/check",
                         timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert set(body) == BASE_KEYS_PENDING, (
            f"Contrato de /check roto (pending). "
            f"Extras: {set(body) - BASE_KEYS_PENDING} | Faltan: {BASE_KEYS_PENDING - set(body)}"
        )
        assert "server_url" not in body

    def test_active_has_7_keys_with_screen_resolution_no_server_url(self, base_url, paired):
        r = requests.get(f"{base_url}/api/devices/{paired['device_id']}/check", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "active"
        assert body["screen_id"] == paired["screen_id"]
        assert set(body) == KEYS_ACTIVE, (
            f"Contrato de /check roto (active). "
            f"Extras: {set(body) - KEYS_ACTIVE} | Faltan: {KEYS_ACTIVE - set(body)}"
        )
        assert "server_url" not in body


# ─── 2. /admin/player-server is gone ──────────────────────────────────────
class TestAdminPlayerServerRemoved:
    def test_get_returns_404_even_with_superadmin(self, base_url, admin_headers):
        r = requests.get(f"{base_url}/api/admin/player-server",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 404, (
            f"GET /api/admin/player-server debe estar removido; got {r.status_code}: {r.text[:200]}"
        )

    def test_post_is_not_200_even_with_superadmin(self, base_url, admin_headers):
        r = requests.post(f"{base_url}/api/admin/player-server",
                          headers=admin_headers, json={"server_url": "https://x"},
                          timeout=20)
        # Ideal: 404. Accept 405 (path exists only with other methods) as also-gone.
        assert r.status_code in (404, 405), (
            f"POST /api/admin/player-server debe estar removido; got {r.status_code}: {r.text[:200]}"
        )


# ─── 3. End-to-end player flow ────────────────────────────────────────────
class TestPlayerEndToEnd:
    def test_register_check_connect_check_playlist(self, base_url, owner_headers, registered_device):
        did = registered_device["device_id"]
        code = registered_device["activation_code"]
        dtok = registered_device["device_token"]

        # Step A: check pending
        r = requests.get(f"{base_url}/api/devices/{did}/check", timeout=20)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        assert r.json()["activation_code"] == code

        # Step B: connect from workspace owner
        conn = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": code, "screen_name": f"iter38 e2e {uuid.uuid4().hex[:6]}"},
            timeout=20,
        )
        assert conn.status_code == 200, conn.text
        screen_id = conn.json()["screen"]["id"]
        try:
            # Step C: check active
            r = requests.get(f"{base_url}/api/devices/{did}/check", timeout=20)
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "active"
            assert body["screen_id"] == screen_id
            assert body["screen_name"]

            # Step D: playlist with device token
            r = requests.get(
                f"{base_url}/api/devices/{did}/playlist",
                headers={"Authorization": f"Bearer {dtok}"},
                timeout=20,
            )
            assert r.status_code == 200, r.text
            pl = r.json()
            # Expected top-level keys the player uses
            for k in ("device_id", "screen_id", "screen_name", "items",
                      "total_items", "playlist_version"):
                assert k in pl, f"playlist payload missing key {k}: {list(pl)}"
            # Each item MUST have non-empty media_id AND download_url (Kotlin parser drops otherwise)
            for it in pl.get("items", []):
                assert it.get("media_id"), f"item without media_id: {it}"
                dl = it.get("download_url") or it.get("media_url")
                assert dl, f"item without download_url/media_url: {it}"
        finally:
            requests.delete(f"{base_url}/api/workspace/screens/{screen_id}",
                            headers=owner_headers, timeout=20)


# ─── 4. R2 media chain (only if there is an r2 media doc in the DB) ───────
class TestR2MediaChain:
    def _find_r2_media_id(self, mongo_db):
        doc = mongo_db.media.find_one({"storage": "r2", "r2_key": {"$exists": True, "$ne": None}},
                                      {"id": 1, "r2_key": 1})
        return doc

    def test_player_media_redirects_302_for_r2(self, base_url, mongo_db):
        doc = self._find_r2_media_id(mongo_db)
        if not doc:
            pytest.skip("No r2 media in this environment")
        r = requests.get(f"{base_url}/api/player/media/{doc['id']}",
                         allow_redirects=False, timeout=20)
        assert r.status_code in (302, 307), (
            f"Expected redirect for r2 media, got {r.status_code}"
        )
        loc = r.headers.get("location", "")
        assert loc, "Redirect without Location header"

    def test_media_serve_returns_200_without_auth(self, base_url, mongo_db):
        doc = self._find_r2_media_id(mongo_db)
        if not doc:
            pytest.skip("No r2 media in this environment")
        r = requests.get(f"{base_url}/api/media/serve", params={"key": doc["r2_key"]},
                         timeout=30, stream=True)
        assert r.status_code == 200, f"/api/media/serve without auth failed: {r.status_code} {r.text[:200]}"
        # ensure some bytes come out
        chunk = next(r.iter_content(chunk_size=1024), b"")
        assert chunk, "media serve returned no bytes"


# ─── 5. Route inventory snapshot sanity ───────────────────────────────────
class TestRouteInventory:
    def test_snapshot_total_is_493_and_no_player_server(self):
        import json
        import pathlib
        p = pathlib.Path("/app/backend/tests/route_inventory_snapshot.json")
        d = json.loads(p.read_text())
        # snapshot may be a list of route dicts or {routes: [...], total: N}
        if isinstance(d, dict):
            total = d.get("total")
            routes = d.get("routes", [])
        else:
            total = len(d)
            routes = d
        assert total == 493, f"expected 493 routes, got {total}"
        paths = {r.get("path") for r in routes}
        assert "/api/admin/player-server" not in paths
        assert "/api/workspace/screens/{screen_id}" in paths
