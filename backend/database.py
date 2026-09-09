"""Owns the single Mongo client/database handle.

Extracted out of server.py (Fase 2A of the modularization plan - see
docs/AGENT_COORDINATION.md and docs/REFACTOR_FASE2_PLAN.md) so that
deps.py and media_utils.py can import `db` without creating a circular
import with server.py: server.py in turn imports get_current_user /
require_admin / require_superadmin from deps.py, and media_orientation /
_media_has_inline_bytes / bump_playlist_version from media_utils.py.

Pure relocation: same MONGO_URL/DB_NAME resolution, same
AsyncIOMotorClient instance, same object identity server.py already used.
No behavior change.
"""
import os

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ.get('DB_NAME', 'mediaview_db')

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
