"""Sprint 1 del Player — token de dispositivo, máquina de estados, progreso real y canal SSE."""
import os
import uuid

import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")


def _register(client_uuid: str) -> dict:
    r = requests.post(f"{BASE}/api/devices/register", timeout=30, json={
        "client_uuid": client_uuid, "device_model": "SprintOneBox",
        "os_version": "13", "app_version": "3.3.0", "resolution": "1920x1080",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _owner_headers():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": OWNER[0], "password": OWNER[1]}, timeout=30)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_device_token_is_issued_and_enforced():
    client_uuid = f"sprint1-{uuid.uuid4()}"
    reg = _register(client_uuid)
    assert reg["device_token"] and len(reg["device_token"]) >= 32
    assert reg["heartbeat_interval_seconds"] == 30
    device_id, token = reg["device_id"], reg["device_token"]

    # sin token → rechazado (el device_id ya no es credencial)
    assert requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", timeout=30,
                         json={"status": "online"}).status_code == 401
    # token equivocado → rechazado
    assert requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", timeout=30,
                         headers={"X-Device-Token": "no-soy-el-token"},
                         json={"status": "online"}).status_code == 401
    # token correcto → aceptado (también por Authorization: Bearer)
    for headers in ({"X-Device-Token": token}, {"Authorization": f"Bearer {token}"}):
        ok = requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", headers=headers,
                           timeout=30, json={"status": "online"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["heartbeat_interval_seconds"] == 30

    # el registro es el punto de enrolamiento: rota el token y el viejo deja de servir
    again = _register(client_uuid)
    assert again["device_id"] == device_id
    assert again["device_token"] != token
    assert requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", timeout=30,
                         headers={"X-Device-Token": token},
                         json={"status": "online"}).status_code == 401

    # los endpoints de contenido y de log también exigen token
    assert requests.get(f"{BASE}/api/devices/{device_id}/playlist", timeout=30).status_code == 401
    assert requests.get(f"{BASE}/api/devices/{device_id}/playlist", timeout=30,
                        headers={"X-Device-Token": again["device_token"]}).status_code == 200
    assert requests.post(f"{BASE}/api/devices/{device_id}/log", timeout=30,
                         json={"level": "info", "message": "hola"}).status_code == 401
    assert requests.post(f"{BASE}/api/devices/{device_id}/log", timeout=30,
                         headers={"X-Device-Token": again["device_token"]},
                         json={"level": "info", "message": "hola"}).status_code == 200


def test_legacy_player_without_token_is_adopted_not_locked_out():
    """Compatibilidad: un player ya instalado (sin token) sigue funcionando."""
    from pymongo import MongoClient
    from dotenv import dotenv_values
    env = dotenv_values("/app/backend/.env")
    db = MongoClient(env["MONGO_URL"])[env.get("DB_NAME", "mediaview")]

    reg = _register(f"sprint1-legacy-{uuid.uuid4()}")
    device_id = reg["device_id"]
    db.devices.update_one({"id": device_id}, {"$unset": {"device_token_hash": ""}})

    # sin token: aceptado en modo gracia
    assert requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", timeout=30,
                         json={"status": "online"}).status_code == 200
    # el primer token que presente queda adoptado y a partir de ahí es obligatorio
    adopted = f"token-adoptado-{uuid.uuid4()}"
    assert requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", timeout=30,
                         headers={"X-Device-Token": adopted},
                         json={"status": "online"}).status_code == 200
    assert requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", timeout=30,
                         json={"status": "online"}).status_code == 401


