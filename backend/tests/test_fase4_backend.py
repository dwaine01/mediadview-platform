"""
MediAd View — backend regression tests for Fase 4 JWT_SECRET fix + Fase 2/3 sanity.
Coverage:
  • JWT_SECRET stability across backend restart
  • Access token issued pre-restart valid post-restart (same secret loaded)
  • Auth v2 login/refresh/logout + HttpOnly refresh cookie for web
  • Brute-force lockout (5+ failures → 429)
  • Rate-limit headers (X-RateLimit-*)
  • Health endpoints: /api/health, /api/livez, /api/ready
  • Menu HTML render + WebSocket auto-reload snippet
  • Media upload (fallback legacy disk), presign 503, .exe validation
  • Startup fail-fast validator (startup_check.py exit 2 on broken .env)
  • A40 device Basic Auth on /api/wp-json/wp/v2/comments (no regression)
  • audit_log ingestion for login_success / login_failed / logout
"""
import base64
import os
import subprocess
import time
from pathlib import Path

import jwt as pyjwt
import pytest
import requests

from rate_limit import LIMITS, is_rate_limit_disabled
from storage import R2_ENABLED
from tests.conftest import BASE_URL  # type: ignore

BACKEND_DIR = Path(__file__).resolve().parent.parent
BACKEND_ENV = BACKEND_DIR / ".env"


def _login_limit_per_minute() -> int:
    """Lee el límite de login de la misma fuente que el backend."""
    for part in LIMITS.login.split(";"):
        amount, _, period = part.strip().partition("/")
        if period.strip().startswith("minute"):
            return int(amount)
    raise AssertionError(f"no per-minute limit in {LIMITS.login!r}")


def _lockout_max_fail() -> int:
    return int(os.environ.get("LOCKOUT_MAX_FAIL", "5"))


def _lockout_disabled() -> bool:
    return int(os.environ.get("LOCKOUT_WINDOW_MIN", "15")) <= 0

# ── Credentials (from /app/memory/test_credentials.md + review request) ──
SUPERADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")
ADMIN_DEMO = ("admin.demo@mediadview.com", "AdminDemo#2026")
A40_USER   = ("4h7QNZL5tnAY", "Iv7LfV4gls2DSrv")


def _restart_backend_or_skip_ci():
    if os.environ.get("CI", "").lower() == "true":
        pytest.skip("requires the local Supervisor-managed backend")
    subprocess.run(
        ["sudo", "supervisorctl", "restart", "backend"],
        check=True,
        capture_output=True,
    )


# Skip this whole module in CI environments that don't have seed data.
# The tests are integration-style and require the seeded users +
# the /app/backend/.env file. E2E job (SKIP_SEED=false + running
# server) runs them via a separate step.
def _seed_available():
    if os.environ.get("SKIP_SEED", "").lower() == "true":
        return False
    if os.environ.get("ENVIRONMENT") == "test":
        return False
    try:
        if not BACKEND_ENV.exists():
            return False
        r = requests.get(f"{BASE_URL}/api/livez", timeout=2)
        if r.status_code != 200:
            return False
        r = requests.post(f"{BASE_URL}/api/auth/v2/login",
                          json={"email": SUPERADMIN[0], "password": SUPERADMIN[1],
                                "client_type": "web"}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _seed_available(),
    reason="requires seeded users + running backend (skipped in CI test job)")


