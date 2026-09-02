"""Auth failures must consistently return 401 so web refresh logic can recover."""

import os

import requests


BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


def test_missing_bearer_token_returns_401():
    response = requests.get(f"{BASE_URL}/api/playlists", timeout=20)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").lower() == "bearer"


def test_invalid_bearer_token_returns_401():
    response = requests.get(
        f"{BASE_URL}/api/playlists",
        headers={"Authorization": "Bearer invalid-token"},
        timeout=20,
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").lower() == "bearer"