"""Iteración 29 — cobertura adicional del review request.

Cubre los escenarios que no estaban en los pytest existentes:
- media upload → GET /api/player/media/{id} sirve la imagen
- publish playlist sin items = 400
- cambio de contraseña: 400 si la actual es incorrecta o si la nueva es igual
- restricciones del gerente (SELF_SERVICE_MANAGER): puede pantallas, NO billing/team
- restricciones adicionales del empleado: /screens/connect, /logo
- team reset-password endpoint
"""
import base64
import os
import uuid

import pytest
import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")

# 1x1 PNG
PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d7636060600000000400012734270a0000000049454e44ae426082"
)).decode()


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


def _token(email, password):
    r = _login(email, password)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# --- Media upload → player serve ---
def test_media_upload_is_served_by_player():
    tok = _token(*OWNER)
    up = requests.post(f"{BASE}/api/media/upload", headers=_h(tok), timeout=60, json={
        "filename": "iter29-serve.png", "content_type": "image/png", "data": PNG,
    })
    assert up.status_code == 200, up.text
    mid = up.json()["id"]

    serve = requests.get(f"{BASE}/api/player/media/{mid}", timeout=30)
    assert serve.status_code == 200, serve.text
    ct = serve.headers.get("content-type", "")
    assert "image" in ct, ct
    assert len(serve.content) > 0

    requests.delete(f"{BASE}/api/media/{mid}", headers=_h(tok), timeout=30)


# --- Playlists: publish sin items = 400 ---
def test_publish_empty_playlist_returns_400():
    tok = _token(*OWNER)
    made = requests.post(f"{BASE}/api/workspace/playlists", headers=_h(tok), timeout=30, json={
        "name": f"EmptyPub-{uuid.uuid4().hex[:6]}", "items": [],
    })
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    pub = requests.post(f"{BASE}/api/workspace/playlists/{pid}/publish",
                        headers=_h(tok), timeout=30, json={"screen_ids": []})
    assert pub.status_code == 400, pub.text
    requests.delete(f"{BASE}/api/workspace/playlists/{pid}", headers=_h(tok), timeout=30)


# --- Change password: wrong current & same new ---
def test_change_password_validations():
    tok = _token(*OWNER)
    oh = _h(tok)

    email = f"empleado-{uuid.uuid4().hex[:8]}@demo.com"
    temp = "TempPass123!"
    created = requests.post(f"{BASE}/api/workspace/team", headers=oh, timeout=30, json={
        "name": "Test CPV", "email": email, "temporary_password": temp, "role": "employee",
    })
    assert created.status_code == 201, created.text
    mid = created.json()["id"]

    sess = requests.post(f"{BASE}/api/auth/login",
                         json={"email": email, "password": temp}, timeout=30).json()
    mh = _h(sess["access_token"])

    # Wrong current password
    r1 = requests.post(f"{BASE}/api/workspace/change-password", headers=mh, timeout=30, json={
        "current_password": "WrongPass!123", "new_password": "AnotherNew12!",
    })
    assert r1.status_code == 400, r1.text

    # New == current
    r2 = requests.post(f"{BASE}/api/workspace/change-password", headers=mh, timeout=30, json={
        "current_password": temp, "new_password": temp,
    })
    assert r2.status_code == 400, r2.text

    # cleanup — deactivate the test member
    requests.delete(f"{BASE}/api/workspace/team/{mid}", headers=oh, timeout=30)