# ══════════════════════════════════════════════════════════════════════
# 1) JWT_SECRET loading + stability
# ══════════════════════════════════════════════════════════════════════
class TestJWTSecret:
    """Verifies the .env fix — JWT_SECRET is loaded, stable, non-random."""

    def _read_env_secret(self):
        for line in BACKEND_ENV.read_text().splitlines():
            if line.startswith("JWT_SECRET="):
                v = line.split("=", 1)[1].strip()
                return v.strip('"').strip("'")
        return None

    def test_env_file_has_jwt_secret(self):
        secret = self._read_env_secret()
        assert secret and len(secret) >= 32, "JWT_SECRET missing or too short in .env"
        assert secret != "mediaview-secure-jwt-secret-2026", "still using old placeholder"

    def test_login_and_decode_with_env_secret(self, api):
        """Login → the returned JWT MUST decode against the .env secret."""
        secret = self._read_env_secret()
        assert secret, "JWT_SECRET not found in .env"
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": SUPERADMIN[0], "password": SUPERADMIN[1],
                           "client_type": "web"})
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        # Must decode with the SAME secret from .env — no random fallback in play.
        payload = pyjwt.decode(access, secret, algorithms=["HS256"],
                               audience="mediadview-frontend", issuer="mediadview-api")
        assert payload["email"] == SUPERADMIN[0]
        assert payload["typ"] == "access"

    def test_token_survives_backend_restart(self, api):
        """CRITICAL FASE-4 CHECK — token issued pre-restart still valid post-restart.
        Confirms JWT_SECRET is loaded stably from .env (not regenerated randomly)."""
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": SUPERADMIN[0], "password": SUPERADMIN[1],
                           "client_type": "native"})
        assert r.status_code == 200
        access_pre = r.json()["access_token"]

        # /me works pre-restart
        h = {"Authorization": f"Bearer {access_pre}"}
        r0 = requests.get(f"{BASE_URL}/api/auth/v2/me", headers=h)
        assert r0.status_code == 200

        # Restart backend and wait for it to come back up.
        _restart_backend_or_skip_ci()
        deadline = time.time() + 30
        up = False
        while time.time() < deadline:
            try:
                if requests.get(f"{BASE_URL}/api/livez", timeout=2).status_code == 200:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(1)
        assert up, "backend did not come back up after restart"

        # Same token must still validate.
        r1 = requests.get(f"{BASE_URL}/api/auth/v2/me", headers=h)
        assert r1.status_code == 200, (
            f"Pre-restart token rejected after restart ({r1.status_code}). "
            "JWT_SECRET is NOT stable across restarts."
        )
        assert r1.json()["email"] == SUPERADMIN[0]


# ══════════════════════════════════════════════════════════════════════
# 2) Auth v2 flow — login + refresh + logout (web cookie + rotation)
# ══════════════════════════════════════════════════════════════════════
class TestAuthV2Flow:
    def test_login_web_sets_httponly_cookie(self, api):
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": ADMIN_DEMO[0], "password": ADMIN_DEMO[1],
                           "client_type": "web"})
        assert r.status_code == 200, r.text
        cookie_hdr = r.headers.get("set-cookie", "")
        assert "mediadview_refresh" in cookie_hdr.lower()
        assert "httponly" in cookie_hdr.lower(), "refresh cookie must be HttpOnly"
        # Body must NOT ship a refresh token for web clients (null OR absent is fine,
        # since Pydantic Optional[str]=None serialises to null and native flow needs
        # the field on the model).
        assert not r.json().get("refresh_token"), \
            "web client MUST NOT receive a refresh_token value in body (only cookie)"

    def test_login_native_returns_refresh_in_body(self, api):
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": ADMIN_DEMO[0], "password": ADMIN_DEMO[1],
                           "client_type": "native"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("refresh_token"), "native client MUST get refresh_token in JSON body"

    def test_refresh_rotates_token(self, api):
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": ADMIN_DEMO[0], "password": ADMIN_DEMO[1],
                           "client_type": "web"})
        assert r.status_code == 200
        cookies = r.cookies
        access1 = r.json()["access_token"]

        r2 = requests.post(f"{BASE_URL}/api/auth/v2/refresh", cookies=cookies)
        assert r2.status_code == 200, r2.text
        access2 = r2.json()["access_token"]
        assert access2 and access2 != access1, "refresh must issue a NEW access token"
        assert "mediadview_refresh" in r2.headers.get("set-cookie", "").lower()

    def test_logout_revokes_session(self, api):
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": ADMIN_DEMO[0], "password": ADMIN_DEMO[1],
                           "client_type": "web"})
        assert r.status_code == 200
        access = r.json()["access_token"]
        cookies = r.cookies

        r2 = requests.post(f"{BASE_URL}/api/auth/v2/logout",
                           headers={"Authorization": f"Bearer {access}"}, cookies=cookies)
        assert r2.status_code == 200

        # After logout the session is revoked → /me must reject.
        r3 = requests.get(f"{BASE_URL}/api/auth/v2/me",
                          headers={"Authorization": f"Bearer {access}"})
        assert r3.status_code == 401, "access token must be revoked after logout"


