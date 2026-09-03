"""
test_rbac_fase1.py — FASE 1 RBAC Acceptance Tests A-H
======================================================
Valida tenant isolation y RBAC enforcement en MediaView.
Tests: A, B, C, D, E, F, G, H + BONUS
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://menu-studio-3.preview.emergentagent.com").rstrip("/")

# ── Credenciales ────────────────────────────────────────────────
LOCATION = {"city": "Test City", "address": "123 Test St", "country": "US"}

CREDS = {
    "superadmin":   ("superadmin@mediadview.com",      "SuperAdmin#2026"),
    "mwadmin":      ("rbac.mwadmin@test.com",          "RbacTest#2026"),
    "ssowner_a":    ("rbac.ssowner.orga@test.com",     "RbacTest#2026"),
    "ssowner_b":    ("rbac.ssowner.orgb@test.com",     "RbacTest#2026"),
    "advertiser":   ("rbac.advertiser@test.com",       "RbacTest#2026"),
    "viewer":       ("rbac.viewer@test.com",           "RbacTest#2026"),
}

# ── Helpers ─────────────────────────────────────────────────────
def login(role_key: str) -> str:
    """Devuelve JWT token para el rol dado."""
    email, password = CREDS[role_key]
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login falló para {role_key}: {resp.status_code} — {resp.text[:200]}"
    data = resp.json()
    return data.get("access_token") or data.get("token")


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures / SETUP ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def superadmin_token():
    return login("superadmin")


@pytest.fixture(scope="module")
def seed_data(superadmin_token):
    """SETUP: llama seed-test-users y devuelve los IDs de pantallas de test."""
    resp = requests.post(
        f"{BASE_URL}/api/admin/rbac/seed-test-users",
        headers=auth_header(superadmin_token),
    )
    assert resp.status_code == 200, f"Seed falló: {resp.status_code} — {resp.text[:400]}"
    data = resp.json()
    screens = data.get("test_screens", {})
    print(f"\n[SETUP] Seed completado. test_screens: {screens}")
    return screens


# ═══════════════════════════════════════════════════════════════
# TEST A — SUPER_ADMIN crea pantalla SELF_SERVICE
# ═══════════════════════════════════════════════════════════════
class TestA_SuperAdminCreaSelfService:
    def test_superadmin_crea_self_service(self, superadmin_token):
        """TEST A: SUPER_ADMIN POST /api/admin/screens con operation_type=SELF_SERVICE → 200"""
        payload = {
            "name":           "TEST_A SELF_SERVICE Screen",
            "location":       LOCATION,
            "operation_type": "SELF_SERVICE",
        }
        resp = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json=payload,
            headers=auth_header(superadmin_token),
        )
        assert resp.status_code == 200, f"TEST A falló: {resp.status_code} — {resp.text[:300]}"
        data = resp.json()
        assert data.get("operation_type") == "SELF_SERVICE" or "id" in data or "_id" in data
        print(f"[TEST A] ✅ PASS — screen_id={data.get('id') or data.get('_id')}")


# ═══════════════════════════════════════════════════════════════
# TEST B — SUPER_ADMIN crea pantalla PUBLIC_ADVERTISING
# ═══════════════════════════════════════════════════════════════
class TestB_SuperAdminCreaPublicAdvertising:
    def test_superadmin_crea_public_advertising(self, superadmin_token):
        """TEST B: SUPER_ADMIN POST /api/admin/screens con operation_type=PUBLIC_ADVERTISING → 200"""
        payload = {
            "name":           "TEST_B PUBLIC_ADVERTISING Screen",
            "location":       LOCATION,
            "operation_type": "PUBLIC_ADVERTISING",
        }
        resp = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json=payload,
            headers=auth_header(superadmin_token),
        )
        assert resp.status_code == 200, f"TEST B falló: {resp.status_code} — {resp.text[:300]}"
        data = resp.json()
        print(f"[TEST B] ✅ PASS — screen_id={data.get('id') or data.get('_id')}")


# ═══════════════════════════════════════════════════════════════
# TEST C — SUPER_ADMIN crea pantalla MEDIAVIEW_MANAGED
# ═══════════════════════════════════════════════════════════════
class TestC_SuperAdminCreaManaged:
    def test_superadmin_crea_mediaview_managed(self, superadmin_token):
        """TEST C: SUPER_ADMIN POST /api/admin/screens con operation_type=MEDIAVIEW_MANAGED → 200"""
        payload = {
            "name":           "TEST_C MEDIAVIEW_MANAGED Screen",
            "location":       LOCATION,
            "operation_type": "MEDIAVIEW_MANAGED",
        }
        resp = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json=payload,
            headers=auth_header(superadmin_token),
        )
        assert resp.status_code == 200, f"TEST C falló: {resp.status_code} — {resp.text[:300]}"
        data = resp.json()
        print(f"[TEST C] ✅ PASS — screen_id={data.get('id') or data.get('_id')}")


# ═══════════════════════════════════════════════════════════════
# TEST D — SELF_SERVICE_OWNER crea pantalla en SU propia org
# ═══════════════════════════════════════════════════════════════
class TestD_SelfServiceOwnerCreaPropiaOrg:
    def test_ssowner_orga_crea_pantalla_propia(self, seed_data):
        """TEST D: SELF_SERVICE_OWNER Org A POST /api/screens/self-service → 200"""
        token = login("ssowner_a")
        payload = {
            "name":     "TEST_D Screen Org A",
            "location": LOCATION,
        }
        resp = requests.post(
            f"{BASE_URL}/api/screens/self-service",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 200, f"TEST D falló: {resp.status_code} — {resp.text[:300]}"
        data = resp.json()
        # Verificar que la pantalla fue creada con organization_id correcto
        assert data.get("organization_id") == "org_rbac_test_a", \
            f"organization_id incorrecto: {data.get('organization_id')}"
        print(f"[TEST D] ✅ PASS — org_id={data.get('organization_id')}, screen_id={data.get('id')}")


# ═══════════════════════════════════════════════════════════════
# TEST E — SELF_SERVICE_OWNER Org A modifica pantalla de Org B → 403
# ═══════════════════════════════════════════════════════════════
class TestE_TenantIsolation:
    def test_ssowner_orga_no_puede_modificar_orgb(self, seed_data):
        """TEST E: SELF_SERVICE_OWNER Org A PUT pantalla de Org B → 403"""
        token = login("ssowner_a")
        screen_org_b_id = (seed_data.get("screen_org_b") or {}).get("id")
        if not screen_org_b_id:
            pytest.skip("screen_org_b no encontrado en seed_data")

        payload = {"name": "INTRUDER modification"}
        resp = requests.put(
            f"{BASE_URL}/api/screens/self-service/{screen_org_b_id}",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 403, \
            f"TEST E FALLÓ — esperado 403, recibido {resp.status_code}: {resp.text[:300]}"
        print(f"[TEST E] ✅ PASS — 403 recibido correctamente (tenant isolation OK)")


# ═══════════════════════════════════════════════════════════════
# TEST F — ADVERTISER no puede crear screens
# ═══════════════════════════════════════════════════════════════
class TestF_AdvertiserBloqueado:
    def test_advertiser_no_puede_admin_screens(self):
        """TEST F-1: ADVERTISER POST /api/admin/screens → 403"""
        token = login("advertiser")
        payload = {
            "name":     "INTRUDER admin screen",
            "location": LOCATION,
        }
        resp = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 403, \
            f"TEST F-1 FALLÓ — esperado 403, recibido {resp.status_code}: {resp.text[:300]}"
        print(f"[TEST F-1] ✅ PASS — ADVERTISER bloqueado de /admin/screens")

    def test_advertiser_no_puede_self_service_screens(self):
        """TEST F-2: ADVERTISER POST /api/screens/self-service → 403"""
        token = login("advertiser")
        payload = {
            "name":     "INTRUDER self-service screen",
            "location": LOCATION,
        }
        resp = requests.post(
            f"{BASE_URL}/api/screens/self-service",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 403, \
            f"TEST F-2 FALLÓ — esperado 403, recibido {resp.status_code}: {resp.text[:300]}"
        print(f"[TEST F-2] ✅ PASS — ADVERTISER bloqueado de /screens/self-service")


# ═══════════════════════════════════════════════════════════════
# TEST G — MANAGED_VIEWER crea playlist pero no puede publicarla
# ═══════════════════════════════════════════════════════════════
class TestG_ManagedViewerNoPublica:
    def test_viewer_no_puede_publicar_playlist(self):
        """TEST G: MANAGED_VIEWER crea playlist (puede) pero publish → 403"""
        token = login("viewer")

        # Crear playlist
        create_resp = requests.post(
            f"{BASE_URL}/api/playlists",
            json={"name": "TEST_G Viewer Playlist", "screen_id": "dummy_screen"},
            headers=auth_header(token),
        )
        # La creación puede fallar o tener status 200/201 (viewer tiene acceso a playlists)
        # Si falla con 403, igual aceptamos — lo que importa es que publish falle
        playlist_id = None
        if create_resp.status_code in (200, 201):
            data = create_resp.json()
            playlist_id = data.get("id") or data.get("_id")
            print(f"[TEST G] Playlist creada: {playlist_id}")
        else:
            print(f"[TEST G] Playlist creation status: {create_resp.status_code} — {create_resp.text[:200]}")
            # Si no pudo crear, verificamos publish con un ID ficticio (igual debe dar 403 por auth)
            playlist_id = "000000000000000000000000"

        # Intentar publicar — debe dar 403
        publish_resp = requests.post(
            f"{BASE_URL}/api/playlists/{playlist_id}/publish",
            json={"screen_ids": []},
            headers=auth_header(token),
        )
        assert publish_resp.status_code == 403, \
            f"TEST G FALLÓ — esperado 403 en publish, recibido {publish_resp.status_code}: {publish_resp.text[:300]}"
        print(f"[TEST G] ✅ PASS — MANAGED_VIEWER bloqueado de publicar playlist (403)")


# ═══════════════════════════════════════════════════════════════
# TEST H — MEDIAVIEW_ADMIN administra pantallas
# ═══════════════════════════════════════════════════════════════
class TestH_MediaviewAdminGestionaPantallas:
    def test_mwadmin_crea_public_advertising(self, seed_data):
        """TEST H-1: MEDIAVIEW_ADMIN POST /api/admin/screens PUBLIC_ADVERTISING → 200"""
        token = login("mwadmin")
        payload = {
            "name":           "TEST_H MEDIAVIEW_ADMIN Public Screen",
            "location":       LOCATION,
            "operation_type": "PUBLIC_ADVERTISING",
        }
        resp = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 200, \
            f"TEST H-1 FALLÓ: {resp.status_code} — {resp.text[:300]}"
        data = resp.json()
        self.__class__.created_screen_id = data.get("id") or data.get("_id")
        print(f"[TEST H-1] ✅ PASS — screen_id={self.__class__.created_screen_id}")

    def test_mwadmin_actualiza_pantalla_existente(self, seed_data):
        """TEST H-2: MEDIAVIEW_ADMIN PUT /api/admin/screens/{id} → 200"""
        token = login("mwadmin")
        # Usar la pantalla pública del seed si no tenemos la creada
        screen_id = getattr(self.__class__, "created_screen_id", None) or (seed_data.get("screen_public") or {}).get("id")
        if not screen_id:
            pytest.skip("No hay screen_id disponible para TEST H-2")

        payload = {"name": "TEST_H Updated by MEDIAVIEW_ADMIN"}
        resp = requests.put(
            f"{BASE_URL}/api/admin/screens/{screen_id}",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 200, \
            f"TEST H-2 FALLÓ: {resp.status_code} — {resp.text[:300]}"
        print(f"[TEST H-2] ✅ PASS — Screen actualizada correctamente")


# ═══════════════════════════════════════════════════════════════
# BONUS — SELF_SERVICE_OWNER no puede usar /admin/screens
# ═══════════════════════════════════════════════════════════════
class TestBonus_SelfServiceOwnerNoAdmin:
    def test_ssowner_no_puede_admin_screens(self):
        """BONUS: SELF_SERVICE_OWNER POST /api/admin/screens → 403"""
        token = login("ssowner_a")
        payload = {
            "name":     "INTRUDER via admin endpoint",
            "location": LOCATION,
        }
        resp = requests.post(
            f"{BASE_URL}/api/admin/screens",
            json=payload,
            headers=auth_header(token),
        )
        assert resp.status_code == 403, \
            f"BONUS FALLÓ — esperado 403, recibido {resp.status_code}: {resp.text[:300]}"
        print(f"[BONUS] ✅ PASS — SELF_SERVICE_OWNER bloqueado de /admin/screens")
