"""Iteración 38 — el SSE de pantallas tiene UNA sola implementación.

Antes había dos rutas para /api/events/screen/{id}: la de `realtime.py`
(`connected` + `playlist.updated`, que es lo que el player escucha) y una de
`server.py` que emitía `hello`/`version` y, al registrarse primero, dejaba al
player sin sincronización en tiempo real. Ahora solo existe la de `realtime.py`,
que además vigila `playlist_version` en Mongo para que un bump hecho por otro
proceso también llegue.
"""

import os
import re
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        yield db
    finally:
        client.close()


def test_only_one_sse_route_is_registered():
    """El código solo debe declarar un handler para el canal de eventos."""
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    declared = []
    for name in sorted(os.listdir(backend)):
        if not name.endswith(".py"):
            continue
        source = open(os.path.join(backend, name), encoding="utf-8").read()
        declared += [
            f"{name}:{match}"
            for match in re.findall(r'@\w+\.get\("(/(?:api/)?events/[^"]+)"', source)
        ]
    assert declared == ["realtime.py:/events/{channel}/{rid}"], declared


def test_unknown_screen_still_opens_the_stream():
    """Contrato de iteración 9: 200 + `event: connected` aunque la pantalla no exista."""
    with requests.get(
        f"{BASE_URL}/api/events/screen/TEST-sse-{uuid.uuid4().hex[:8]}",
        stream=True, timeout=(10, 30),
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in (response.headers.get("content-type") or "")
        lines = []
        for raw in response.iter_lines(decode_unicode=True):
            lines.append(raw or "")
            if len(lines) > 8:
                break
        assert any(line.strip() == "event: connected" for line in lines)


def test_version_bump_reaches_the_stream(mongo_db):
    """Un bump de playlist_version en Mongo (otro proceso) emite playlist.updated."""
    screen_id = f"TEST-sse-{uuid.uuid4().hex[:8]}"
    mongo_db.screens.insert_one({"id": screen_id, "name": "sse probe", "playlist_version": 1})
    try:
        with requests.get(
            f"{BASE_URL}/api/events/screen/{screen_id}", stream=True, timeout=(10, 30),
        ) as response:
            assert response.status_code == 200
            lines = response.iter_lines(decode_unicode=True)
            for raw in lines:  # consume hasta el connected
                if (raw or "").strip() == "event: connected":
                    break
            time.sleep(1)
            mongo_db.screens.update_one({"id": screen_id}, {"$set": {"playlist_version": 2}})
            deadline = time.time() + 20
            seen = []
            for raw in lines:
                seen.append(raw or "")
                if (raw or "").strip() == "event: playlist.updated":
                    break
                if time.time() > deadline:
                    pytest.fail(f"no llegó playlist.updated; visto: {seen}")
            assert any(line.strip() == "event: playlist.updated" for line in seen), seen
    finally:
        mongo_db.screens.delete_one({"id": screen_id})
