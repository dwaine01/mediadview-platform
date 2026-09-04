"""
Tests for SaaS Self-Service Onboarding:
- POST /api/auth/signup (free plan, paid plan graceful, duplicate email, short pw, missing fields)
- GET /api/sign-up and GET /api/sign-up?plan=standard (HTML pages)
- GET /api/landing (HTML page with pricing)
- POST /api/admin/create-client (superadmin token)
- GET /api/health
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://menu-studio-3.preview.emergentagent.com").rstrip("/")

TEST_EMAIL_FREE = f"TEST_saas_free_{int(time.time())}@example.com"
TEST_EMAIL_STANDARD = f"TEST_saas_std_{int(time.time())}@example.com"
TEST_EMAIL_DUPLICATE = f"TEST_saas_dup_{int(time.time())}@example.com"
TEST_CLIENT_EMAIL = f"TEST_client_{int(time.time())}@example.com"

SUPERADMIN_EMAIL = "superadmin@mediadview.com"
SUPERADMIN_PASSWORD = "SuperAdmin#2026"

@pytest.fixture(scope="module")
def superadmin_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPERADMIN_EMAIL,
        "password": SUPERADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Superadmin login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"No token in response: {data}"
    return token


class TestHealth:
    """Health check"""
    def test_health(self):
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("healthy", "ok", "running"), f"Unexpected health: {data}"
        print(f"PASS health: {data}")


class TestHTMLPages:
    """HTML page endpoints"""
    def test_get_signup_page(self):
        resp = requests.get(f"{BASE_URL}/api/sign-up")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "<form" in resp.text.lower() or "sign" in resp.text.lower()
        print("PASS GET /api/sign-up")

    def test_get_signup_page_plan_standard(self):
        resp = requests.get(f"{BASE_URL}/api/sign-up?plan=standard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "standard" in resp.text.lower()
        print("PASS GET /api/sign-up?plan=standard")

    def test_get_landing_page(self):
        resp = requests.get(f"{BASE_URL}/api/landing")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        # Should contain pricing section
        content = resp.text.lower()
        assert "pric" in content or "plan" in content or "free" in content
        print("PASS GET /api/landing")


class TestSignupFreePlan:
    """POST /api/auth/signup - free plan"""
    def test_signup_free_plan(self):
        resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "name": "TEST Free User",
            "email": TEST_EMAIL_FREE,
            "password": "Password123!",
            "plan": "free",
            "company_name": "TEST Company Free"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data or "user_id" in data, f"No id in response: {data}"
        assert data.get("email") == TEST_EMAIL_FREE.lower()
        assert data.get("plan") == "free"
        assert data.get("name") == "TEST Free User"
        print(f"PASS signup free: {data}")


class TestSignupStandardPlan:
    """POST /api/auth/signup - standard plan (Stripe placeholder -> graceful degradation)"""
    def test_signup_standard_pending(self):
        resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "name": "TEST Standard User",
            "email": TEST_EMAIL_STANDARD,
            "password": "Password123!",
            "plan": "standard",
            "company_name": "TEST Company Standard"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("pending_payment") is True, f"Expected pending_payment=true: {data}"
        print(f"PASS signup standard (pending_payment): {data}")


class TestSignupValidation:
    """POST /api/auth/signup - validation errors"""
    def test_signup_duplicate_email(self):
        payload = {
            "name": "TEST Dup User",
            "email": TEST_EMAIL_DUPLICATE,
            "password": "Password123!",
            "plan": "free",
            "company_name": "TEST Company Dup"
        }
        # First signup
        r1 = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        assert r1.status_code == 200, f"First signup failed: {r1.status_code} {r1.text}"
        # Duplicate
        r2 = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        assert r2.status_code == 409, f"Expected 409 for duplicate, got {r2.status_code}: {r2.text}"
        print("PASS signup duplicate -> 409")

    def test_signup_short_password(self):
        resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "name": "TEST Short PW",
            "email": f"TEST_short_{int(time.time())}@example.com",
            "password": "abc",
            "plan": "free",
            "company_name": "TEST Co"
        })
        assert resp.status_code == 400, f"Expected 400 for short pw, got {resp.status_code}: {resp.text}"
        print("PASS signup short pw -> 400")

    def test_signup_missing_fields(self):
        resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "name": "TEST Missing"
            # missing email and password
        })
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"
        print(f"PASS signup missing fields -> {resp.status_code}")


class TestAdminCreateClient:
    """POST /api/admin/create-user - superadmin token required (endpoint is create-user, not create-client)"""
    def test_create_client(self, superadmin_token):
        resp = requests.post(
            f"{BASE_URL}/api/admin/create-user",
            json={
                "name": "TEST Client Corp",
                "email": TEST_CLIENT_EMAIL,
                "password": "ClientPass123!",
                "company_name": "TEST Corp"
            },
            headers={"Authorization": f"Bearer {superadmin_token}"}
        )
        assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("email") == TEST_CLIENT_EMAIL.lower()
        print(f"PASS admin create-user: {data}")

    def test_create_client_no_auth(self):
        resp = requests.post(
            f"{BASE_URL}/api/admin/create-user",
            json={
                "name": "TEST Unauth",
                "email": f"TEST_unauth_{int(time.time())}@example.com",
                "password": "ClientPass123!"
            }
        )
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}: {resp.text}"
        print(f"PASS admin create-user no auth -> {resp.status_code}")