# ══════════════════════════════════════════════════════════════════════
# 3) Brute-force + rate-limit headers
# ══════════════════════════════════════════════════════════════════════
class TestBruteForceAndRateLimit:

    def test_rate_limit_headers_present(self, api, mongo_db):
        """Verify slowapi is wired: cuando el límite de slowapi es el que salta
        primero, el 429 DEBE traer X-RateLimit-* y el valor configurado.

        El límite y el umbral de bloqueo se leen de la MISMA fuente que usa el
        backend (`rate_limit.LIMITS` y `LOCKOUT_MAX_FAIL`) en vez de hardcodear
        un "5": en development/test el login permite 60/minuto, así que el
        guardia que salta primero es el bloqueo por fuerza bruta.
        """
        if is_rate_limit_disabled():
            pytest.skip("rate limiter apagado en CI (ENVIRONMENT=test + RATE_LIMIT_DISABLED)")

        per_minute = _login_limit_per_minute()
        max_fail = _lockout_max_fail()
        mongo_db.login_attempts.delete_many({"ip": "127.0.0.1"})

        last = None
        for _ in range(min(per_minute, max_fail) + 2):
            last = api.post(f"{BASE_URL}/api/auth/v2/login",
                            json={"email": "no-such-rl@example.com", "password": "x",
                                  "client_type": "native"})
            if last.status_code == 429:
                break
        assert last.status_code == 429, f"expected a 429, got {last.status_code}"

        if max_fail < per_minute:
            # El bloqueo por fuerza bruta salta antes que slowapi: su 429 no
            # lleva cabeceras de rate limit y eso es correcto.
            assert last.json().get("detail") or last.json().get("error")
            return

        keys = {k.lower() for k in last.headers.keys()}
        assert "x-ratelimit-limit" in keys, f"missing X-RateLimit-Limit: {dict(last.headers)}"
        assert "x-ratelimit-remaining" in keys, "missing X-RateLimit-Remaining"
        assert "x-ratelimit-reset" in keys, "missing X-RateLimit-Reset"
        assert last.headers.get("x-ratelimit-limit") == str(per_minute)

    def test_bruteforce_lockout_returns_429(self, api, mongo_db):
        """`LOCKOUT_MAX_FAIL` logins fallidos → el siguiente intento es 429."""
        if _lockout_disabled():
            pytest.skip("bloqueo por fuerza bruta apagado en CI (LOCKOUT_WINDOW_MIN=0)")
        max_fail = _lockout_max_fail()
        mongo_db.login_attempts.delete_many({"ip": "127.0.0.1"})
        email = "brute-test@example.com"
        for _ in range(max_fail):
            api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": email, "password": "wrong",
                           "client_type": "native"})
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": email, "password": "wrong",
                           "client_type": "native"})
        assert r.status_code == 429, f"expected 429 after {max_fail} failures, got {r.status_code}"


# ══════════════════════════════════════════════════════════════════════
# 4) Health probes
# ══════════════════════════════════════════════════════════════════════
class TestHealth:
    def test_legacy_health(self, api):
        r = api.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        j = r.json()
        # Legacy shape for the Android APK.
        assert j.get("status") == "healthy"

    def test_livez(self, api):
        r = api.get(f"{BASE_URL}/api/livez")
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert "uptime_s" in j and isinstance(j["uptime_s"], (int, float))
        assert j["app"] == "MediAd View"

    def test_ready_checks(self, api):
        r = api.get(f"{BASE_URL}/api/ready")
        # Should be 200 in dev even without redis/worker (soft in dev).
        assert r.status_code == 200, r.text
        j = r.json()
        # `storage` se añadió después; se exige que estén los tres duros y se
        # aceptan chequeos nuevos sin tener que tocar el test cada vez.
        assert {"mongo", "redis", "worker"} <= set(j["checks"].keys()), j["checks"]
        assert j["checks"]["mongo"]["ok"] is True, f"mongo not healthy: {j['checks']['mongo']}"


