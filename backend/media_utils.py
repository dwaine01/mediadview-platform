"""Small media/playlist helpers shared across server.py's route handlers.

Extracted from server.py (Fase 2A). Pure relocation: same logic, same
behavior, now importable directly by any future per-domain route module
without threading them through server.py as factory parameters.

Note: playlist item validation/normalization for the real /playlists/*
routes already lives in playlist_domain.py (normalize_playlist_items and
friends) - that module was not touched here. The separate
_build_playlist_items closure inside workspace_routes.py serves a
different, org-scoped workspace API and stays where it is; it is not a
server.py helper and is out of scope for this move.
"""
import logging
from datetime import datetime
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


def media_orientation(width: Optional[int], height: Optional[int]) -> Optional[str]:
    """portrait | landscape | square — None when the size is unknown."""
    if not width or not height:
        return None
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


async def _media_has_inline_bytes(media_id: str) -> bool:
    """True when the media document still carries the file as base64.

    Legacy uploads live on the container filesystem, which Render wipes on every
    deploy — but the same document usually keeps a base64 copy in Mongo, and
    /api/player/media/{id} can serve it. Without this check the playlist dropped
    perfectly playable items just because the disk copy was gone.
    """
    return await db.media.count_documents(
        {"id": media_id, "data": {"$exists": True, "$nin": [None, ""]}}, limit=1) > 0


async def bump_playlist_version(screen_id: str, reason: str = ""):
    """Increment the playlist_version counter for a screen. Any code path
    that changes what a screen should play MUST call this so the player
    can detect it via GET /api/player/{id}/version and resync."""
    if not screen_id:
        return
    try:
        r = await db.screens.update_one(
            {"id": screen_id},
            {"$inc": {"playlist_version": 1},
             "$set": {"playlist_version_updated_at": datetime.utcnow(),
                      "playlist_version_reason": reason}}
        )
        if r.matched_count:
            logger.info(f"playlist_version bumped for screen={screen_id} reason={reason}")
            try:
                from realtime import manager as realtime_manager
                await realtime_manager.broadcast_screen(
                    screen_id,
                    "playlist.updated",
                    {"reason": reason},
                )
            except Exception as event_error:
                logger.warning("playlist realtime event failed for %s: %s", screen_id, event_error)
    except Exception as e:
        logger.warning(f"bump_playlist_version failed for {screen_id}: {e}")
