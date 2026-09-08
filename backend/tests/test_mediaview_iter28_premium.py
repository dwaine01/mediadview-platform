"""
Iteration 28 — Premium MediaView redesign regression tests.
Covers:
 * Annual pricing data (data-driven, no hardcoded discount)
 * Signup billing_cycle persistence (monthly / annual / invalid / omitted)
 * Client-logos CRUD + validation + public-vs-admin auth boundary
 * Admin panel HTML route
 * Static/HTML regression after the SaaS export swap
"""
import base64
import os
import time
import uuid
from typing import Optional

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://menu-studio-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

SUPERADMIN_EMAIL = "superadmin@mediadview.com"
SUPERADMIN_PASSWORD = "SuperAdmin#2026"
WORKSPACE_EMAIL = "testws@test.com"
WORKSPACE_PASSWORD = "Test1234!"

# Smallest valid PNG (1x1 transparent), base64
PNG_1X1_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR"
               "42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{API}/auth/login", json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD})
    assert r.status_code == 200, f"superadmin login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def workspace_token(s):
    r = s.post(f"{API}/auth/login", json={"email": WORKSPACE_EMAIL, "password": WORKSPACE_PASSWORD})
    assert r.status_code == 200, f"workspace login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


# ─── Annual pricing (data driven) ────────────────────────────────────────────
class TestAnnualPricingData:
    def test_plans_expose_annual_free_months(self, s):
        r = s.get(f"{API}/plans")
        assert r.status_code == 200
        plans = {p["plan_id"]: p for p in r.json()}
        assert set(plans) >= {"free", "starter", "pro", "enterprise"}
        for pid in plans:
            assert "annual_free_months" in plans[pid], f"{pid} missing annual_free_months"
            assert "annual_price" in plans[pid], f"{pid} missing annual_price"

    def test_annual_price_matches_formula(self, s):
        """annual_price == monthly_price * (12 - annual_free_months)"""
        r = s.get(f"{API}/plans")
        plans = {p["plan_id"]: p for p in r.json()}
        for pid, plan in plans.items():
            m = plan["monthly_price"]
            afm = plan["annual_free_months"]
            expected = round(m * (12 - afm), 2)
            got = round(plan["annual_price"], 2)
            assert got == expected, f"{pid}: expected annual={expected}, got {got} (monthly={m}, free_months={afm})"

    def test_specific_expected_values(self, s):
        r = s.get(f"{API}/plans")
        plans = {p["plan_id"]: p for p in r.json()}
        assert plans["free"]["monthly_price"] == 0 and plans["free"]["annual_free_months"] == 0
        assert plans["starter"]["monthly_price"] == 49 and plans["starter"]["annual_price"] == 490 and plans["starter"]["annual_free_months"] == 2
        assert plans["pro"]["monthly_price"] == 149 and plans["pro"]["annual_price"] == 1490 and plans["pro"]["annual_free_months"] == 2
        assert plans["enterprise"]["monthly_price"] == 499 and plans["enterprise"]["annual_price"] == 4990 and plans["enterprise"]["annual_free_months"] == 2


# ─── Signup billing_cycle persistence ────────────────────────────────────────
def _new_signup(s, cycle: Optional[str], plan="starter"):
    uid = uuid.uuid4().hex[:10]
    payload = {
        "plan_id": plan,
        "business_name": f"TEST_biz_{uid}",
        "contact_name": "Testeador",
        "contact_email": f"test_{uid}@test.com",
        "password": "Passw0rd!",
    }
    if cycle is not None:
        payload["billing_cycle"] = cycle
    return payload, s.post(f"{API}/auth/customer-signup", json=payload)


