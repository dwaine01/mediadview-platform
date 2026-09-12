"""Iteration 49 — per-item scheduling windows on playlists.

Covers:
- PATCH /api/workspace/playlists/{id} accepts/rejects starts_at/ends_at
- Backend filters items outside their window from /api/player/{screen_id}/playlist
- Contract keys (playlist_version / schedule_key) unchanged
- All-items-outside-window returns valid list (not 500)
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = (os.environ.get("EXPO_BACKEND_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or "https://sprint1-signage.preview.emergentagent.com").rstrip("/")

EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})

    # Media library — grab 2 media items
    media = s.get(f"{BASE}/api/workspace/media").json()
    assert len(media) >= 2, f"Need at least 2 media items in demo org, got {len(media)}"
    media_ids = [media[0]["id"], media[1]["id"]]

    screens = s.get(f"{BASE}/api/workspace/screens").json()
    assert len(screens) >= 1
    screen_id = screens[0]["id"]

    # Create playlist owned by test run
    tag = f"TEST_ITER49_{uuid.uuid4().hex[:6]}"
    r = s.post(f"{BASE}/api/workspace/playlists", json={
        "name": tag,
        "items": [
            {"type": "media", "ref_id": media_ids[0], "duration": 10},
            {"type": "media", "ref_id": media_ids[1], "duration": 10},
        ],
    })
    assert r.status_code == 201, r.text
    pl = r.json()
    playlist_id = pl["id"]

    # Publish to screen
    r = s.post(f"{BASE}/api/workspace/playlists/{playlist_id}/publish",
               json={"screen_ids": [screen_id]})
    assert r.status_code == 200, r.text

    yield {"session": s, "playlist_id": playlist_id, "screen_id": screen_id,
           "media_ids": media_ids, "tag": tag}

    # Cleanup
    s.delete(f"{BASE}/api/workspace/playlists/{playlist_id}")


def get_playlist(s, pid):
    r = s.get(f"{BASE}/api/workspace/playlists")
    assert r.status_code == 200
    return next(p for p in r.json() if p["id"] == pid)


# ── PATCH accepts ISO with Z, normalises to UTC without tz ──────────────
def test_patch_accepts_iso_and_returns_normalized(ctx):
    s = ctx["session"]
    starts = iso(datetime.now(timezone.utc) - timedelta(days=1))  # yesterday
    ends = iso(datetime.now(timezone.utc) + timedelta(days=1))    # tomorrow
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [
            {"type": "media", "ref_id": ctx["media_ids"][0], "duration": 10,
             "starts_at": starts, "ends_at": ends},
            {"type": "media", "ref_id": ctx["media_ids"][1], "duration": 10},
        ],
    })
    assert r.status_code == 200, r.text
    pl = get_playlist(s, ctx["playlist_id"])
    items = pl["items"]
    assert items[0]["starts_at"] is not None
    assert items[0]["ends_at"] is not None
    # Normalized: no Z, no +00:00
    assert "Z" not in items[0]["starts_at"]
    assert "+" not in items[0]["starts_at"]
    # Item 2 kept as null
    assert items[1]["starts_at"] is None
    assert items[1]["ends_at"] is None


def test_patch_invalid_date_400(ctx):
    s = ctx["session"]
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [{"type": "media", "ref_id": ctx["media_ids"][0],
                   "duration": 10, "ends_at": "mañana"}],
    })
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"


# ── Player endpoint filters by window ───────────────────────────────────
def test_player_shows_both_when_no_windows(ctx):
    s = ctx["session"]
    # Reset both items to no window
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [
            {"type": "media", "ref_id": ctx["media_ids"][0], "duration": 10},
            {"type": "media", "ref_id": ctx["media_ids"][1], "duration": 10},
        ],
    })
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/player/{ctx['screen_id']}/playlist")
    assert r.status_code == 200, r.text
    data = r.json()
    # Contract keys must remain
    assert "playlist_version" in data
    assert "schedule_key" in data
    assert "items" in data
    # Filter to our items only (screen might have other content)
    ours = [i for i in data["items"] if i.get("playlist_id") == ctx["playlist_id"]]
    assert len(ours) == 2, f"Expected 2, got {len(ours)}: {[i.get('filename') for i in ours]}"


def test_player_hides_past_ends_at(ctx):
    s = ctx["session"]
    yesterday = iso(datetime.now(timezone.utc) - timedelta(days=1))
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [
            {"type": "media", "ref_id": ctx["media_ids"][0], "duration": 10,
             "ends_at": yesterday},  # expired
            {"type": "media", "ref_id": ctx["media_ids"][1], "duration": 10},  # always
        ],
    })
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/player/{ctx['screen_id']}/playlist")
    assert r.status_code == 200
    ours = [i for i in r.json()["items"] if i.get("playlist_id") == ctx["playlist_id"]]
    assert len(ours) == 1, f"Only one item should survive; got {len(ours)}"


def test_player_hides_future_starts_at(ctx):
    s = ctx["session"]
    tomorrow = iso(datetime.now(timezone.utc) + timedelta(days=1))
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [
            {"type": "media", "ref_id": ctx["media_ids"][0], "duration": 10,
             "starts_at": tomorrow},  # future, not yet
            {"type": "media", "ref_id": ctx["media_ids"][1], "duration": 10},  # always
        ],
    })
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/player/{ctx['screen_id']}/playlist")
    assert r.status_code == 200
    ours = [i for i in r.json()["items"] if i.get("playlist_id") == ctx["playlist_id"]]
    assert len(ours) == 1


def test_player_shows_when_inside_window(ctx):
    s = ctx["session"]
    yesterday = iso(datetime.now(timezone.utc) - timedelta(days=1))
    tomorrow = iso(datetime.now(timezone.utc) + timedelta(days=1))
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [
            {"type": "media", "ref_id": ctx["media_ids"][0], "duration": 10,
             "starts_at": yesterday, "ends_at": tomorrow},
            {"type": "media", "ref_id": ctx["media_ids"][1], "duration": 10},
        ],
    })
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/player/{ctx['screen_id']}/playlist")
    assert r.status_code == 200
    ours = [i for i in r.json()["items"] if i.get("playlist_id") == ctx["playlist_id"]]
    assert len(ours) == 2


def test_all_items_outside_window_no_500(ctx):
    s = ctx["session"]
    yesterday = iso(datetime.now(timezone.utc) - timedelta(days=2))
    also_yesterday = iso(datetime.now(timezone.utc) - timedelta(days=1))
    r = s.patch(f"{BASE}/api/workspace/playlists/{ctx['playlist_id']}", json={
        "items": [
            {"type": "media", "ref_id": ctx["media_ids"][0], "duration": 10,
             "starts_at": yesterday, "ends_at": also_yesterday},
            {"type": "media", "ref_id": ctx["media_ids"][1], "duration": 10,
             "starts_at": yesterday, "ends_at": also_yesterday},
        ],
    })
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/player/{ctx['screen_id']}/playlist")
    assert r.status_code == 200, f"Must NEVER 500. got {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert isinstance(data.get("items"), list)
    ours = [i for i in data["items"] if i.get("playlist_id") == ctx["playlist_id"]]
    assert len(ours) == 0
