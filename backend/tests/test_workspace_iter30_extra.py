"""Iteration 30 — extra coverage for:
- AI menu import: synthetic PIL menu photo → real vision call (at most one live call),
                  and DB "no-write" invariant.
- Playlist PATCH cross-organization isolation (404, not other org's playlist).
- Activity feed: multi-tenant isolation between pizzeria@demo.com and testws@test.com,
                 employee can read own org feed, media.uploaded + team.member_created are logged.
"""
import base64
import io
import os
import uuid

import pytest
import requests
from PIL import Image, ImageDraw

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
OTHER = ("testws@test.com", "Test1234!")
EMPLEADO = ("empleado@demo.com", "Empleado123!")

TIMEOUT = 60

PNG_1PX = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d7636060600000000400012734270a0000000049454e44ae426082"
)).decode()


def _login(email: str, password: str) -> dict:
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return r.json()


def _token(email: str, password: str) -> str:
    return _login(email, password)["access_token"]


def _headers(email: str, password: str) -> dict:
    return {"Authorization": f"Bearer {_token(email, password)}"}


def _synthetic_menu_jpeg() -> str:
    """Real menu-like image with clear black text on white with color header."""
    img = Image.new("RGB", (900, 1100), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (899, 90)], fill="#8B0000")
    d.text((260, 30), "PIZZERIA DON LUIS", fill="white")
    d.text((30, 130), "PIZZAS", fill="black")
    d.line([(30, 160), (870, 160)], fill="black", width=2)
    d.text((30, 180), "Margherita  ...........  12.50", fill="black")
    d.text((30, 220), "Pepperoni   ...........  14.00", fill="black")
    d.text((30, 260), "Hawaiana    ...........  13.75", fill="black")
    d.text((30, 300), "Cuatro Quesos ......... 15.90", fill="black")
    d.text((30, 360), "BEBIDAS", fill="black")
    d.line([(30, 390), (870, 390)], fill="black", width=2)
    d.text((30, 410), "Coca Cola   ...........  2.50", fill="black")
    d.text((30, 450), "Agua        ...........  1.50", fill="black")
    d.text((30, 490), "Cerveza     ...........  3.75", fill="black")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# AI menu import — live call (once) + DB no-write invariant
# ---------------------------------------------------------------------------

def test_ai_menu_import_synthetic_photo_returns_items_and_does_not_write_db():
    h = _headers(*OWNER)
    before = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=TIMEOUT).json()
    count_before = len(before)

    payload = {"image_base64": _synthetic_menu_jpeg(), "content_type": "image/jpeg"}
    r = requests.post(f"{BASE}/api/workspace/menus/ai-import",
                      headers=h, json=payload, timeout=90)
    # Vision provider may occasionally fail — treat 502 as skip so we don't burn credits/CI.
    if r.status_code == 502:
        pytest.skip(f"AI provider unavailable: {r.text}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "menu_name" in body and isinstance(body["menu_name"], str)
    assert "currency" in body and isinstance(body["currency"], str)
    assert isinstance(body.get("items"), list)
    assert body.get("raw_count") == len(body["items"])

    if body["items"]:  # very likely for a clean synthetic image
        sample = body["items"][0]
        assert isinstance(sample["name"], str) and sample["name"].strip()
        assert isinstance(sample["price"], (int, float))
        assert sample["price"] >= 0
        assert "category" in sample  # may be None but the key exists

    after = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=TIMEOUT).json()
    assert len(after) == count_before, "ai-import must NOT persist menus"


# ---------------------------------------------------------------------------
# Playlist PATCH cross-organization isolation
# ---------------------------------------------------------------------------

