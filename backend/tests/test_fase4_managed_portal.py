"""
Fase 4 — MediaView Managed Portal: Backend API Tests
=====================================================
Tests 1-13 from the Phase 4 review request:
  • MANAGED_VIEWER login + token fields
  • Managed Dashboard / Screens / Requests CRUD
  • RBAC guards (403 on admin routes for MANAGED_VIEWER)
  • Admin list/update requests
  • Audit logs
  • Admin managed summary
"""
import os
import pytest
import requests
from tests.conftest import BASE_URL  # type: ignore

# ── Credentials ──────────────────────────────────────────────────────────────
SUPERADMIN_EMAIL = "superadmin@mediadview.com"
SUPERADMIN_PASS  = "SuperAdmin#2026"
MANAGED_EMAIL    = "managed.viewer@demo.mediaview.com"
MANAGED_PASS     = "ManagedView#2026"
MANAGED_ORG_ID   = "org_managed_demo_v4"

# ── Shared helpers ────────────────────────────────────────────────────────────

def _login(email, password, client_type="native"):
    r = requests.post(
        f"{BASE_URL}/api/auth/v2/login",
        json={"email": email, "password": password, "client_type": client_type},
        timeout=10,
    )
    return r


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def managed_token():
    """Login as MANAGED_VIEWER and return access token."""
    r = _login(MANAGED_EMAIL, MANAGED_PASS)
    if r.status_code != 200:
        pytest.skip(f"MANAGED_VIEWER login failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def superadmin_token():
    """Login as SUPER_ADMIN and return access token."""
    r = _login(SUPERADMIN_EMAIL, SUPERADMIN_PASS)
    if r.status_code != 200:
        pytest.skip(f"SuperAdmin login failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def created_request_id(managed_token):
    """Create a change request as MANAGED_VIEWER and return its id."""
    r = requests.post(
        f"{BASE_URL}/api/managed/requests",
        json={
            "title": "TEST_ Phase4 content update",
            "request_type": "CONTENT_UPDATE",
            "description": "TEST_ Please update lobby screen content for Q2 campaign.",
            "priority": "HIGH",
        },
        headers=_headers(managed_token),
        timeout=10,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"Could not create request: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1: MANAGED_VIEWER Login
# ══════════════════════════════════════════════════════════════════════════════
class TestManagedViewerLogin:
    """TEST 1 — Login as MANAGED_VIEWER returns correct role and org."""

    def test_login_returns_200(self):
        r = _login(MANAGED_EMAIL, MANAGED_PASS)
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"

    def test_login_returns_access_token(self):
        r = _login(MANAGED_EMAIL, MANAGED_PASS)
        assert r.status_code == 200
        j = r.json()
        assert "access_token" in j and j["access_token"], "access_token missing"

    def test_login_returns_rbac_role_managed_viewer(self):
        r = _login(MANAGED_EMAIL, MANAGED_PASS)
        assert r.status_code == 200
        j = r.json()
        user = j.get("user", j)  # token might be in top level or in user key
        rbac_role = user.get("rbac_role") or j.get("rbac_role")
        assert rbac_role == "MANAGED_VIEWER", f"Expected MANAGED_VIEWER, got {rbac_role}"

    def test_login_returns_correct_organization_id(self):
        r = _login(MANAGED_EMAIL, MANAGED_PASS)
        assert r.status_code == 200
        j = r.json()
        user = j.get("user", j)
        org_id = user.get("organization_id") or j.get("organization_id")
        assert org_id == MANAGED_ORG_ID, f"Expected org {MANAGED_ORG_ID}, got {org_id}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2: Managed Dashboard
# ══════════════════════════════════════════════════════════════════════════════
class TestManagedDashboard:
    """TEST 2 — /api/managed/dashboard returns proper KPIs."""

    def test_dashboard_200(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/dashboard", headers=_headers(managed_token))
        assert r.status_code == 200, r.text[:300]

    def test_dashboard_has_total_screens_ge_2(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/dashboard", headers=_headers(managed_token))
        assert r.status_code == 200
        j = r.json()
        assert j.get("total_screens", 0) >= 2, f"total_screens={j.get('total_screens')}"

    def test_dashboard_has_total_locations_ge_1(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/dashboard", headers=_headers(managed_token))
        assert r.status_code == 200
        j = r.json()
        assert j.get("total_locations", 0) >= 1, f"total_locations={j.get('total_locations')}"

    def test_dashboard_shape(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/dashboard", headers=_headers(managed_token))
        j = r.json()
        for field in ("total_screens", "online_screens", "offline_screens", "total_locations",
                      "active_content", "pending_requests", "screens_status"):
            assert field in j, f"missing field: {field}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3: Managed Screens
# ══════════════════════════════════════════════════════════════════════════════
class TestManagedScreens:
    """TEST 3 — /api/managed/screens returns list with >=2 screens."""

    def test_screens_200(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/screens", headers=_headers(managed_token))
        assert r.status_code == 200, r.text[:300]

    def test_screens_ge_2(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/screens", headers=_headers(managed_token))
        assert r.status_code == 200
        screens = r.json()
        assert isinstance(screens, list), "Expected list"
        assert len(screens) >= 2, f"Expected >=2 screens, got {len(screens)}"

    def test_screens_have_expected_fields(self, managed_token):
        r = requests.get(f"{BASE_URL}/api/managed/screens", headers=_headers(managed_token))
        screens = r.json()
        if screens:
            s = screens[0]
            for field in ("id", "name", "device_status"):
                assert field in s, f"Screen missing field: {field}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4: Create Change Request
# ══════════════════════════════════════════════════════════════════════════════
class TestCreateChangeRequest:
    """TEST 4 — POST /api/managed/requests returns status=PENDING."""

    def test_create_request_201_or_200(self, managed_token):
        r = requests.post(
            f"{BASE_URL}/api/managed/requests",
            json={
                "title": "TEST_ Lobby screen update",
                "request_type": "CONTENT_UPDATE",
                "description": "TEST_ Please update the content on the lobby screen.",
                "priority": "NORMAL",
            },
            headers=_headers(managed_token),
            timeout=10,
        )
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:300]}"

    def test_create_request_returns_pending(self, managed_token):
        r = requests.post(
            f"{BASE_URL}/api/managed/requests",
            json={
                "title": "TEST_ Status check request",
                "request_type": "OTHER",
                "description": "TEST_ Checking that status defaults to PENDING.",
                "priority": "LOW",
            },
            headers=_headers(managed_token),
        )
        assert r.status_code in (200, 201)
        j = r.json()
        assert j.get("status") == "PENDING", f"Expected PENDING, got {j.get('status')}"

    def test_create_request_has_id(self, managed_token):
        r = requests.post(
            f"{BASE_URL}/api/managed/requests",
            json={
                "title": "TEST_ ID presence check",
                "request_type": "TECHNICAL_ISSUE",
                "description": "TEST_ Checking that id is returned.",
                "priority": "URGENT",
            },
            headers=_headers(managed_token),
        )
        assert r.status_code in (200, 201)
        j = r.json()
        assert "id" in j and j["id"], "Request must have an id"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5: List Own Requests
# ══════════════════════════════════════════════════════════════════════════════
class TestListOwnRequests:
    """TEST 5 — GET /api/managed/requests returns requests array."""

    def test_list_requests_200(self, managed_token, created_request_id):
        r = requests.get(f"{BASE_URL}/api/managed/requests", headers=_headers(managed_token))
        assert r.status_code == 200, r.text[:300]

    def test_list_requests_is_list(self, managed_token, created_request_id):
        r = requests.get(f"{BASE_URL}/api/managed/requests", headers=_headers(managed_token))
        assert isinstance(r.json(), list), "Expected list"

    def test_list_requests_contains_created_request(self, managed_token, created_request_id):
        r = requests.get(f"{BASE_URL}/api/managed/requests", headers=_headers(managed_token))
        ids = [req["id"] for req in r.json()]
        assert created_request_id in ids, f"Created request {created_request_id} not in list"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6: RBAC Guard — MANAGED_VIEWER cannot access admin routes
# ══════════════════════════════════════════════════════════════════════════════
class TestRBACGuard:
    """TEST 6 — MANAGED_VIEWER gets 403 on admin routes."""

    def test_managed_viewer_cannot_list_admin_requests(self, managed_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/managed/requests",
            headers=_headers(managed_token),
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7: Admin List Requests
# ══════════════════════════════════════════════════════════════════════════════
class TestAdminListRequests:
    """TEST 7 — GET /api/admin/managed/requests with superadmin returns all requests."""

    def test_admin_list_requests_200(self, superadmin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/managed/requests",
            headers=_headers(superadmin_token),
        )
        assert r.status_code == 200, r.text[:300]

    def test_admin_list_requests_is_list(self, superadmin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/managed/requests",
            headers=_headers(superadmin_token),
        )
        assert isinstance(r.json(), list)

    def test_admin_list_includes_managed_org_requests(self, superadmin_token, created_request_id):
        r = requests.get(
            f"{BASE_URL}/api/admin/managed/requests",
            headers=_headers(superadmin_token),
        )
        ids = [req["id"] for req in r.json()]
        assert created_request_id in ids, f"Created request not visible to admin"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 8: Admin Update Request to IN_PROGRESS
# ══════════════════════════════════════════════════════════════════════════════
class TestAdminUpdateRequest:
    """TEST 8 — PATCH /api/admin/managed/requests/{id} updates status."""

    def test_admin_update_to_in_progress(self, superadmin_token, created_request_id):
        r = requests.patch(
            f"{BASE_URL}/api/admin/managed/requests/{created_request_id}",
            json={"status": "IN_PROGRESS", "admin_notes": "Working on it"},
            headers=_headers(superadmin_token),
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        j = r.json()
        assert j.get("status") == "IN_PROGRESS", f"Status mismatch: {j.get('status')}"
        assert j.get("admin_notes") == "Working on it", f"admin_notes mismatch: {j.get('admin_notes')}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 9: Admin Update to COMPLETED
# ══════════════════════════════════════════════════════════════════════════════
class TestAdminCompleteRequest:
    """TEST 9 — PATCH to COMPLETED."""

    def test_admin_update_to_completed(self, superadmin_token, created_request_id):
        # Ensure it's IN_PROGRESS first (idempotent setup)
        requests.patch(
            f"{BASE_URL}/api/admin/managed/requests/{created_request_id}",
            json={"status": "IN_PROGRESS"},
            headers=_headers(superadmin_token),
        )
        r = requests.patch(
            f"{BASE_URL}/api/admin/managed/requests/{created_request_id}",
            json={"status": "COMPLETED"},
            headers=_headers(superadmin_token),
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        j = r.json()
        assert j.get("status") == "COMPLETED", f"Expected COMPLETED, got {j.get('status')}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 10: Audit Log
# ══════════════════════════════════════════════════════════════════════════════
class TestAuditLog:
    """TEST 10 — GET /api/admin/audit-logs returns request.created and request.status_updated."""

    def test_audit_logs_200(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/audit-logs", headers=_headers(superadmin_token))
        assert r.status_code == 200, r.text[:300]

    def test_audit_logs_is_array(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/audit-logs", headers=_headers(superadmin_token))
        assert isinstance(r.json(), list)

    def test_audit_log_has_request_created(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/audit-logs?limit=200", headers=_headers(superadmin_token))
        actions = [log.get("action") for log in r.json()]
        assert "request.created" in actions, f"No request.created in audit logs. Actions found: {set(actions)}"

    def test_audit_log_has_request_status_updated(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/audit-logs?limit=200", headers=_headers(superadmin_token))
        actions = [log.get("action") for log in r.json()]
        assert "request.status_updated" in actions, f"No request.status_updated in audit logs. Actions found: {set(actions)}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 11: RBAC Screen Create Block
# ══════════════════════════════════════════════════════════════════════════════
class TestRBACScreenCreate:
    """TEST 11 — MANAGED_VIEWER cannot POST /api/admin/screens."""

    def test_managed_viewer_cannot_create_screen(self, managed_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json={"name": "TEST_ Unauthorized Screen", "location": {"city": "Miami"}},
            headers=_headers(managed_token),
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 12: RBAC Media Upload Block
# ══════════════════════════════════════════════════════════════════════════════
class TestRBACMediaUpload:
    """TEST 12 — MANAGED_VIEWER cannot POST /api/media/upload."""

    def test_managed_viewer_cannot_upload_media(self, managed_token):
        import base64
        _PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")
        r = requests.post(
            f"{BASE_URL}/api/media/upload",
            json={"filename": "test.png", "content_type": "image/png", "data": _PNG_B64},
            headers=_headers(managed_token),
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 13: Admin Managed Summary
# ══════════════════════════════════════════════════════════════════════════════
class TestAdminManagedSummary:
    """TEST 13 — GET /api/admin/managed/summary returns correct fields."""

    def test_summary_200(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/managed/summary", headers=_headers(superadmin_token))
        assert r.status_code == 200, r.text[:300]

    def test_summary_has_required_fields(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/managed/summary", headers=_headers(superadmin_token))
        j = r.json()
        for field in ("managed_screens", "managed_viewers", "pending", "total_requests"):
            assert field in j, f"Missing field: {field}"

    def test_summary_managed_viewers_ge_1(self, superadmin_token):
        r = requests.get(f"{BASE_URL}/api/admin/managed/summary", headers=_headers(superadmin_token))
        j = r.json()
        assert j.get("managed_viewers", 0) >= 1, f"managed_viewers={j.get('managed_viewers')}"
