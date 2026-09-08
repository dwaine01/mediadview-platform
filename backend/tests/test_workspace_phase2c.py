"""
Phase 2C P1 - Workspace API tests
Tests: /api/workspace/context, screens, menus, billing, connect
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://menu-studio-3.preview.emergentagent.com")
EMAIL = "testws@test.com"
PASSWORD = "Test1234!"

@pytest.fixture(scope="module")
def auth_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestWorkspaceContext:
    """Workspace context endpoint"""

    def test_context_returns_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/context", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_context_has_required_fields(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/context", headers=auth_headers)
        data = resp.json()
        assert "organization" in data
        assert "stats" in data
        assert "current_user" in data

    def test_context_stats_structure(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/context", headers=auth_headers)
        stats = resp.json()["stats"]
        assert "screens" in stats
        assert "users" in stats
        assert "devices" in stats

    def test_context_no_id_field(self, auth_headers):
        """Ensure _id (MongoDB objectId) is not exposed"""
        resp = requests.get(f"{BASE_URL}/api/workspace/context", headers=auth_headers)
        data = resp.json()
        assert "_id" not in data.get("organization", {})


class TestWorkspaceScreens:
    """Workspace screens endpoints"""

    def test_list_screens_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/screens", headers=auth_headers)
        assert resp.status_code == 200, resp.text

    def test_list_screens_returns_list(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/screens", headers=auth_headers)
        assert isinstance(resp.json(), list)

    def test_create_screen(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/workspace/screens", json={"name": "TEST_Screen_P2C"}, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "TEST_Screen_P2C"
        assert "id" in data
        return data["id"]

    def test_create_screen_missing_name(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/workspace/screens", json={}, headers=auth_headers)
        assert resp.status_code == 400


class TestWorkspaceMenus:
    """Workspace menus CRUD"""

    menu_id = None

    def test_list_menus_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/menus", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)

    def test_create_menu(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/workspace/menus",
                             json={"name": "TEST_Menu_P2C", "description": "Test menu"},
                             headers=auth_headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "TEST_Menu_P2C"
        TestWorkspaceMenus.menu_id = data["id"]

    def test_get_menu(self, auth_headers):
        if not TestWorkspaceMenus.menu_id:
            pytest.skip("No menu created")
        resp = requests.get(f"{BASE_URL}/api/workspace/menus/{TestWorkspaceMenus.menu_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_add_menu_item(self, auth_headers):
        if not TestWorkspaceMenus.menu_id:
            pytest.skip("No menu created")
        resp = requests.post(f"{BASE_URL}/api/workspace/menus/{TestWorkspaceMenus.menu_id}/items",
                             json={"name": "TEST_Item", "price": 9.99, "description": "Test item"},
                             headers=auth_headers)
        assert resp.status_code == 201, resp.text

    def test_publish_menu(self, auth_headers):
        if not TestWorkspaceMenus.menu_id:
            pytest.skip("No menu created")
        resp = requests.post(f"{BASE_URL}/api/workspace/menus/{TestWorkspaceMenus.menu_id}/publish",
                             json={}, headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_menu(self, auth_headers):
        if not TestWorkspaceMenus.menu_id:
            pytest.skip("No menu created")
        resp = requests.delete(f"{BASE_URL}/api/workspace/menus/{TestWorkspaceMenus.menu_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_deleted_menu_404(self, auth_headers):
        if not TestWorkspaceMenus.menu_id:
            pytest.skip("No menu created")
        resp = requests.get(f"{BASE_URL}/api/workspace/menus/{TestWorkspaceMenus.menu_id}", headers=auth_headers)
        assert resp.status_code == 404


class TestWorkspaceBilling:
    """Workspace billing endpoints"""

    def test_billing_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/billing", headers=auth_headers)
        assert resp.status_code == 200, resp.text

    def test_billing_has_subscription(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/billing", headers=auth_headers)
        data = resp.json()
        # subscription may be present
        assert "subscription" in data or "plan_config" in data

    def test_screen_cost_preview(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/workspace/billing/screen-cost?additional_screens=1", headers=auth_headers)
        # May return 200 or 400 if no pricing agreement — both acceptable
        assert resp.status_code in (200, 400), resp.text


class TestWorkspaceConnect:
    """Connect screen with activation code"""

    def test_connect_invalid_code_404(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/workspace/screens/connect",
                             json={"activation_code": "XXXXXX", "screen_name": "TEST_Connect"},
                             headers=auth_headers)
        assert resp.status_code == 404, resp.text

    def test_connect_short_code_400(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/workspace/screens/connect",
                             json={"activation_code": "ABC", "screen_name": "TEST_Connect"},
                             headers=auth_headers)
        assert resp.status_code == 400


class TestUnauthorized:
    """Without auth token should 401/403"""

    def test_context_no_auth(self):
        resp = requests.get(f"{BASE_URL}/api/workspace/context")
        assert resp.status_code in (401, 403)

    def test_screens_no_auth(self):
        resp = requests.get(f"{BASE_URL}/api/workspace/screens")
        assert resp.status_code in (401, 403)