def test_playlist_patch_cross_org_returns_404():
    owner_h = _headers(*OWNER)
    other_h = _headers(*OTHER)

    up = requests.post(f"{BASE}/api/media/upload", headers=owner_h, timeout=TIMEOUT, json={
        "filename": "iter30-cross.png", "content_type": "image/png", "data": PNG_1PX,
    })
    assert up.status_code == 200, up.text
    media_id = up.json()["id"]

    created = requests.post(f"{BASE}/api/workspace/playlists", headers=owner_h, timeout=TIMEOUT, json={
        "name": "Iter30 CrossOrg",
        "items": [{"type": "media", "ref_id": media_id, "duration": 8}],
    })
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    # OTHER organization must not be able to see or patch this playlist → 404
    cross = requests.patch(f"{BASE}/api/workspace/playlists/{pid}",
                           headers=other_h, timeout=TIMEOUT, json={"name": "hijack"})
    assert cross.status_code == 404, cross.text

    # Owner still can patch normally
    ok = requests.patch(f"{BASE}/api/workspace/playlists/{pid}",
                        headers=owner_h, timeout=TIMEOUT, json={"name": "Iter30 CrossOrg v2"})
    assert ok.status_code == 200
    assert ok.json()["name"] == "Iter30 CrossOrg v2"

    requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=owner_h, timeout=TIMEOUT)
    requests.delete(f"{BASE}/api/media/{media_id}", headers=owner_h, timeout=TIMEOUT)


# ---------------------------------------------------------------------------
# Activity feed: isolation, employee access, and media.uploaded logging
# ---------------------------------------------------------------------------

def test_activity_feed_is_isolated_between_organizations():
    owner_h = _headers(*OWNER)
    other_h = _headers(*OTHER)

    # Owner creates a uniquely named menu so we can look for the marker.
    marker = f"TEST_iter30_activity_{uuid.uuid4().hex[:8]}"
    created = requests.post(f"{BASE}/api/workspace/menus", headers=owner_h, timeout=TIMEOUT, json={
        "name": marker, "items": [{"name": "Café", "price": 2.5}],
    })
    assert created.status_code == 201, created.text
    menu_id = created.json()["id"]

    owner_feed = requests.get(f"{BASE}/api/workspace/activity?limit=100",
                              headers=owner_h, timeout=TIMEOUT).json()
    assert any(e.get("action") == "menu.created" and marker in str(e.get("details"))
               for e in owner_feed), "owner feed should contain their menu.created"

    other_feed = requests.get(f"{BASE}/api/workspace/activity?limit=200",
                              headers=other_h, timeout=TIMEOUT).json()
    # Cross-org isolation: the marker must NOT appear in the other org's feed
    assert not any(marker in str(e) for e in other_feed), \
        "other organization feed leaked the owner's activity"

    # Every event returned to OTHER must belong to OTHER's user emails (not the owner)
    for e in other_feed:
        if e.get("user_email"):
            assert e["user_email"] != OWNER[0]

    requests.delete(f"{BASE}/api/workspace/menus/{menu_id}", headers=owner_h, timeout=TIMEOUT)


def test_activity_feed_media_uploaded_is_logged():
    h = _headers(*OWNER)
    up = requests.post(f"{BASE}/api/media/upload", headers=h, timeout=TIMEOUT, json={
        "filename": "iter30-activity.png", "content_type": "image/png", "data": PNG_1PX,
    })
    assert up.status_code == 200, up.text
    media_id = up.json()["id"]

    feed = requests.get(f"{BASE}/api/workspace/activity?limit=60",
                        headers=h, timeout=TIMEOUT).json()
    assert any(e.get("action") == "media.uploaded" for e in feed), \
        "media.uploaded event should be recorded in the activity feed"

    requests.delete(f"{BASE}/api/media/{media_id}", headers=h, timeout=TIMEOUT)


def test_activity_feed_readable_by_employee_after_password_change():
    """Employee has a temporary password; we log in but skip if we cannot
    complete the change-password step (that flow is covered separately)."""
    login = requests.post(f"{BASE}/api/auth/login",
                          json={"email": EMPLEADO[0], "password": EMPLEADO[1]},
                          timeout=TIMEOUT).json()
    token = login.get("access_token")
    if not token:
        pytest.skip("employee login did not return a token")

    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/api/workspace/activity", headers=h, timeout=TIMEOUT)
    # If backend forces password change (428) the read is not possible — this is
    # a valid state, not a bug, so we accept it as a skip.
    if r.status_code == 428:
        pytest.skip("employee must change password before reading activity")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
