"""Pure playlist rules shared by API routes and the player pipeline."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from zoneinfo import ZoneInfo

PLAYLIST_ITEM_TYPES = {"menu", "media", "webpage"}
PLAYLIST_MODES = {"admin", "client", "public"}


def normalize_playlist_item(raw: dict[str, Any], index: int) -> dict[str, Any]:
    item_type = str(raw.get("type") or "").lower()
    if item_type not in PLAYLIST_ITEM_TYPES:
        raise ValueError(f"Unsupported playlist item type: {item_type or 'empty'}")
    ref_id = str(raw.get("ref_id") or "").strip()
    if not ref_id:
        raise ValueError("Playlist item ref_id is required")
    return {
        "id": str(raw.get("id") or uuid4()),
        "type": item_type,
        "ref_id": ref_id,
        "title": str(raw.get("title") or "Content")[:160],
        "duration": max(3, min(int(raw.get("duration") or 15), 86_400)),
        "transition": str(raw.get("transition") or "fade")[:24],
        "order": index,
    }


def normalize_playlist_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [normalize_playlist_item(item, index) for index, item in enumerate(items or [])]


def normalize_schedule(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    mode = "scheduled" if raw.get("mode") == "scheduled" else "always"
    days = sorted({int(day) for day in raw.get("days", range(7)) if 0 <= int(day) <= 6})
    return {
        "mode": mode,
        "timezone": str(raw.get("timezone") or "America/New_York")[:80],
        "days": days or list(range(7)),
        "start_time": str(raw.get("start_time") or "00:00")[:5],
        "end_time": str(raw.get("end_time") or "23:59")[:5],
        "start_date": raw.get("start_date") or None,
        "end_date": raw.get("end_date") or None,
    }


def _minutes(value: str, fallback: int) -> int:
    try:
        hours, minutes = map(int, value.split(":"))
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return hours * 60 + minutes
    except (TypeError, ValueError):
        pass
    return fallback


def schedule_is_active(schedule: dict[str, Any] | None, now: datetime | None = None) -> bool:
    schedule = normalize_schedule(schedule)
    if schedule["mode"] == "always":
        return True
    try:
        tz = ZoneInfo(schedule["timezone"])
    except Exception:
        tz = timezone.utc
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)
    start = _minutes(schedule["start_time"], 0)
    end = _minutes(schedule["end_time"], 1439)
    minute = current.hour * 60 + current.minute
    effective = current
    if end < start:
        if minute >= start:
            in_window = True
        elif minute <= end:
            in_window = True
            effective = current - timedelta(days=1)
        else:
            return False
    else:
        in_window = start <= minute <= end
    if not in_window or effective.weekday() not in schedule["days"]:
        return False
    effective_date = effective.date().isoformat()
    if schedule["start_date"] and effective_date < str(schedule["start_date"]):
        return False
    if schedule["end_date"] and effective_date > str(schedule["end_date"]):
        return False
    return True


def select_winning_playlist(playlists: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any] | None:
    active = [playlist for playlist in playlists if schedule_is_active(playlist.get("schedule"), now)]
    if not active:
        return None
    active.sort(
        key=lambda playlist: (
            int(playlist.get("priority") or 0),
            str(playlist.get("published_at") or playlist.get("updated_at") or ""),
        ),
        reverse=True,
    )
    return active[0]


def scheduled_playlist_key(playlists: list[dict[str, Any]], now: datetime | None = None) -> str:
    """Stable key for the current schedule winner; empty when none is active."""
    winner = select_winning_playlist(playlists, now)
    if not winner:
        return ""
    return hashlib.sha256(str(winner.get("id", "")).encode()).hexdigest()[:12]
