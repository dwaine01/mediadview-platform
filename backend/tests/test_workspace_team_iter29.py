"""Iteración 29 — equipo del negocio (RBAC de cliente) y cambio de contraseña forzado."""
import os
import uuid

import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
OTHER_OWNER = ("testws@test.com", "Test1234!")


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_creates_member_and_forces_password_change():
    owner = _login(*OWNER)
    oh = _h(owner["access_token"])

    email = f"empleado-{uuid.uuid4().hex[:8]}@demo.com"
    temp = "TempPass123!"
    created = requests.post(f"{BASE}/api/workspace/team", headers=oh, timeout=30, json={
        "name": "Empleado Prueba", "email": email, "temporary_password": temp, "role": "employee",
    })
    assert created.status_code == 201, created.text
    member = created.json()
    assert member["team_role"] == "employee"
    assert member["must_change_password"] is True
    assert member["rbac_role"] == "SELF_SERVICE_STAFF"

    listed = requests.get(f"{BASE}/api/workspace/team", headers=oh, timeout=30).json()
    assert listed["can_manage"] is True
    assert any(m["id"] == member["id"] for m in listed["members"])

    # duplicate email rejected
    dup = requests.post(f"{BASE}/api/workspace/team", headers=oh, timeout=30, json={
        "name": "Otro", "email": email, "temporary_password": temp, "role": "employee",
    })
    assert dup.status_code == 409

    # member logs in with the temporary password
    session = _login(email, temp)
    assert session["must_change_password"] is True
    mh = _h(session["access_token"])

    # workspace is gated until the password is changed
    blocked = requests.get(f"{BASE}/api/workspace/context", headers=mh, timeout=30)
    assert blocked.status_code == 428, blocked.text

    # employee cannot manage the team
    denied = requests.get(f"{BASE}/api/workspace/team", headers=mh, timeout=30).json()
    assert denied["can_manage"] is False

    # change password clears the flag
    changed = requests.post(f"{BASE}/api/workspace/change-password", headers=mh, timeout=30, json={
        "current_password": temp, "new_password": "MiClaveReal9!",
    })
    assert changed.status_code == 200, changed.text

    session2 = _login(email, "MiClaveReal9!")
    assert session2["must_change_password"] is False
    mh2 = _h(session2["access_token"])
    ctx = requests.get(f"{BASE}/api/workspace/context", headers=mh2, timeout=30)
    assert ctx.status_code == 200

    # employee restrictions: no billing, no screen creation, no team writes
    assert requests.get(f"{BASE}/api/workspace/billing", headers=mh2, timeout=30).status_code == 403
    assert requests.post(f"{BASE}/api/workspace/screens", headers=mh2, timeout=30,
                         json={"name": "Nope"}).status_code == 403
    assert requests.post(f"{BASE}/api/workspace/team", headers=mh2, timeout=30, json={
        "name": "X", "email": f"x-{uuid.uuid4().hex[:6]}@demo.com",
        "temporary_password": "Whatever12!", "role": "employee",
    }).status_code == 403

    # employee CAN use content and playlists
    assert requests.get(f"{BASE}/api/workspace/media", headers=mh2, timeout=30).status_code == 200
    assert requests.get(f"{BASE}/api/workspace/playlists", headers=mh2, timeout=30).status_code == 200

    # cross-tenant: another org's owner cannot touch this member
    other = _login(*OTHER_OWNER)
    ooh = _h(other["access_token"])
    assert requests.patch(f"{BASE}/api/workspace/team/{member['id']}", headers=ooh, timeout=30,
                          json={"role": "admin"}).status_code == 404
    assert requests.delete(f"{BASE}/api/workspace/team/{member['id']}", headers=ooh,
                           timeout=30).status_code == 404

    # owner cannot manage their own account through the team endpoints
    me = next(m for m in listed["members"] if m["is_me"])
    assert requests.delete(f"{BASE}/api/workspace/team/{me['id']}", headers=oh,
                           timeout=30).status_code == 400

    # role promotion + deactivation
    promoted = requests.patch(f"{BASE}/api/workspace/team/{member['id']}", headers=oh, timeout=30,
                              json={"role": "manager"})
    assert promoted.status_code == 200 and promoted.json()["team_role"] == "manager"

    off = requests.delete(f"{BASE}/api/workspace/team/{member['id']}", headers=oh, timeout=30)
    assert off.status_code == 200
    dead = requests.post(f"{BASE}/api/auth/login", timeout=30,
                         json={"email": email, "password": "MiClaveReal9!"})
    assert dead.status_code == 401

    # cleanup
    requests.patch(f"{BASE}/api/workspace/team/{member['id']}", headers=oh, timeout=30,
                   json={"active": False})
