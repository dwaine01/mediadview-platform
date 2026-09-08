"""Iter31 — extra coverage: now-playing progression, AI photo end-to-end,
render safe_src rejections, and dayparting winners between two playlists."""

import os
import time

import pytest
import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
OTHER = ("testws@test.com", "Test1234!")


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    return body["access_token"], body.get("user", {})


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ------------------------- now-playing progresses over time -------------------------

def test_now_playing_progresses_over_time():
    tok, _ = _login(*OWNER)
    h = _auth(tok)
    first = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30).json()
    playing_first = [s for s in first if s.get("now_playing")]
    assert playing_first, "al menos una pantalla debe tener contenido en reproducción"
    time.sleep(3.0)
    second = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30).json()
    by_id = {s["screen_id"]: s for s in second}

    advanced = False
    for s in playing_first:
        b = by_id.get(s["screen_id"])
        if not b or not b.get("now_playing"):
            continue
        a = s["now_playing"]
        c = b["now_playing"]
        if c["index"] != a["index"] or c["seconds_left"] < a["seconds_left"]:
            advanced = True
            break
    assert advanced, "seconds_left debería bajar o el index cambiar tras esperar 3s"


# ------------------------- render rejects javascript: and //host -------------------------

def test_menu_render_safe_src_rejects_dangerous_urls(monkeypatch):
    tok, _ = _login(*OWNER)
    h = _auth(tok)
    from server import _safe_src  # type: ignore
    assert _safe_src("javascript:alert(1)") == ""
    assert _safe_src("JavaScript:alert(1)") == ""
    assert _safe_src("//evil.com/x.png") == ""
    assert _safe_src("vbscript:msgbox") == ""
    # allowed
    assert _safe_src("/api/player/media/abc").endswith("/api/player/media/abc")
    assert _safe_src("https://cdn.example.com/x.png").endswith("x.png")


def test_menu_render_html_never_contains_javascript_uri():
    tok, _ = _login(*OWNER)
    h = _auth(tok)
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]
    page = requests.get(f"{BASE}/api/menus/{menu['id']}/render", headers=h, timeout=30)
    assert page.status_code == 200
    assert "javascript:" not in page.text.lower()


# ------------------------- dayparting: two playlists, only one live -------------------------

