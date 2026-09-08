"""
MediAd View — Real-time WebSocket module

Provides live sync between the admin editor and TV/player screens:
- When an admin edits a menu, category or item → TVs refresh instantly.
- When an admin pushes new content to a screen → the player reloads immediately.
- Removes the need for polling.

Usage from server.py:

    from realtime import manager, ws_router
    app.include_router(ws_router)                     # exposes /api/ws/{channel}/{id}
    await manager.broadcast_menu(menu_id, "updated")  # inside any menu mutation
    await manager.broadcast_screen(screen_id, "reload")

Channels:
    menu    → notifies TV displays showing that menu
    screen  → notifies player/APK bound to that screen
    device  → notifies Colorlight A40 direct-mode devices
"""
import asyncio
import json
import logging
import time
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

logger = logging.getLogger("realtime")
logger.setLevel(logging.INFO)


class ConnectionManager:
    """Tracks active WebSocket clients grouped by (channel, resource_id)."""

    def __init__(self):
        # {(channel, id): set(WebSocket)}
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._event_rooms: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(channel: str, rid: str) -> str:
        return f"{channel}:{rid}"

    async def connect(self, ws: WebSocket, channel: str, rid: str):
        await ws.accept()
        key = self._key(channel, rid)
        async with self._lock:
            self._rooms.setdefault(key, set()).add(ws)
        try:
            await ws.send_json({"type": "connected", "channel": channel, "id": rid})
        except Exception:
            pass
        logger.info(f"WS connected → {key} (total in room: {len(self._rooms[key])})")

    async def disconnect(self, ws: WebSocket, channel: str, rid: str):
        key = self._key(channel, rid)
        async with self._lock:
            room = self._rooms.get(key)
            if room:
                room.discard(ws)
                if not room:
                    self._rooms.pop(key, None)
        logger.info(f"WS disconnected ← {key}")

    async def _broadcast(self, key: str, payload: dict):
        """Send a payload to every WebSocket and SSE subscriber in the room."""
        room = list(self._rooms.get(key, set()))
        dead = []
        for ws in room:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._rooms.get(key, set()).discard(ws)
        for queue in list(self._event_rooms.get(key, set())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)

    async def subscribe_events(self, channel: str, rid: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        async with self._lock:
            self._event_rooms.setdefault(self._key(channel, rid), set()).add(queue)
        return queue

    async def unsubscribe_events(self, channel: str, rid: str, queue: asyncio.Queue):
        key = self._key(channel, rid)
        async with self._lock:
            room = self._event_rooms.get(key)
            if room:
                room.discard(queue)
                if not room:
                    self._event_rooms.pop(key, None)

    async def broadcast_menu(self, menu_id: str, event: str = "updated", data: dict | None = None):
        await self._broadcast(self._key("menu", menu_id),
                              {"type": "menu", "event": event, "menu_id": menu_id,
                               "data": data or {}})

    async def broadcast_screen(self, screen_id: str, event: str = "reload", data: dict | None = None):
        await self._broadcast(self._key("screen", screen_id),
                              {"type": "screen", "event": event, "screen_id": screen_id,
                               "data": data or {}})

    async def broadcast_device(self, device_id: str, event: str, data: dict | None = None):
        await self._broadcast(self._key("device", device_id),
                              {"type": "device", "event": event, "device_id": device_id,
                               "data": data or {}})

    async def broadcast_dashboard(self, event: str, data: dict | None = None, scope: str = "global"):
        """Broadcast a finance/business event to admin dashboard subscribers.

        `event` examples: 'order.created', 'order.approved', 'payment.captured',
        'refund.executed', 'invoice.issued'.
        `scope` allows narrowing (e.g. 'global', 'finance', 'admin')."""
        await self._broadcast(self._key("dashboard", scope),
                              {"type": "dashboard", "event": event,
                               "scope": scope, "data": data or {}})

    def room_size(self, channel: str, rid: str) -> int:
        return len(self._rooms.get(self._key(channel, rid), set()))

    def event_room_size(self, channel: str, rid: str) -> int:
        return len(self._event_rooms.get(self._key(channel, rid), set()))


# Singleton
manager = ConnectionManager()


# The SSE channel for a screen also watches `playlist_version` in Mongo, so a
# version bump made by another process (worker, scheduler or a second Render
# instance) still reaches the player. server.py registers the reader at boot.
_screen_version_reader = None


def set_screen_version_reader(reader):
    """`reader(screen_id) -> int | None` (None = screen not found)."""
    global _screen_version_reader
    _screen_version_reader = reader


async def _read_screen_version(screen_id: str):
    """Never let a DB hiccup kill a live stream: on error keep the last value."""
    if _screen_version_reader is None:
        return None
    try:
        return await _screen_version_reader(screen_id)
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("screen version read failed for %s: %s", screen_id, error)
        return None


ws_router = APIRouter(prefix="/api")


@ws_router.websocket("/ws/{channel}/{rid}")
async def ws_endpoint(ws: WebSocket, channel: str, rid: str):
    """Generic subscribe endpoint. channel ∈ {menu, screen, device}."""
    if channel not in ("menu", "screen", "device", "dashboard"):
        await ws.close(code=1008, reason="invalid channel")
        return

    await manager.connect(ws, channel, rid)
    try:
        while True:
            # Passive: we don't require the client to send anything.
            # But if it sends a ping/keep-alive we echo it.
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(ws, channel, rid)
    except Exception as e:
        logger.exception(f"WS error on {channel}:{rid} → {e}")
        await manager.disconnect(ws, channel, rid)


@ws_router.get("/events/{channel}/{rid}")
async def sse_endpoint(channel: str, rid: str):
    """Server-Sent Events for native players, with periodic keep-alives.

    This is the ONLY SSE implementation: the player listens on
    /api/events/screen/{screen_id} and reacts to `playlist.updated` / `reload`.
    """
    if channel not in ("menu", "screen", "device"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Invalid event channel")

    async def stream():
        queue = await manager.subscribe_events(channel, rid)
        watch_version = channel == "screen" and _screen_version_reader is not None
        last_version = None
        idle_since = time.monotonic()
        try:
            yield "retry: 5000\nevent: connected\ndata: {}\n\n"
            if watch_version:
                last_version = await _read_screen_version(rid)
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=2)
                    event = str(payload.get("event") or "message")
                    data = json.dumps(payload, separators=(",", ":"), default=str)
                    idle_since = time.monotonic()
                    if watch_version:
                        last_version = await _read_screen_version(rid)
                    yield f"event: {event}\ndata: {data}\n\n"
                    continue
                except asyncio.TimeoutError:
                    pass

                # A bump from another process/instance never reaches the queue,
                # so the screen channel also polls the stored version.
                if watch_version:
                    version = await _read_screen_version(rid)
                    if version is not None and version != last_version:
                        last_version = version
                        idle_since = time.monotonic()
                        yield (
                            'event: playlist.updated\n'
                            f'data: {{"type":"screen","event":"playlist.updated",'
                            f'"screen_id":{json.dumps(rid)},"version":{int(version)}}}\n\n'
                        )
                        continue

                if time.monotonic() - idle_since >= 20:
                    idle_since = time.monotonic()
                    yield "event: keepalive\ndata: {}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            await manager.unsubscribe_events(channel, rid, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
