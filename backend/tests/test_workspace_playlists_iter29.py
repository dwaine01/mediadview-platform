"""Iteración 29 — playlists del workspace + subida de contenido."""
import base64
import io
import os

import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"

PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d7636060600000000400012734270a0000000049454e44ae426082"
)).decode()


def _token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def test_workspace_playlist_flow():
    h = {"Authorization": f"Bearer {_token()}"}

    up = requests.post(f"{BASE}/api/media/upload", headers=h, timeout=60, json={
        "filename": "iter29-test.png", "content_type": "image/png", "data": PNG,
    })
    assert up.status_code == 200, up.text
    media_id = up.json()["id"]

    lib = requests.get(f"{BASE}/api/workspace/media", headers=h, timeout=30)
    assert lib.status_code == 200
    assert any(m["id"] == media_id for m in lib.json())

    created = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30, json={
        "name": "Iter29 Test Playlist",
        "items": [{"type": "media", "ref_id": media_id, "duration": 12}],
    })
    assert created.status_code == 201, created.text
    pl = created.json()
    assert pl["status"] == "draft" and len(pl["items"]) == 1

    listed = requests.get(f"{BASE}/api/workspace/playlists", headers=h, timeout=30)
    assert listed.status_code == 200
    assert any(p["id"] == pl["id"] for p in listed.json()), "draft must be listed"

    pub = requests.post(f"{BASE}/api/workspace/playlists/{pl['id']}/publish",
                        headers=h, timeout=30, json={"screen_ids": []})
    assert pub.status_code == 200, pub.text
    assert len(pub.json()["screen_ids"]) >= 1

    bad = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30, json={
        "name": "Bad", "items": [{"type": "media", "ref_id": "does-not-exist"}],
    })
    assert bad.status_code == 404

    unnamed = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30,
                            json={"name": "  ", "items": []})
    assert unnamed.status_code == 400

    delete = requests.delete(f"{BASE}/api/workspace/playlists/{pl['id']}", headers=h, timeout=30)
    assert delete.status_code == 200

    requests.delete(f"{BASE}/api/media/{media_id}", headers=h, timeout=30)


def test_cross_tenant_playlist_is_hidden():
    h = {"Authorization": f"Bearer {_token()}"}
    other = requests.post(f"{BASE}/api/auth/login", timeout=30,
                          json={"email": "testws@test.com", "password": "Test1234!"})
    if other.status_code != 200:
        return
    h2 = {"Authorization": f"Bearer {other.json()['access_token']}"}
    made = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30, json={
        "name": "Tenant A only", "items": [],
    })
    assert made.status_code == 201
    pid = made.json()["id"]
    seen = requests.get(f"{BASE}/api/workspace/playlists", headers=h2, timeout=30).json()
    assert all(p["id"] != pid for p in seen)
    denied = requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=h2, timeout=30)
    assert denied.status_code == 404
    requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30)
