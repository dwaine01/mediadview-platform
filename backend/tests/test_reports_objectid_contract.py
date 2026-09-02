"""Reports contracts: BI invoices JSON serialization and invoices.xlsx export validity."""

import json
import os

import pytest
import requests

# Module: CI/local endpoint first; public preview is an explicit fallback only.
BASE_URL = (
    os.environ.get("TEST_BASE_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
)


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("Missing EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL/TEST_BASE_URL")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def auth_token(base_url):
    response = requests.post(
        f"{base_url}/api/auth/v2/login",
        json={"email": "admin.demo@mediadview.com", "password": "AdminDemo#2026", "client_type": "native"},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Login failed: {response.status_code} {response.text[:200]}")
    token = (response.json() or {}).get("access_token")
    if not token:
        pytest.skip("No access_token returned")
    return token


# Module: BI invoices endpoint should not leak Mongo ObjectId details
def test_bi_invoices_has_no_objectid_leak(base_url, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = requests.get(f"{base_url}/api/admin/reports/bi/invoices?limit=50", headers=headers, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload and isinstance(payload["items"], list)

    for row in payload["items"]:
        assert "_id" not in row

    serialized = json.dumps(payload)
    assert "ObjectId(" not in serialized


# Module: invoices.xlsx export should be a valid XLSX zip payload
def test_invoices_xlsx_export_is_valid(base_url, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = requests.get(f"{base_url}/api/admin/reports/export/invoices.xlsx", headers=headers, timeout=30)
    assert response.status_code == 200
    assert "openxmlformats" in response.headers.get("content-type", "")
    assert len(response.content) > 100
    assert response.content[:2] == b"PK"
