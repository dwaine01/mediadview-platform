"""Iteración 30 — editar playlist (orden/duración), registro de actividad e importar menú con IA."""
import base64
import os
import uuid

import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")

PNG_1PX = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d7636060600000000400012734270a0000000049454e44ae426082"
)).decode()


def _token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": OWNER[0], "password": OWNER[1]}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_playlist_reorder_and_durations():
    h = {"Authorization": f"Bearer {_token()}"}

    media_ids = []
    for i in range(2):
        up = requests.post(f"{BASE}/api/media/upload", headers=h, timeout=60, json={
            "filename": f"iter30-{i}.png", "content_type": "image/png", "data": PNG_1PX,
        })
        assert up.status_code == 200, up.text
        media_ids.append(up.json()["id"])

    created = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30, json={
        "name": "Iter30 Orden",
        "items": [{"type": "media", "ref_id": mid, "duration": 10} for mid in media_ids],
    })
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    # reorder (swap) + change durations
    patched = requests.patch(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30, json={
        "name": "Iter30 Orden v2",
        "items": [
            {"type": "media", "ref_id": media_ids[1], "duration": 25},
            {"type": "media", "ref_id": media_ids[0], "duration": 7},
        ],
    })
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["name"] == "Iter30 Orden v2"
    assert [i["ref_id"] for i in body["items"]] == [media_ids[1], media_ids[0]]
    assert [i["duration"] for i in body["items"]] == [25, 7]
    assert [i["order"] for i in body["items"]] == [0, 1]
    assert body["version"] == 2

    # durations are clamped to a minimum of 3s
    clamped = requests.patch(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30, json={
        "items": [{"type": "media", "ref_id": media_ids[0], "duration": 1}],
    })
    assert clamped.status_code == 200
    assert clamped.json()["items"][0]["duration"] == 3

    # empty name rejected, unknown content rejected
    assert requests.patch(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30,
                          json={"name": "   "}).status_code == 400
    assert requests.patch(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30,
                          json={"items": [{"type": "media", "ref_id": "nope"}]}).status_code == 404
    assert requests.patch(f"{BASE}/api/workspace/playlists/{uuid.uuid4()}", headers=h, timeout=30,
                          json={"name": "x"}).status_code == 404

    requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30)
    for mid in media_ids:
        requests.delete(f"{BASE}/api/media/{mid}", headers=h, timeout=30)


def test_activity_feed_records_who_and_what():
    h = {"Authorization": f"Bearer {_token()}"}

    menu = requests.post(f"{BASE}/api/workspace/menus", headers=h, timeout=30, json={
        "name": "Iter30 Actividad", "items": [{"name": "Café", "price": 2.5}],
    })
    assert menu.status_code == 201
    menu_id = menu.json()["id"]
    item_id = menu.json()["items"][0]["id"]

    price_change = requests.put(f"{BASE}/api/workspace/menus/{menu_id}/items/{item_id}",
                                headers=h, timeout=30, json={"price": 3.75})
    assert price_change.status_code == 200

    feed = requests.get(f"{BASE}/api/workspace/activity?limit=40", headers=h, timeout=30)
    assert feed.status_code == 200
    events = feed.json()
    actions = [e["action"] for e in events]
    assert "menu.created" in actions
    assert "menu_item.updated" in actions

    price_event = next(e for e in events if e["action"] == "menu_item.updated")
    assert price_event["user_email"] == OWNER[0]
    assert price_event["details"]["price_from"] == 2.5
    assert price_event["details"]["price_to"] == 3.75
    assert price_event["created_at"]

    requests.delete(f"{BASE}/api/workspace/menus/{menu_id}", headers=h, timeout=30)


def test_ai_menu_import_input_validation():
    h = {"Authorization": f"Bearer {_token()}"}

    bad_type = requests.post(f"{BASE}/api/workspace/menus/ai-import", headers=h, timeout=30, json={
        "image_base64": PNG_1PX, "content_type": "application/pdf",
    })
    assert bad_type.status_code == 400

    bad_data = requests.post(f"{BASE}/api/workspace/menus/ai-import", headers=h, timeout=30, json={
        "image_base64": "no-es-base64!!" * 4, "content_type": "image/png",
    })
    assert bad_data.status_code == 400

    anon = requests.post(f"{BASE}/api/workspace/menus/ai-import", timeout=30, json={
        "image_base64": PNG_1PX, "content_type": "image/png",
    })
    assert anon.status_code in (401, 403)
