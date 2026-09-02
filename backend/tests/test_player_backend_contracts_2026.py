"""Backend contract regression tests for Android player pipeline endpoints.

Scope: health, device registration idempotency, controlled empty playlist,
null-date campaign eligibility, player/media serving contract and playlist version.
"""

import base64
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient


def _public_base_url() -> str:
    env = dotenv_values("/app/frontend/.env")
    base_url = (
        os.environ.get("TEST_BASE_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or env.get("EXPO_PUBLIC_BACKEND_URL")
    )
    if not base_url:
        pytest.fail("TEST_BASE_URL/EXPO_PUBLIC_BACKEND_URL is missing")
    return base_url.rstrip("/")


BASE_URL = _public_base_url()
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def api_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def mongo_db():
    if not MONGO_URL or not DB_NAME:
        pytest.fail("MONGO_URL/DB_NAME missing in environment")
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        yield db
    finally:
        client.close()


# health module
def test_health_endpoint_contract(api_session):
    response = api_session.get(f"{BASE_URL}/api/health", timeout=20)
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "healthy", "service": "MediaView API"}


# pairing/register module
def test_device_register_is_idempotent_with_client_uuid(api_session, mongo_db):
    client_uuid = f"TEST-client-{uuid.uuid4().hex}"
    payload = {
        "client_uuid": client_uuid,
        "device_name": "TEST Contract Device",
        "device_model": "A40",
    }
    first = api_session.post(f"{BASE_URL}/api/devices/register", json=payload, timeout=20)
    second = api_session.post(f"{BASE_URL}/api/devices/register", json=payload, timeout=20)

    assert first.status_code == 200
    assert second.status_code == 200
    f_json, s_json = first.json(), second.json()
    assert f_json["device_id"] == s_json["device_id"]
    assert f_json["activation_code"] == s_json["activation_code"]

    mongo_db.devices.delete_many({"client_uuid": client_uuid})


# playlist contract module
def test_device_playlist_returns_controlled_empty_state_when_unpaired(api_session, mongo_db):
    client_uuid = f"TEST-unpaired-{uuid.uuid4().hex}"
    reg = api_session.post(
        f"{BASE_URL}/api/devices/register",
        json={"client_uuid": client_uuid, "device_name": "TEST Unpaired"},
        timeout=20,
    )
    assert reg.status_code == 200
    device_id = reg.json()["device_id"]

    response = api_session.get(f"{BASE_URL}/api/devices/{device_id}/playlist", timeout=20)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_activated"
    assert body["items"] == []

    mongo_db.devices.delete_many({"id": device_id})


def test_device_and_screen_playlist_fields_support_null_dates_and_media_contract(api_session, mongo_db):
    suffix = uuid.uuid4().hex[:10]
    screen_id = f"TEST-screen-{suffix}"
    device_id = f"TEST-device-{suffix}"
    media_id = f"TEST-media-{suffix}"
    campaign_id = f"TEST-campaign-{suffix}"

    # prepare a tiny valid PNG for legacy storage path
    media_dir = Path("/app/backend/media")
    media_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{media_id}.png"
    media_path = media_dir / stored_filename
    media_path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+AvzZVwAAAABJRU5ErkJggg=="))

    mongo_db.screens.insert_one(
        {
            "id": screen_id,
            "name": "TEST Screen",
            "specs": {"resolution": "1920x1080"},
            "playlist_version": 5,
        }
    )
    mongo_db.devices.insert_one(
        {
            "id": device_id,
            "screen_id": screen_id,
            "status": "active",
            "last_heartbeat": None,
        }
    )
    mongo_db.media.insert_one(
        {
            "id": media_id,
            "filename": "TEST-pixel.png",
            "content_type": "image/png",
            "size": media_path.stat().st_size,
            "storage": "legacy",
            "stored_filename": stored_filename,
            "status": "ready",
        }
    )
    mongo_db.campaigns.insert_one(
        {
            "id": campaign_id,
            "screen_id": screen_id,
            "status": "approved",
            "schedule": {
                "start_date": None,
                "end_date": None,
                "start_time": "00:00",
                "end_time": "23:59",
                "slot_duration": 15,
                "frequency": 5,
            },
            "media_ids": [media_id],
        }
    )

    try:
        device_playlist = api_session.get(f"{BASE_URL}/api/devices/{device_id}/playlist", timeout=20)
        assert device_playlist.status_code == 200
        d_body = device_playlist.json()
        assert d_body["total_items"] == 1
        item = d_body["items"][0]
        assert item["media_id"] == media_id
        assert item["media_url"] == f"/api/player/media/{media_id}"
        assert item["download_url"] == f"/api/player/media/{media_id}"
        assert len(item["checksum"]) == 64

        screen_playlist = api_session.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20)
        assert screen_playlist.status_code == 200
        s_body = screen_playlist.json()
        assert s_body["total_items"] == 1
        s_item = s_body["items"][0]
        assert s_item["media_url"] == s_item["download_url"]
        assert len(s_item["checksum"]) == 64
        assert s_body["playlist_version"] == 5
    finally:
        mongo_db.campaigns.delete_many({"id": campaign_id})
        mongo_db.media.delete_many({"id": media_id})
        mongo_db.devices.delete_many({"id": device_id})
        mongo_db.screens.delete_many({"id": screen_id})
        if media_path.exists():
            media_path.unlink()


def test_player_media_endpoint_serves_legacy_content(api_session, mongo_db):
    media_id = f"TEST-legacy-{uuid.uuid4().hex[:10]}"
    media_dir = Path("/app/backend/media")
    media_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{media_id}.jpg"
    media_path = media_dir / stored_filename
    payload = bytes.fromhex(
        "FFD8FFE000104A46494600010100000100010000FFDB004300080606070605080707"
        "07090908090C0A0B0A0B0A0C110C0D0C0D0C110D0E10101010100E10101011101112"
        "12131212111414141416161617171818181919191A1A1A1BFFC00011080001000103"
        "012200021101031101FFC4001F0000010501010101010100000000000000000102030405"
        "060708090A0BFFDA0008010100003F00D2CFFFD9"
    )
    media_path.write_bytes(payload)

    mongo_db.media.insert_one(
        {
            "id": media_id,
            "filename": "TEST-legacy.jpg",
            "content_type": "image/jpeg",
            "size": len(payload),
            "storage": "legacy",
            "stored_filename": stored_filename,
            "status": "ready",
        }
    )
    try:
        response = api_session.get(f"{BASE_URL}/api/player/media/{media_id}", timeout=20, allow_redirects=False)
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("image/jpeg")
        assert len(response.content) == len(payload)
    finally:
        mongo_db.media.delete_many({"id": media_id})
        if media_path.exists():
            media_path.unlink()


def test_playlist_version_never_goes_back_for_same_screen(api_session, mongo_db):
    screen_id = f"TEST-version-{uuid.uuid4().hex[:10]}"
    mongo_db.screens.insert_one({"id": screen_id, "name": "TEST Version", "playlist_version": 2})
    try:
        first = api_session.get(f"{BASE_URL}/api/player/{screen_id}/version", timeout=20)
        assert first.status_code == 200
        v1 = first.json()["playlist_version"]
        assert v1 == 2

        mongo_db.screens.update_one({"id": screen_id}, {"$inc": {"playlist_version": 3}})
        second = api_session.get(f"{BASE_URL}/api/player/{screen_id}/version", timeout=20)
        assert second.status_code == 200
        v2 = second.json()["playlist_version"]
        assert v2 >= v1
    finally:
        mongo_db.screens.delete_many({"id": screen_id})