# ══════════════════════════════════════════════════════════════════════
# 5) Menu render + WebSocket auto-reload snippet
# ══════════════════════════════════════════════════════════════════════
class TestMenuRender:
    def test_menu_html_contains_ws_client(self, api, mongo_db):
        # H3: solo los menús publicados renderizan sin autenticación; un draft
        # devuelve 404 a propósito.
        menu = mongo_db.menus.find_one({"status": {"$in": ["published", "active"]}}, {"id": 1})
        if not menu:
            pytest.skip("no published menu documents in DB")
        r = api.get(f"{BASE_URL}/api/menus/{menu['id']}/render")
        assert r.status_code == 200
        html = r.text.lower()
        assert "<html" in html
        # WebSocket auto-reload snippet should be embedded.
        assert "websocket" in html or "ws://" in html or "wss://" in html or "/api/ws/menu/" in html, \
            "menu render must include the WebSocket auto-reload client"


# ══════════════════════════════════════════════════════════════════════
# 6) Media upload (legacy fallback), presign 503, .exe validation
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def superadmin_token():
    # The login endpoint is capped at 5/minute per IP (slowapi memory storage).
    # If earlier tests exhausted the window, restart the backend to flush it.
    for attempt in range(2):
        r = requests.post(f"{BASE_URL}/api/auth/v2/login",
                          json={"email": SUPERADMIN[0], "password": SUPERADMIN[1],
                                "client_type": "native"})
        if r.status_code == 200:
            return r.json()["access_token"]
        if r.status_code == 429 and attempt == 0:
            _restart_backend_or_skip_ci()
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    if requests.get(f"{BASE_URL}/api/livez", timeout=2).status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(1)
            continue
        assert False, r.text
    assert False, "unable to obtain superadmin token"


# 1x1 transparent PNG
_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAA"
            "AAAMAASsJTYQAAAAASUVORK5CYII=")