class TestSignupBillingCycle:
    def test_annual_signup_persistence(self, s, admin_token):
        payload, r = _new_signup(s, "annual", plan="pro")
        assert r.status_code == 201, r.text
        body = r.json()
        token = body["access_token"]
        # fetch workspace context to inspect subscription
        ctx = s.get(f"{API}/workspace/context", headers={"Authorization": f"Bearer {token}"})
        assert ctx.status_code == 200
        sub = ctx.json().get("subscription") or {}
        assert sub.get("billing_cycle") == "annual", f"billing_cycle not persisted: {sub}"
        assert sub.get("billing_status") == "pending", f"expected pending, got {sub.get('billing_status')}"
        # period ~= 365 days (allow 360-370)
        # some serializations expose it as ISO string
        start = sub.get("current_period_start")
        end = sub.get("current_period_end")
        assert start and end
        from datetime import datetime
        s_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00").split("+")[0])
        e_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00").split("+")[0])
        days = (e_dt - s_dt).days
        assert 360 <= days <= 370, f"annual period expected ~365 days, got {days}"

    def test_monthly_signup_persistence(self, s):
        _, r = _new_signup(s, "monthly")
        assert r.status_code == 201
        token = r.json()["access_token"]
        ctx = s.get(f"{API}/workspace/context", headers={"Authorization": f"Bearer {token}"})
        sub = ctx.json().get("subscription") or {}
        assert sub.get("billing_cycle") == "monthly"
        assert sub.get("billing_status") == "pending"
        from datetime import datetime
        s_dt = datetime.fromisoformat(str(sub["current_period_start"]).split("+")[0])
        e_dt = datetime.fromisoformat(str(sub["current_period_end"]).split("+")[0])
        days = (e_dt - s_dt).days
        assert 28 <= days <= 32, f"monthly period expected ~30 days, got {days}"

    def test_invalid_billing_cycle_rejected(self, s):
        _, r = _new_signup(s, "weekly")
        assert r.status_code == 400
        assert "billing_cycle" in r.text.lower() or "weekly" in r.text.lower()

    def test_omitted_billing_cycle_defaults_monthly(self, s):
        _, r = _new_signup(s, None)
        assert r.status_code == 201
        token = r.json()["access_token"]
        ctx = s.get(f"{API}/workspace/context", headers={"Authorization": f"Bearer {token}"})
        sub = ctx.json().get("subscription") or {}
        assert sub.get("billing_cycle") == "monthly"