def test_player_state_and_real_sync_progress_reach_the_panel():
    from pymongo import MongoClient
    from dotenv import dotenv_values
    env = dotenv_values("/app/backend/.env")
    db = MongoClient(env["MONGO_URL"])[env.get("DB_NAME", "mediaview")]

    owner = _owner_headers()
    screen = requests.get(f"{BASE}/api/workspace/screens", headers=owner, timeout=30).json()[0]

    reg = _register(f"sprint1-state-{uuid.uuid4()}")
    device_id, token = reg["device_id"], reg["device_token"]
    dev_headers = {"X-Device-Token": token}
    # lo atamos a una pantalla real del negocio para verlo en el panel
    db.devices.update_one({"id": device_id}, {"$set": {"screen_id": screen["id"], "status": "active"}})

    downloading = requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", headers=dev_headers, timeout=30,
                                json={"status": "online", "screen_id": screen["id"],
                                      "player_state": "downloading",
                                      "sync_progress": {"files_done": 3, "files_total": 8,
                                                        "bytes_done": 62_000_000, "bytes_total": 145_000_000,
                                                        "current_file": "promo.jpg", "manifest_version": "42"}})
    assert downloading.status_code == 200

    row = next(r for r in requests.get(f"{BASE}/api/workspace/now-playing", headers=owner, timeout=30).json()
               if r["screen_id"] == screen["id"])
    assert row["player_state"] == "DOWNLOADING"
    assert row["connectivity"] == "ONLINE" and row["is_online"] is True
    assert row["app_version"] == "3.3.0"
    progress = row["sync_progress"]
    assert progress["files_done"] == 3 and progress["files_total"] == 8
    assert round(progress["percent"]) == 43  # 62/145 MB reales, no inventado

    # un estado inválido no contamina la máquina de estados
    requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", headers=dev_headers, timeout=30,
                  json={"status": "online", "player_state": "CUALQUIER_COSA"})
    row = next(r for r in requests.get(f"{BASE}/api/workspace/now-playing", headers=owner, timeout=30).json()
               if r["screen_id"] == screen["id"])
    assert row["player_state"] == "DOWNLOADING"

    # al empezar a reproducir, el progreso desaparece (no se queda pegado en 43%)
    requests.post(f"{BASE}/api/devices/{device_id}/heartbeat", headers=dev_headers, timeout=30,
                  json={"status": "online", "player_state": "playing"})
    row = next(r for r in requests.get(f"{BASE}/api/workspace/now-playing", headers=owner, timeout=30).json()
               if r["screen_id"] == screen["id"])
    assert row["player_state"] == "PLAYING"
    assert row["sync_progress"] is None

    db.devices.delete_one({"id": device_id})


def test_sse_event_channel_exists_and_announces_connection():
    """Iteración 38: el canal SSE es UNO solo (realtime.py).

    Contrato unificado: abre siempre con `event: connected` (el player resetea su
    backoff con ese evento) y avisa los cambios con `playlist.updated`. Ya no
    existe la variante `hello`/`version` de server.py ni el 404 por pantalla
    inexistente; el detalle del bump se cubre en
    tests/test_sse_single_channel_iter38.py.
    """
    owner = _owner_headers()
    screen = requests.get(f"{BASE}/api/workspace/screens", headers=owner, timeout=30).json()[0]

    with requests.get(f"{BASE}/api/events/screen/{screen['id']}", stream=True, timeout=20) as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        chunks = []
        for line in stream.iter_lines(decode_unicode=True):
            chunks.append(line or "")
            if any(c.strip() == "event: connected" for c in chunks):
                break
        assert any(c.strip() == "event: connected" for c in chunks), chunks

    unknown = requests.get(f"{BASE}/api/events/screen/{uuid.uuid4()}", stream=True, timeout=20)
    assert unknown.status_code == 200
    unknown.close()

    bad_channel = requests.get(f"{BASE}/api/events/nope/{uuid.uuid4()}", timeout=20)
    assert bad_channel.status_code == 404


def test_connectivity_thresholds_are_real():
    from device_security import connectivity_from_heartbeat
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    assert connectivity_from_heartbeat(None) == "NEVER"
    assert connectivity_from_heartbeat(now - timedelta(seconds=10), now) == "ONLINE"
    assert connectivity_from_heartbeat(now - timedelta(seconds=120), now) == "STALE"
    assert connectivity_from_heartbeat(now - timedelta(minutes=30), now) == "OFFLINE"