# --- Manager role: can screens, NOT billing, NOT team ---
def test_manager_role_permissions():
    tok = _token(*OWNER)
    oh = _h(tok)

    email = f"gerente-{uuid.uuid4().hex[:8]}@demo.com"
    temp = "TempMgr123!"
    real = "MgrReal4321!"
    created = requests.post(f"{BASE}/api/workspace/team", headers=oh, timeout=30, json={
        "name": "Gerente Test", "email": email, "temporary_password": temp, "role": "manager",
    })
    assert created.status_code == 201, created.text
    mid = created.json()["id"]
    assert created.json()["rbac_role"] == "SELF_SERVICE_MANAGER"

    sess = requests.post(f"{BASE}/api/auth/login",
                         json={"email": email, "password": temp}, timeout=30).json()
    mh0 = _h(sess["access_token"])
    # change password first
    ch = requests.post(f"{BASE}/api/workspace/change-password", headers=mh0, timeout=30, json={
        "current_password": temp, "new_password": real,
    })
    assert ch.status_code == 200

    sess2 = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": real}, timeout=30).json()
    mh = _h(sess2["access_token"])

    # Manager CAN see team but can_manage=False
    team = requests.get(f"{BASE}/api/workspace/team", headers=mh, timeout=30)
    if team.status_code == 200:
        assert team.json().get("can_manage") is False, team.json()
    else:
        # 403 also acceptable per requirement wording
        assert team.status_code == 403

    # Manager CANNOT see billing
    billing = requests.get(f"{BASE}/api/workspace/billing", headers=mh, timeout=30)
    assert billing.status_code == 403, billing.text

    # Manager CANNOT create team members
    write_team = requests.post(f"{BASE}/api/workspace/team", headers=mh, timeout=30, json={
        "name": "X", "email": f"x-{uuid.uuid4().hex[:6]}@demo.com",
        "temporary_password": "Whatever12!", "role": "employee",
    })
    assert write_team.status_code == 403, write_team.text

    # Manager CAN create a screen
    screen = requests.post(f"{BASE}/api/workspace/screens", headers=mh, timeout=30,
                           json={"name": f"MgrScreen-{uuid.uuid4().hex[:5]}"})
    assert screen.status_code in (200, 201), screen.text
    if screen.status_code in (200, 201):
        sid = screen.json().get("id")
        if sid:
            requests.delete(f"{BASE}/api/workspace/screens/{sid}", headers=oh, timeout=30)

    # cleanup
    requests.delete(f"{BASE}/api/workspace/team/{mid}", headers=oh, timeout=30)


# --- Employee 403 on connect + logo ---
def test_employee_denied_on_screens_connect_and_logo():
    tok = _token(*OWNER)
    oh = _h(tok)

    email = f"emp-{uuid.uuid4().hex[:8]}@demo.com"
    temp = "TempEmp123!"
    real = "EmpReal4321!"
    created = requests.post(f"{BASE}/api/workspace/team", headers=oh, timeout=30, json={
        "name": "Emp Test", "email": email, "temporary_password": temp, "role": "employee",
    })
    assert created.status_code == 201, created.text
    mid = created.json()["id"]

    sess = requests.post(f"{BASE}/api/auth/login",
                         json={"email": email, "password": temp}, timeout=30).json()
    mh0 = _h(sess["access_token"])
    requests.post(f"{BASE}/api/workspace/change-password", headers=mh0, timeout=30, json={
        "current_password": temp, "new_password": real,
    })

    sess2 = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": real}, timeout=30).json()
    mh = _h(sess2["access_token"])

    connect = requests.post(f"{BASE}/api/workspace/screens/connect", headers=mh, timeout=30,
                            json={"code": "ABC123"})
    assert connect.status_code == 403, connect.text

    logo = requests.post(f"{BASE}/api/workspace/logo", headers=mh, timeout=30, json={
        "logo_filename": "l.png", "logo_base64": PNG,
    })
    assert logo.status_code == 403, logo.text

    # cleanup
    requests.delete(f"{BASE}/api/workspace/team/{mid}", headers=oh, timeout=30)


# --- Team reset-password endpoint sets must_change_password=True ---
def test_team_reset_password():
    tok = _token(*OWNER)
    oh = _h(tok)

    email = f"reset-{uuid.uuid4().hex[:8]}@demo.com"
    temp = "TempReset123!"
    real = "RealReset4321!"
    created = requests.post(f"{BASE}/api/workspace/team", headers=oh, timeout=30, json={
        "name": "Reset Test", "email": email, "temporary_password": temp, "role": "employee",
    })
    assert created.status_code == 201, created.text
    mid = created.json()["id"]

    # Member changes password (so must_change_password becomes False)
    sess = requests.post(f"{BASE}/api/auth/login",
                         json={"email": email, "password": temp}, timeout=30).json()
    requests.post(f"{BASE}/api/workspace/change-password",
                  headers=_h(sess["access_token"]), timeout=30, json={
                      "current_password": temp, "new_password": real,
                  })

    # Owner resets password
    new_temp = "OwnerReset99!"
    r = requests.post(f"{BASE}/api/workspace/team/{mid}/reset-password",
                      headers=oh, timeout=30, json={"temporary_password": new_temp})
    assert r.status_code == 200, r.text

    # Old real password no longer works
    dead = requests.post(f"{BASE}/api/auth/login",
                         json={"email": email, "password": real}, timeout=30)
    assert dead.status_code == 401

    # New temp works and must_change_password=True again
    fresh = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": new_temp}, timeout=30)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["must_change_password"] is True

    # cleanup
    requests.delete(f"{BASE}/api/workspace/team/{mid}", headers=oh, timeout=30)
