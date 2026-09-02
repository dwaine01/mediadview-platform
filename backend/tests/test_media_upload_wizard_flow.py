"""Media wizard backend regression tests (auth + upload validation + persistence)."""

import base64
import os

import pytest
import requests
from dotenv import load_dotenv


# Module: Base URL resolution from env (public preview first)
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("TEST_BASE_URL")
)


# Module: Test credentials (explicitly from local test credentials doc)
SUPERADMIN_EMAIL = "superadmin@mediadview.com"
SUPERADMIN_PASSWORD = "SuperAdmin#2026"


# 1x1 PNG (valid image bytes)
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAgMBgJc8lGgAAAAASUVORK5CYII="
)


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("Missing EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL/TEST_BASE_URL")
    return BASE_URL.rstrip("/")


@pytest.fixture
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def auth_token(api_client, base_url):
    resp = api_client.post(
        f"{base_url}/api/auth/login",
        json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip(f"Auth failed for test user: {resp.status_code} {resp.text}")
    token = (resp.json() or {}).get("access_token")
    if not token:
        pytest.skip("No access_token from /api/auth/login")
    return token


# Module: Upload endpoint health for media wizard (Create -> GET -> DELETE)
def test_media_upload_png_persists_and_is_retrievable(api_client, base_url, auth_token):
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    payload = {
        "filename": "TEST_wizard_valid.png",
        "content_type": "image/png",
        "data": PNG_B64,
    }
    create = api_client.post(f"{base_url}/api/media/upload", json=payload, timeout=60)
    assert create.status_code == 200
    body = create.json()
    assert body["filename"] == payload["filename"]
    assert body["content_type"] == "image/png"
    media_id = body["id"]

    get_meta = api_client.get(f"{base_url}/api/media/{media_id}", timeout=30)
    assert get_meta.status_code == 200
    meta = get_meta.json()
    assert meta["id"] == media_id
    assert meta["filename"] == payload["filename"]

    get_file = api_client.get(f"{base_url}/api/media/{media_id}/file", timeout=30, allow_redirects=False)
    assert get_file.status_code in (200, 302)

    delete = api_client.delete(f"{base_url}/api/media/{media_id}", timeout=30)
    assert delete.status_code == 200


# Module: Magic-byte/content-type mismatch hardening behavior
def test_media_upload_rejects_mime_spoof(api_client, base_url, auth_token):
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    # Bytes are PNG, declared as JPEG -> should be rejected by validate_magic_bytes
    payload = {
        "filename": "TEST_spoof.jpg",
        "content_type": "image/jpeg",
        "data": PNG_B64,
    }
    resp = api_client.post(f"{base_url}/api/media/upload", json=payload, timeout=60)
    assert resp.status_code == 415
    detail = (resp.json() or {}).get("detail", "")
    assert "does not match" in detail or "Upload rejected" in detail