def _make_playlist(h, name, menu_id):
    r = requests.post(f"{BASE}/api/workspace/playlists", headers=h, timeout=30, json={
        "name": name, "items": [{"type": "menu", "ref_id": menu_id, "duration": 10}],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _publish(h, pid, screen_id):
    r = requests.post(f"{BASE}/api/workspace/playlists/{pid}/publish", headers=h, timeout=30,
                      json={"screen_ids": [screen_id]})
    assert r.status_code in (200, 201), r.text


def test_dayparting_winner_is_in_window_playlist():
    tok, _ = _login(*OWNER)
    h = _auth(tok)
    from datetime import datetime, timedelta

    menus = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()
    menu_id = menus[0]["id"]
    screens = requests.get(f"{BASE}/api/workspace/screens", headers=h, timeout=30).json()
    assert screens, "necesitamos al menos una pantalla"
    screen_id = screens[0]["id"]

    p_in = _make_playlist(h, "Iter31 IN window", menu_id)
    p_out = _make_playlist(h, "Iter31 OUT window", menu_id)
    try:
        now = datetime.utcnow()
        # window covers current UTC hour ±1h → UTC tz to avoid regional drift
        start = (now - timedelta(hours=1)).strftime("%H:%M")
        end = (now + timedelta(hours=1)).strftime("%H:%M")
        far_start = (now + timedelta(hours=3)).strftime("%H:%M")
        far_end = (now + timedelta(hours=5)).strftime("%H:%M")
        all_days = [0, 1, 2, 3, 4, 5, 6]

        r = requests.patch(f"{BASE}/api/workspace/playlists/{p_in}", headers=h, timeout=30, json={
            "schedule": {"mode": "scheduled", "start_time": start, "end_time": end,
                          "days": all_days, "timezone": "UTC"}, "priority": 50,
        })
        assert r.status_code == 200

        r = requests.patch(f"{BASE}/api/workspace/playlists/{p_out}", headers=h, timeout=30, json={
            "schedule": {"mode": "scheduled", "start_time": far_start, "end_time": far_end,
                          "days": all_days, "timezone": "UTC"}, "priority": 50,
        })
        assert r.status_code == 200

        _publish(h, p_in, screen_id)
        _publish(h, p_out, screen_id)

        rows = requests.get(f"{BASE}/api/workspace/schedules", headers=h, timeout=30).json()
        by_id = {r["id"]: r for r in rows}
        assert by_id[p_in]["in_window"] is True
        assert by_id[p_out]["in_window"] is False
        # live_now should ONLY be true for the one whose window covers now
        assert by_id[p_in]["live_now"] is True, by_id[p_in]
        assert by_id[p_out]["live_now"] is False, by_id[p_out]
        # both are published so status must be 'live' or similar (not draft)
        assert by_id[p_in]["status"] != "draft"
    finally:
        # cleanup: unpublish + delete
        for pid in (p_in, p_out):
            try:
                requests.post(f"{BASE}/api/workspace/playlists/{pid}/unpublish", headers=h,
                              timeout=30, json={"screen_ids": [screen_id]})
            except Exception:
                pass
            requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=h, timeout=30)


# ------------------------- AI photo end-to-end (ONE real call, guarded) -------------------------

@pytest.mark.skipif(os.environ.get("MV_SKIP_AI") == "1", reason="skip real AI (credits)")
def test_ai_photo_full_flow_real_generation():
    tok, _ = _login(*OWNER)
    h = _auth(tok)
    menus = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()
    menu = menus[0]
    # pick first item WITHOUT image_url; if none, pick first item anyway
    target = next((i for i in menu["items"] if not i.get("image_url")), menu["items"][0])
    item_id = target["id"]

    r = requests.post(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item_id}/ai-photo",
                       headers=h, timeout=180)
    if r.status_code == 502:
        pytest.skip(f"AI provider error, no cobrable: {r.text[:120]}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "image_url" in body and body["image_url"].startswith("/api/player/media/")
    assert "media_id" in body and body["media_id"]
    media_id = body["media_id"]

    # media downloadable with 200 + non-empty binary
    mres = requests.get(f"{BASE}/api/player/media/{media_id}", timeout=30)
    assert mres.status_code == 200, mres.status_code
    assert mres.headers.get("content-type", "").startswith("image/")
    assert len(mres.content) > 1024, "imagen sospechosamente pequeña"

    # menu item now has image_url and media_id persisted
    updated = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()
    updated_item = None
    for m in updated:
        if m["id"] != menu["id"]:
            continue
        for it in m["items"]:
            if it["id"] == item_id:
                updated_item = it
                break
    assert updated_item is not None
    assert updated_item.get("image_url") == body["image_url"]
    assert updated_item.get("media_id") == media_id

    # activity log has menu_item.ai_photo event
    events = requests.get(f"{BASE}/api/workspace/activity", headers=h, timeout=30).json()
    kinds = [e.get("action") or e.get("event") or e.get("type") for e in events]
    assert "menu_item.ai_photo" in kinds, kinds[:10]


# ------------------------- now-playing accessible by employee (temp password bypass) -------------------------

def test_now_playing_accessible_by_manager_after_password_change():
    """Manager gerente@demo.com may still have a temp password → 428. In that case, skip.
    Otherwise: confirm they can query now-playing (workspace user is not just OWNER)."""
    r = requests.post(f"{BASE}/api/auth/login",
                       json={"email": "gerente@demo.com", "password": "Gerente123!"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login gerente falló: {r.status_code}")
    body = r.json()
    if body.get("user", {}).get("must_change_password") or body.get("must_change_password"):
        # Manager still on temp password — workspace endpoints will return 428 by design
        h = {"Authorization": f"Bearer {body['access_token']}"}
        np = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30)
        assert np.status_code in (428, 401, 403)
        pytest.skip("manager con contraseña temporal — comportamiento esperado 428")
    h = {"Authorization": f"Bearer {body['access_token']}"}
    np = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30)
    assert np.status_code == 200, np.text