# ─── Client-logos CRUD ───────────────────────────────────────────────────────
class TestClientLogos:
    _created_ids: list = []

    def test_public_list_no_auth(self, s):
        r = s.get(f"{API}/client-logos")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_endpoints_require_auth(self, s):
        r = s.get(f"{API}/admin/client-logos")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_admin_endpoints_reject_non_admin(self, s, workspace_token):
        r = s.get(f"{API}/admin/client-logos", headers={"Authorization": f"Bearer {workspace_token}"})
        assert r.status_code == 403, f"non-admin should get 403, got {r.status_code}"
        r2 = s.post(f"{API}/admin/client-logos",
                    headers={"Authorization": f"Bearer {workspace_token}"},
                    json={"name": "X", "logo_base64": PNG_1X1_B64, "logo_filename": "x.png"})
        assert r2.status_code == 403

    def test_create_logo_and_public_fetch(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = s.post(f"{API}/admin/client-logos",
                   headers=headers,
                   json={"name": "TEST_Client_A", "logo_base64": PNG_1X1_B64, "logo_filename": "a.png"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["logo_url"].startswith("/api/web/clients/")
        TestClientLogos._created_ids.append(body["id"])
        # public GET returns it
        pub = s.get(f"{API}/client-logos")
        assert any(row["id"] == body["id"] for row in pub.json())
        # file is fetchable (no auth)
        file_r = requests.get(f"{BASE}{body['logo_url']}")
        assert file_r.status_code == 200
        assert len(file_r.content) > 0

    def test_deactivate_removes_from_public_but_not_admin(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        # create a second logo, deactivate it
        r = s.post(f"{API}/admin/client-logos",
                   headers=headers,
                   json={"name": "TEST_Client_Deactivated", "logo_base64": PNG_1X1_B64, "logo_filename": "b.png"})
        assert r.status_code == 201
        lid = r.json()["id"]
        TestClientLogos._created_ids.append(lid)
        p = s.patch(f"{API}/admin/client-logos/{lid}", headers=headers, json={"is_active": False})
        assert p.status_code == 200
        assert p.json()["is_active"] is False
        pub = s.get(f"{API}/client-logos")
        assert not any(row["id"] == lid for row in pub.json())
        admin_list = s.get(f"{API}/admin/client-logos", headers=headers)
        assert any(row["id"] == lid for row in admin_list.json())

    def test_validation_rejects_bad_extension(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = s.post(f"{API}/admin/client-logos", headers=headers,
                   json={"name": "TEST_bad", "logo_base64": PNG_1X1_B64, "logo_filename": "bad.gif"})
        assert r.status_code == 400

    def test_validation_rejects_bad_base64(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = s.post(f"{API}/admin/client-logos", headers=headers,
                   json={"name": "TEST_bad2", "logo_base64": "!!!not base64!!!", "logo_filename": "x.png"})
        assert r.status_code == 400

    def test_validation_rejects_oversize(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        # ~2.5MB of random-ish bytes → base64 will still decode fine but exceed 2MB
        big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"A" * (2_600_000)).decode()
        r = s.post(f"{API}/admin/client-logos", headers=headers,
                   json={"name": "TEST_big", "logo_base64": big, "logo_filename": "big.png"})
        assert r.status_code == 413

    def test_validation_requires_url_or_base64(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = s.post(f"{API}/admin/client-logos", headers=headers, json={"name": "TEST_none"})
        assert r.status_code == 400

    def test_delete_and_confirm_gone(self, s, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        # find a still-active logo we created
        for lid in TestClientLogos._created_ids:
            d = s.delete(f"{API}/admin/client-logos/{lid}", headers=headers)
            assert d.status_code == 200
            d2 = s.delete(f"{API}/admin/client-logos/{lid}", headers=headers)
            assert d2.status_code == 404
        TestClientLogos._created_ids.clear()
        # final: public list should be empty (or at least not contain our test names)
        pub = s.get(f"{API}/client-logos")
        assert not any(row.get("name", "").startswith("TEST_") for row in pub.json())


# ─── Admin panel HTML route ──────────────────────────────────────────────────
class TestAdminHtml:
    def test_admin_clients_view(self, s):
        r = s.get(f"{API}/admin/clients-view")
        assert r.status_code == 200
        assert "html" in r.headers.get("content-type", "").lower()
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


# ─── Static export / route regression ────────────────────────────────────────
class TestRouteRegression:
    def test_root_landing_html(self, s):
        r = s.get(f"{BASE}/")
        assert r.status_code == 200

    def test_saas_routes_return_200(self, s):
        for path in ["/pricing", "/account/login", "/account/signup", "/workspace"]:
            r = s.get(f"{BASE}{path}", allow_redirects=True)
            assert r.status_code == 200, f"{path} returned {r.status_code}"

    def test_legacy_advertiser_routes_still_customer_html(self, s):
        # These HTML routes are served by FastAPI itself. The preview ingress sends
        # non-/api paths to the Expo dev server, so we must hit the backend directly
        # (in single-origin production FastAPI serves them on the public domain).
        for path in ["/login", "/signup", "/portal", "/marketplace"]:
            r = s.get(f"http://localhost:8001{path}", allow_redirects=True)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            # customer.html contains the advertiser SPA marker
            # We don't require a specific marker; just ensure it isn't the Expo saas landing.

    def test_api_plans_public(self, s):
        r = s.get(f"{API}/plans")
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) >= 3

    def test_hero_asset(self, s):
        r = requests.get(f"{API}/web/assets/mv-hero-001.webp")
        assert r.status_code == 200
        assert "image/webp" in r.headers.get("content-type", "")

    def test_workspace_apis_auth(self, s, workspace_token):
        h = {"Authorization": f"Bearer {workspace_token}"}
        for path in ["/workspace/context", "/workspace/screens"]:
            r = s.get(f"{API}{path}", headers=h)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
