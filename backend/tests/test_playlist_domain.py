from datetime import datetime

import pytest
from zoneinfo import ZoneInfo

from playlist_domain import (
    normalize_playlist_items,
    schedule_is_active,
    scheduled_playlist_key,
    select_winning_playlist,
)


def test_normalizes_mixed_playlist_items_in_order():
    items = normalize_playlist_items([
        {"type": "menu", "ref_id": "menu-1", "title": "Lunch", "duration": 30},
        {"type": "media", "ref_id": "media-1", "title": "Promo", "duration": 2},
    ])
    assert [item["type"] for item in items] == ["menu", "media"]
    assert [item["order"] for item in items] == [0, 1]
    assert items[1]["duration"] == 3


def test_rejects_unknown_playlist_item_type():
    with pytest.raises(ValueError):
        normalize_playlist_items([{"type": "unknown", "ref_id": "x"}])


def test_schedule_supports_overnight_windows():
    tz = ZoneInfo("America/New_York")
    schedule = {
        "mode": "scheduled",
        "timezone": "America/New_York",
        "days": [0],
        "start_time": "22:00",
        "end_time": "02:00",
    }
    assert schedule_is_active(schedule, datetime(2026, 9, 7, 23, 0, tzinfo=tz))
    assert not schedule_is_active(schedule, datetime(2026, 9, 7, 12, 0, tzinfo=tz))


def test_overnight_tail_belongs_to_previous_scheduled_day():
    tz = ZoneInfo("America/New_York")
    schedule = {"mode": "scheduled", "timezone": "America/New_York", "days": [4],
                "start_time": "22:00", "end_time": "02:00"}
    assert schedule_is_active(schedule, datetime(2026, 9, 5, 1, 0, tzinfo=tz))
    assert not schedule_is_active(schedule, datetime(2026, 9, 6, 1, 0, tzinfo=tz))


def test_highest_priority_active_playlist_wins():
    now = datetime(2026, 9, 7, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    winner = select_winning_playlist([
        {"id": "base", "priority": 10, "schedule": {"mode": "always"}},
        {"id": "lunch", "priority": 50, "schedule": {"mode": "scheduled", "days": [0], "start_time": "11:00", "end_time": "14:00"}},
    ], now)
    assert winner["id"] == "lunch"


def test_schedule_boundary_changes_lightweight_player_version():
    tz = ZoneInfo("America/New_York")
    playlists = [
        {"id": "base", "priority": 10, "schedule": {"mode": "always"}},
        {"id": "lunch", "priority": 50, "schedule": {"mode": "scheduled", "days": [0],
         "start_time": "11:00", "end_time": "14:00", "timezone": "America/New_York"}},
    ]
    morning = scheduled_playlist_key(playlists, datetime(2026, 9, 7, 10, 0, tzinfo=tz))
    lunch = scheduled_playlist_key(playlists, datetime(2026, 9, 7, 12, 0, tzinfo=tz))
    assert morning != lunch