class TestMedia:
    def test_upload_image_storage_matches_the_configured_backend(self, superadmin_token):
        """Con R2 configurado el media va a R2; sin R2, al disco (legacy).

        `R2_ENABLED` se lee del mismo módulo que usa el backend, así que el
        test no asume un entorno concreto: en CI (sin R2) exige legacy y en
        staging/production (con R2) exige r2 + clave en el bucket.
        """
        h = {"Authorization": f"Bearer {superadmin_token}", "Content-Type": "application/json"}
        payload = {"filename": "TEST_1x1.png",
                   "content_type": "image/png",
                   "data": _PNG_B64}
        r = requests.post(f"{BASE_URL}/api/media/upload", json=payload, headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        expected = "r2" if R2_ENABLED else "legacy"
        assert j["storage"] == expected, f"expected {expected} (R2_ENABLED={R2_ENABLED}), got {j['storage']}"
        if R2_ENABLED:
            assert j.get("public_url"), "R2 upload must expose a public_url"
        assert j["type"] == "image"
        # GET the media metadata to verify persistence.
        rid = j["id"]
        g = requests.get(f"{BASE_URL}/api/media/{rid}", headers=h)
        assert g.status_code == 200
        assert g.json()["id"] == rid

    def test_presign_depends_on_r2_being_configured(self, superadmin_token):
        h = {"Authorization": f"Bearer {superadmin_token}", "Content-Type": "application/json"}
        payload = {"filename": "big.mp4", "content_type": "video/mp4",
                   "size_bytes": 5_000_000, "duration_seconds": 12}
        r = requests.post(f"{BASE_URL}/api/media/presign", json=payload, headers=h)
        if R2_ENABLED:
            assert r.status_code == 200, f"expected a presigned URL, got {r.status_code}: {r.text[:200]}"
            assert r.json().get("url"), r.text[:200]
        else:
            assert r.status_code == 503, f"expected 503 when R2 unset, got {r.status_code}: {r.text}"

    def test_upload_exe_rejected(self, superadmin_token):
        h = {"Authorization": f"Bearer {superadmin_token}", "Content-Type": "application/json"}
        payload = {"filename": "malware.exe",
                   "content_type": "application/x-msdownload",
                   "data": base64.b64encode(b"MZ\x90\x00").decode()}
        r = requests.post(f"{BASE_URL}/api/media/upload", json=payload, headers=h)
        assert r.status_code == 415, f"expected 415 for unsupported .exe, got {r.status_code}: {r.text[:200]}"


# ══════════════════════════════════════════════════════════════════════
# 7) Startup fail-fast validator
# ══════════════════════════════════════════════════════════════════════
class TestStartupCheck:

    def test_startup_check_exits_2_on_broken_env(self, tmp_path):
        """Simulate the exact bug: KEY1="foo"KEY2=bar glued on one line."""
        broken = tmp_path / ".env"
        broken.write_text(
            'MONGO_URL="mongodb://localhost:27017"\n'
            'DB_NAME="mediaview_db"\n'
            'MEDIA_DIR="/tmp"JWT_SECRET="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
        )
        # Swap the .env location the check reads by copying our broken one into a
        # temp workspace and running the check with that as cwd. The script
        # reads /app/backend/.env directly, so we back up & restore instead.
        backup = tmp_path / "env.bak"
        real_env = BACKEND_ENV
        backup.write_text(real_env.read_text())
        try:
            real_env.write_text(broken.read_text())
            proc = subprocess.run(
                ["python3", str(BACKEND_DIR / "startup_check.py")],
                capture_output=True, text=True, timeout=15,
            )
            assert proc.returncode == 2, (
                f"expected exit 2 on broken .env, got {proc.returncode}. "
                f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
            assert "glued" in proc.stderr.lower() or "syntax" in proc.stderr.lower() \
                or "newline" in proc.stderr.lower()
        finally:
            real_env.write_text(backup.read_text())


# ══════════════════════════════════════════════════════════════════════
# 8) A40 Basic Auth regression on wp-json comments
# ══════════════════════════════════════════════════════════════════════
class TestA40Regression:
    def test_wp_comments_basic_auth_ok(self, api):
        r = requests.get(f"{BASE_URL}/api/wp-json/wp/v2/comments",
                         params={"clt_type": "terminal", "device_num": "42"},
                         auth=(A40_USER[0], A40_USER[1]))
        assert r.status_code == 200, r.text
        # Response is a JSON list (possibly empty).
        assert isinstance(r.json(), list)

    def test_wp_comments_wrong_password_401(self, api):
        r = requests.get(f"{BASE_URL}/api/wp-json/wp/v2/comments",
                         params={"clt_type": "terminal"},
                         auth=(A40_USER[0], "wrong-password"))
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# 9) audit_log persistence
# ══════════════════════════════════════════════════════════════════════
class TestAuditLog:
    def test_audit_captures_login_success_and_failed_and_logout(self, api, mongo_db):
        # Fresh rate-limit window: restart backend to flush slowapi memory.
        _restart_backend_or_skip_ci()
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if requests.get(f"{BASE_URL}/api/livez", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        # Failed login
        api.post(f"{BASE_URL}/api/auth/v2/login",
                 json={"email": "totally-nonexistent-user@example.com",
                       "password": "definitely-wrong",
                       "client_type": "native"})
        # Success + logout
        r = api.post(f"{BASE_URL}/api/auth/v2/login",
                     json={"email": ADMIN_DEMO[0], "password": ADMIN_DEMO[1],
                           "client_type": "web"})
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        requests.post(f"{BASE_URL}/api/auth/v2/logout",
                      headers={"Authorization": f"Bearer {access}"}, cookies=r.cookies)

        # audit_log must contain at least one row for each action in the last 5 min.
        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        for action in ("login_success", "login_failed", "logout"):
            n = mongo_db.audit_log.count_documents({"action": action, "ts": {"$gte": since}})
            assert n > 0, f"audit_log has no recent '{action}' entries"
