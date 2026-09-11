"""
Backend regression tests for the MEDIAVIEW premium redesign (iteration 27).
Covers:
  - GET /api/plans (public plans, Spanish features, Pro highlight = "Más Popular")
  - GET /api/workspace/context (stats: devices, devices_online, devices_offline)
  - Workspace list endpoints (regression after workspace_routes.py edit + timedelta import)
  - Static assets under /api/web/assets (webp)
  - GET /api/landing (production homepage HTML)
"""
import os
import re

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://sprint1-signage.preview.emergentagent.com").rstrip("/")
EMAIL = "testws@test.com"
PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Plans API ----------
class TestPlansAPI:
    def test_plans_public(self):
        r = requests.get(f"{BASE_URL}/api/plans", timeout=15)
        assert r.status_code == 200
        plans = r.json()
        assert isinstance(plans, list)
        ids = {p["plan_id"] for p in plans}
        assert {"free", "starter", "pro", "enterprise"}.issubset(ids)

    def test_plans_spanish_features_and_pro_highlight(self):
        plans = requests.get(f"{BASE_URL}/api/plans", timeout=15).json()
        # Spanish detection: features should include "pantalla" / "almacenamiento" / "reproductor"
        for p in plans:
            feats = " ".join(p.get("features", [])).lower()
            assert "pantalla" in feats or "reproductor" in feats or "almacenamiento" in feats, f"Non-Spanish features in {p['plan_id']}: {feats}"
        pro = next(p for p in plans if p["plan_id"] == "pro")
        assert pro["highlight"] is True
        assert pro["highlight_text"] == "Más Popular", f"Unexpected pro highlight: {pro['highlight_text']}"

    def test_plans_no_mongo_id(self):
        plans = requests.get(f"{BASE_URL}/api/plans", timeout=15).json()
        for p in plans:
            assert "_id" not in p


# ---------- Workspace context ----------
class TestWorkspaceContext:
    def test_context_has_extended_stats(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/workspace/context", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "stats" in data
        stats = data["stats"]
        for k in ("screens", "users", "devices", "devices_online", "devices_offline"):
            assert k in stats, f"missing stat key: {k}"
            assert isinstance(stats[k], int), f"{k} not int"
        assert stats["devices_offline"] == max(0, stats["devices"] - stats["devices_online"])

    def test_context_no_500(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/workspace/context", headers=auth_headers, timeout=15)
        assert r.status_code != 500


# ---------- Workspace list endpoints regression ----------
class TestWorkspaceRegression:
    @pytest.mark.parametrize("ep", ["screens", "menus", "playlists", "schedules", "users", "billing", "media", "devices"])
    def test_list_endpoint_ok(self, ep, auth_headers):
        r = requests.get(f"{BASE_URL}/api/workspace/{ep}", headers=auth_headers, timeout=15)
        assert r.status_code == 200, f"{ep} -> {r.status_code} {r.text[:200]}"


# ---------- Static webp assets ----------
class TestStaticAssets:
    ASSETS = [
        "mv-hero-001", "mv-rest-pizza-sm", "mv-hero-002", "mv-ice-001-sm",
        "mv-mobile-001", "mv-player-001", "mv-env-lobby-sm",
    ]

    @pytest.mark.parametrize("asset", ASSETS)
    def test_asset_served(self, asset):
        r = requests.get(f"{BASE_URL}/api/web/assets/{asset}.webp", timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/webp")
        assert len(r.content) > 500


# ---------- Landing HTML ----------
class TestLandingHTML:
    def test_landing_200_html(self):
        r = requests.get(f"{BASE_URL}/api/landing", timeout=15)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "<html" in r.text.lower()

    def test_landing_contains_new_sections(self):
        html = requests.get(f"{BASE_URL}/api/landing", timeout=15).text
        # Some critical hooks the redesign relies on
        for tok in ["pt-minus", "pt-plus", "pt-n", "pt-amt", "pt-note", "ind-tabs", "ind-grid", "tpl-tabs", "tpl-grid"]:
            assert tok in html, f"missing landing element: {tok}"

    def test_landing_has_reveal_and_tv_frame(self):
        html = requests.get(f"{BASE_URL}/api/landing", timeout=15).text
        assert "mv-tv" in html
        assert "reveal" in html

    def test_landing_no_banned_colors(self):
        html = requests.get(f"{BASE_URL}/api/landing", timeout=15).text.lower()
        # Explicit ban: purple + ScreenCloud yellow (#7c3aed / #ffb800 / #ffcc00)
        assert "#7c3aed" not in html, "purple #7c3aed found in landing"
        assert "#6366f1" not in html, "indigo #6366f1 found in landing"
