"""Iteración 31 — pantalla en vivo, fotos con IA y menú por horario."""
import os

import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
OTHER = ("testws@test.com", "Test1234!")


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_now_playing_reports_current_item_per_screen():
    h = _login(*OWNER)
    res = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30)
    assert res.status_code == 200, res.text
    screens = res.json()
    assert screens, "la pizzería demo debe tener pantallas"
    for screen in screens:
        assert {"screen_id", "screen_name", "is_online", "cycle_seconds", "now_playing"} <= set(screen)
        np = screen["now_playing"]
        if np:
            assert np["index"] >= 1 and np["index"] <= np["total"]
            assert np["kind"] in ("image", "video", "menu")
            assert 0 <= np["seconds_left"] <= np["duration"]
            assert np["duration"] > 0

    # tenant isolation: another org never sees these screens
    other = _login(*OTHER)
    mine = {s["screen_id"] for s in screens}
    theirs = {s["screen_id"] for s in requests.get(f"{BASE}/api/workspace/now-playing", headers=other, timeout=30).json()}
    assert mine.isdisjoint(theirs)


def test_menu_render_uses_flat_items_and_relative_photos():
    """Regression: workspace menus store a flat item list — the renderer used to 500."""
    h = _login(*OWNER)
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]
    page = requests.get(f"{BASE}/api/menus/{menu['id']}/render", headers=h, timeout=30)
    assert page.status_code == 200, page.text[:200]
    assert "cat-title" in page.text
    with_photo = [i for i in menu["items"] if i.get("image_url")]
    if with_photo:
        assert with_photo[0]["image_url"] in page.text, "las fotos relativas deben sobrevivir a _safe_src"


def test_playlist_schedule_and_dayparting_view():
    h = _login(*OWNER)
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]

    created = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30, json={
        "name": "Iter31 Desayuno", "items": [{"type": "menu", "ref_id": menu["id"], "duration": 15}],
    })
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["schedule"]["mode"] == "always"

    scheduled = requests.patch(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30, json={
        "schedule": {"mode": "scheduled", "start_time": "06:00", "end_time": "11:00",
                     "days": [0, 1, 2, 3, 4], "timezone": "America/New_York"},
        "priority": 30,
    })
    assert scheduled.status_code == 200, scheduled.text
    body = scheduled.json()
    assert body["schedule"]["mode"] == "scheduled"
    assert body["schedule"]["start_time"] == "06:00"
    assert body["schedule"]["days"] == [0, 1, 2, 3, 4]
    assert body["priority"] == 30

    rows = requests.get(f"{BASE}/api/workspace/schedules", headers=h, timeout=30)
    assert rows.status_code == 200
    row = next(r for r in rows.json() if r["id"] == pid)
    assert row["schedule"]["start_time"] == "06:00"
    assert row["priority"] == 30
    assert isinstance(row["in_window"], bool)
    assert isinstance(row["live_now"], bool)
    assert row["status"] == "draft"

    # priority is clamped and schedules are normalised
    clamped = requests.patch(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30,
                             json={"priority": 999, "schedule": {"mode": "nonsense"}})
    assert clamped.status_code == 200
    assert clamped.json()["priority"] == 100
    assert clamped.json()["schedule"]["mode"] == "always"

    requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30)


def test_ai_photo_permissions_and_404s():
    h = _login(*OWNER)
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]
    item_id = menu["items"][0]["id"]

    assert requests.post(f"{BASE}/api/workspace/menus/{menu['id']}/items/no-such-item/ai-photo",
                         headers=h, timeout=60).status_code == 404
    assert requests.post(f"{BASE}/api/workspace/menus/no-such-menu/items/{item_id}/ai-photo",
                         headers=h, timeout=60).status_code == 404

    other = _login(*OTHER)
    assert requests.post(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item_id}/ai-photo",
                         headers=other, timeout=60).status_code == 404
    assert requests.post(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item_id}/ai-photo",
                         timeout=60).status_code in (401, 403)
