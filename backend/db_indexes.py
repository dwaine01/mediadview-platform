"""
db_indexes.py — MongoDB index definitions for MediaView
=========================================================
All production indexes in one place. Called at startup.

Why this matters:
  - Without these indexes, every auth query does a full collection scan.
  - At 500+ screens or 10K campaigns every heartbeat / campaign-scheduler
    tick / playlist lookup becomes O(N) and will time out.
  - This file is idempotent: safe to run on every startup.
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

logger = logging.getLogger(__name__)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create / verify all required indexes.  Non-fatal — logs errors but never
    raises so that a transient DB glitch during startup doesn't kill the process.
    """
    try:
        await _ensure_indexes(db)
        logger.info("✅  MongoDB indexes verified / created.")
    except Exception as exc:
        logger.error("⚠️  Failed to create MongoDB indexes: %s", exc, exc_info=True)


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    # ─────────────────────────────────────────────────────────────────────────
    #  users
    # ─────────────────────────────────────────────────────────────────────────
    await db.users.create_indexes([
        IndexModel([("email", ASCENDING)],             unique=True,  name="ux_users_email"),
        IndexModel([("role",  ASCENDING)],                            name="ix_users_role"),
        IndexModel([("rbac_role", ASCENDING)],                        name="ix_users_rbac_role"),
        IndexModel([("organization_id", ASCENDING)],                  name="ix_users_org_id"),
        IndexModel([("active", ASCENDING)],                           name="ix_users_active"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  screens
    # ─────────────────────────────────────────────────────────────────────────
    await db.screens.create_indexes([
        IndexModel([("id", ASCENDING)],                unique=True,  name="ux_screens_id"),
        # sparse=True: pairing_code is null on unprovisioned screens
        IndexModel([("pairing_code", ASCENDING)],
                   unique=True, sparse=True,           name="ux_screens_pairing_code"),
        IndexModel([("location_code", ASCENDING)],
                   unique=True, sparse=True,           name="ux_screens_location_code"),
        IndexModel([("organization_id", ASCENDING)],                 name="ix_screens_org_id"),
        IndexModel([("operation_type",  ASCENDING)],                 name="ix_screens_operation_type"),
        IndexModel([("status", ASCENDING)],                          name="ix_screens_status"),
        IndexModel([("active", ASCENDING)],                          name="ix_screens_active"),
        # Compound: tenant + type queries (most common RBAC-aware filter)
        IndexModel([("organization_id", ASCENDING), ("operation_type", ASCENDING)],
                   name="cx_screens_org_type"),
        # Public advertising screens
        IndexModel([("public_screen_code", ASCENDING)], sparse=True, name="ix_screens_public_code"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  devices
    # ─────────────────────────────────────────────────────────────────────────
    await db.devices.create_indexes([
        IndexModel([("id",         ASCENDING)], unique=True, sparse=True, name="ux_devices_id"),
        IndexModel([("device_id",  ASCENDING)], unique=True, sparse=True, name="ux_devices_device_id"),
        IndexModel([("screen_id",  ASCENDING)], sparse=True,              name="ix_devices_screen_id"),
        # Heartbeat recency queries (online/offline dashboard)
        IndexModel([("last_heartbeat", DESCENDING)], sparse=True,         name="ix_devices_heartbeat_desc"),
        # Compound: heartbeat queries scoped by screen list
        IndexModel([("screen_id", ASCENDING), ("last_heartbeat", DESCENDING)],
                   sparse=True, name="cx_devices_screen_heartbeat"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  campaigns (legacy self-service campaigns)
    # ─────────────────────────────────────────────────────────────────────────
    await db.campaigns.create_indexes([
        IndexModel([("id",        ASCENDING)], unique=True, name="ux_campaigns_id"),
        IndexModel([("user_id",   ASCENDING)],              name="ix_campaigns_user_id"),
        IndexModel([("screen_id", ASCENDING)],              name="ix_campaigns_screen_id"),
        IndexModel([("status",    ASCENDING)],              name="ix_campaigns_status"),
        IndexModel([("created_at", DESCENDING)],            name="ix_campaigns_created_desc"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  ad_campaigns (Phase 3 public advertising)
    # ─────────────────────────────────────────────────────────────────────────
    await db.ad_campaigns.create_indexes([
        IndexModel([("id",             ASCENDING)], unique=True, name="ux_adcampaigns_id"),
        IndexModel([("advertiser_id",  ASCENDING)],              name="ix_adcampaigns_advertiser"),
        IndexModel([("status",         ASCENDING)],              name="ix_adcampaigns_status"),
        IndexModel([("payment_status", ASCENDING)],              name="ix_adcampaigns_pay_status"),
        IndexModel([("created_at",     DESCENDING)],             name="ix_adcampaigns_created_desc"),
        # Campaign scheduler must scan by status + dates every tick
        IndexModel([("status", ASCENDING), ("start_date", ASCENDING), ("end_date", ASCENDING)],
                   name="cx_adcampaigns_sched"),
        IndexModel([("screen_codes", ASCENDING)], sparse=True,   name="ix_adcampaigns_screen_codes"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  media
    # ─────────────────────────────────────────────────────────────────────────
    await db.media.create_indexes([
        IndexModel([("id",          ASCENDING)], unique=True,  name="ux_media_id"),
        IndexModel([("user_id",     ASCENDING)],               name="ix_media_user_id"),
        IndexModel([("campaign_id", ASCENDING)], sparse=True,  name="ix_media_campaign_id"),
        IndexModel([("created_at",  DESCENDING)],              name="ix_media_created_desc"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  playlists
    # ─────────────────────────────────────────────────────────────────────────
    await db.playlists.create_indexes([
        IndexModel([("id",          ASCENDING)], unique=True, name="ux_playlists_id"),
        IndexModel([("owner_id",    ASCENDING)],              name="ix_playlists_owner"),
        IndexModel([("screen_ids",  ASCENDING)],              name="ix_playlists_screen_ids"),
        IndexModel([("status",      ASCENDING)],              name="ix_playlists_status"),
        IndexModel([("organization_id", ASCENDING)], sparse=True, name="ix_playlists_org"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  client_requests (Phase 4 managed portal)
    # ─────────────────────────────────────────────────────────────────────────
    await db.client_requests.create_indexes([
        IndexModel([("id",          ASCENDING)], unique=True, name="ux_creq_id"),
        IndexModel([("org_id",      ASCENDING)],              name="ix_creq_org"),
        IndexModel([("status",      ASCENDING)],              name="ix_creq_status"),
        IndexModel([("created_by",  ASCENDING)],              name="ix_creq_created_by"),
        IndexModel([("created_at",  DESCENDING)],             name="ix_creq_created_desc"),
        # Admin list: filter by status + recency
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)],
                   name="cx_creq_status_date"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  audit_logs (Phase 4)
    # ─────────────────────────────────────────────────────────────────────────
    await db.audit_logs.create_indexes([
        IndexModel([("id",            ASCENDING)], unique=True, name="ux_auditlog_id"),
        IndexModel([("action",        ASCENDING)],              name="ix_auditlog_action"),
        IndexModel([("user_id",       ASCENDING)], sparse=True, name="ix_auditlog_user"),
        IndexModel([("org_id",        ASCENDING)], sparse=True, name="ix_auditlog_org"),
        IndexModel([("resource_type", ASCENDING)], sparse=True, name="ix_auditlog_restype"),
        IndexModel([("created_at",    DESCENDING)],             name="ix_auditlog_date_desc"),
        # TTL: audit logs older than 2 years are automatically purged
        IndexModel([("created_at", ASCENDING)],
                   expireAfterSeconds=2 * 365 * 24 * 3600,
                   name="ttl_auditlog_2yr"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  proof_of_play
    # ─────────────────────────────────────────────────────────────────────────
    await db.proof_of_play.create_indexes([
        IndexModel([("campaign_id",  ASCENDING)],              name="ix_pop_campaign"),
        IndexModel([("screen_id",    ASCENDING)],              name="ix_pop_screen"),
        IndexModel([("played_at",    DESCENDING)],             name="ix_pop_played_desc"),
        IndexModel([("campaign_id", ASCENDING), ("played_at", DESCENDING)],
                   name="cx_pop_campaign_date"),
        # TTL: proof-of-play records older than 3 years auto-purge
        IndexModel([("played_at", ASCENDING)],
                   expireAfterSeconds=3 * 365 * 24 * 3600,
                   name="ttl_pop_3yr"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  organizations
    # ─────────────────────────────────────────────────────────────────────────
    await db.organizations.create_indexes([
        IndexModel([("id",           ASCENDING)], unique=True, name="ux_orgs_id"),
        IndexModel([("owner_id",     ASCENDING)],              name="ix_orgs_owner"),
        IndexModel([("subscription_status", ASCENDING)],       name="ix_orgs_sub_status"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  locations
    # ─────────────────────────────────────────────────────────────────────────
    await db.locations.create_indexes([
        IndexModel([("id",             ASCENDING)], unique=True, name="ux_locs_id"),
        IndexModel([("organization_id", ASCENDING)],            name="ix_locs_org"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  sessions (auth_v2 refresh tokens)
    # ─────────────────────────────────────────────────────────────────────────
    await db.sessions.create_indexes([
        IndexModel([("refresh_token", ASCENDING)], unique=True, name="ux_sessions_refresh_token"),
        IndexModel([("user_id",       ASCENDING)],              name="ix_sessions_user_id"),
        # TTL: auto-purge expired sessions (refresh token TTL = 30 days = 2592000s)
        IndexModel([("expires_at", ASCENDING)],
                   expireAfterSeconds=0,
                   name="ttl_sessions_expire"),
    ])

    # ─────────────────────────────────────────────────────────────────────────
    #  device_logs  (diagnostics logs from players)
    # ─────────────────────────────────────────────────────────────────────────
    await db.device_logs.create_indexes([
        IndexModel([("device_id",  ASCENDING)],              name="ix_devlogs_device"),
        IndexModel([("level",      ASCENDING)],              name="ix_devlogs_level"),
        IndexModel([("created_at", DESCENDING)],             name="ix_devlogs_date_desc"),
        # TTL: device logs older than 90 days auto-purge
        IndexModel([("created_at", ASCENDING)],
                   expireAfterSeconds=90 * 24 * 3600,
                   name="ttl_devlogs_90d"),
    ])
