"""campaigns_routes.py -- client-facing /campaigns/* CRUD: create, list,
get, update, replace-media (with its per-publication swap limit), delete.

Fase 2B-7 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md).
These are the 6 CLIENT-facing /campaigns/* routes deliberately left pending
in Fase 2B-6b (docs/FASE2B6_MAPA_RUTAS_ADMIN.md: "para no volver a tener un
PR gigante" -- moving them together with the admin campaign-moderation
routes would have coupled two unrelated PRs). Pure relocation of the 6
handlers below out of server.py: identical paths, methods, decorators and
logic, registered on a router with prefix="/api" so the final routes match
api_router exactly as before. No behavior change.

With this PR, server.py has zero remaining campaign business logic -- what's
left there is static pages, auth, and other not-yet-split domains.

Dependency notes:
  - gen_id and serialize_doc are threaded in, same pattern as every prior
    phase.
  - CampaignSchedule and calculate_campaign_price are threaded in too: both
    stay defined in server.py because they're used by code that is NOT
    moving here -- CampaignSchedule and calculate_campaign_price are already
    threaded into screens_routes.py's create_screens_routes(...) factory
    (calc_price's request-body type and pricing helper), and
    calculate_campaign_price is also called directly by server.py's
    demo-seed-data path. Same precedent, not re-invented here.
  - screen_orientation is threaded in for the same reason: it stays in
    server.py because it's already threaded into player_routes.py's
    create_player_domain_routes(...) factory. screens_routes.py's own
    docstring flagged this explicitly when it chose NOT to thread
    screen_orientation there ("it should be threaded when whichever later
    phase (campaigns or player) actually calls it needs to") -- this is
    that later phase.
  - db (database.py) and get_current_user (deps.py) are imported directly.
  - MEDIA_METADATA_PROJECTION and bump_playlist_version (media_utils.py) are
    imported directly, exactly as server.py already does.
  - normalise_schedule (media_utils.py) is imported directly too -- it moved
    there in Fase 2B-6b specifically so both the admin campaign-repair route
    (admin_campaigns_routes.py) and these client campaign routes could share
    it without threading. This PR is why that relocation was done ahead of
    time.
  - CampaignCreate and CampaignUpdate are NOT plain module-level models:
    both embed `schedule: CampaignSchedule` as a field, and CampaignSchedule
    is a threaded factory parameter (not an importable module-level name
    here), so both classes are defined INSIDE create_campaigns_routes(...),
    right after the router is created -- same reindent/dedent byte-exact
    verification as every route body, just for a class definition instead
    of a function definition.
  - MAX_MEDIA_CHANGES moves here as a plain constant and CampaignMediaReplace
    as a plain model: grep-verified across every file in backend/ that
    neither has any call site outside these 6 routes.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from deps import get_current_user
from media_utils import (
    MEDIA_METADATA_PROJECTION,
    bump_playlist_version,
    normalise_schedule,
)

MAX_MEDIA_CHANGES = 2


class CampaignMediaReplace(BaseModel):
    media_ids: List[str]


def create_campaigns_routes(gen_id, serialize_doc, CampaignSchedule, calculate_campaign_price, screen_orientation):
    router = APIRouter(prefix="/api", tags=["Campaigns"])

    class CampaignCreate(BaseModel):
        name: str
        screen_id: str
        schedule: CampaignSchedule
        media_ids: List[str] = []

    class CampaignUpdate(BaseModel):
        name: Optional[str] = None
        schedule: Optional[CampaignSchedule] = None
        media_ids: Optional[List[str]] = None

    @router.post("/campaigns")
    async def create_campaign(data: CampaignCreate, current_user: dict = Depends(get_current_user)):
        screen = await db.screens.find_one({"id": data.screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        # Normalise the schedule so empty strings never leak into the DB.
        # start_date/end_date=None means "no bound" (always valid on that side).
        sched = normalise_schedule(data.schedule.dict())
        if sched.get("start_date") and sched.get("end_date") and sched["start_date"] > sched["end_date"]:
            raise HTTPException(status_code=400, detail="start_date must be <= end_date")

        # Every media_id must resolve to a real media doc.
        missing = []
        for mid in (data.media_ids or []):
            if not await db.media.find_one({"id": mid}, {"_id": 1}):
                missing.append(mid)
        if missing:
            raise HTTPException(status_code=400,
                detail=f"Media not found: {', '.join(missing)}. Please re-upload.")

        # Orientation gate: a portrait file on a landscape screen (or vice versa)
        # can only be shown with black bars, so it is rejected up front.
        required = screen_orientation(screen)
        for mid in (data.media_ids or []):
            media = await db.media.find_one({"id": mid}, {"orientation": 1})
            found = (media or {}).get("orientation")
            if found and found not in ("square", required):
                raise HTTPException(status_code=422, detail={
                    "message": ("Tu archivo es " + ("vertical" if found == "portrait" else "horizontal")
                                + " y esta pantalla es " + ("vertical" if required == "portrait" else "horizontal")
                                + ". Sube el archivo en la orientación correcta."),
                    "required_orientation": required,
                    "file_orientation": found,
                })

        pricing = calculate_campaign_price(screen.get("pricing", {}), sched)
        campaign = {
            "id": gen_id(), "user_id": current_user["id"],
            "screen_id": data.screen_id, "name": data.name,
            "status": "draft", "schedule": sched,
            "media_ids": data.media_ids, "pricing": pricing,
            "payment_id": None, "admin_notes": None,
            "needs_attention": False,
            "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
        }
        await db.campaigns.insert_one(campaign)
        return serialize_doc(campaign)

    @router.get("/campaigns")
    async def list_campaigns(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
        query = {"user_id": current_user["id"]}
        if status:
            query["status"] = status
        else:
            # Publications the customer deleted stay in the books but not in their portal.
            query["status"] = {"$ne": "archived"}
        campaigns = await db.campaigns.find(query).sort("created_at", -1).to_list(100)
        enriched = []
        for c in campaigns:
            screen = await db.screens.find_one({"id": c.get("screen_id")}, {"advertising": 0})
            c["screen"] = serialize_doc(screen) if screen else None
            c["media_changes_used"] = int(c.get("media_changes_used", 0))
            c["media_changes_left"] = max(0, MAX_MEDIA_CHANGES - c["media_changes_used"])
            enriched.append(c)
        return serialize_doc(enriched)

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
        campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        screen = await db.screens.find_one({"id": campaign.get("screen_id")})
        campaign["screen"] = serialize_doc(screen) if screen else None
        media_items = []
        for mid in campaign.get("media_ids", []):
            media = await db.media.find_one({"id": mid}, MEDIA_METADATA_PROJECTION)
            if media:
                media_items.append(serialize_doc(media))
        campaign["media"] = media_items
        if campaign.get("payment_id"):
            payment = await db.payments.find_one({"id": campaign["payment_id"]})
            campaign["payment"] = serialize_doc(payment)
        campaign["media_changes_used"] = int(campaign.get("media_changes_used", 0))
        campaign["media_changes_left"] = max(0, MAX_MEDIA_CHANGES - campaign["media_changes_used"])
        campaign["screen_orientation"] = screen_orientation(screen)
        return serialize_doc(campaign)

    @router.put("/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, data: CampaignUpdate, current_user: dict = Depends(get_current_user)):
        campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign["status"] not in ["draft", "rejected"]:
            raise HTTPException(status_code=400, detail="Can only edit draft or rejected campaigns")
        update = {k: v for k, v in data.dict().items() if v is not None}
        if "schedule" in update and data.schedule:
            update["schedule"] = normalise_schedule(data.schedule.dict())
            screen = await db.screens.find_one({"id": campaign["screen_id"]})
            if screen:
                update["pricing"] = calculate_campaign_price(screen.get("pricing", {}), update["schedule"])
        # If media_ids are being changed, verify they resolve and clear the
        # needs_attention flag if the campaign now has valid media.
        if "media_ids" in update and update["media_ids"] is not None:
            missing = []
            for mid in update["media_ids"]:
                if not await db.media.find_one({"id": mid}, {"_id": 1}):
                    missing.append(mid)
            if missing:
                raise HTTPException(status_code=400,
                    detail=f"Media not found: {', '.join(missing)}. Please re-upload.")
            if update["media_ids"]:
                update["needs_attention"] = False
        update["updated_at"] = datetime.utcnow()
        await db.campaigns.update_one({"id": campaign_id}, {"$set": update})
        await bump_playlist_version(campaign.get("screen_id"), reason="campaign updated")
        return {"message": "Campaign updated"}

    @router.put("/campaigns/{campaign_id}/media")
    async def replace_campaign_media(campaign_id: str, data: CampaignMediaReplace,
                                     current_user: dict = Depends(get_current_user)):
        """Marketplace customers may swap the creative of their own publication.

    Business rules (marketplace, QR customers):
      • hard limit of MAX_MEDIA_CHANGES swaps per publication (lifetime)
      • screen and dates never change
      • the new file must match the screen orientation, otherwise it would show
        with black bars on the TV
    """
        campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign.get("status") == "archived":
            raise HTTPException(status_code=400, detail="This publication was deleted")
        if not data.media_ids:
            raise HTTPException(status_code=400, detail="media_ids cannot be empty")

        used = int(campaign.get("media_changes_used", 0))
        if used >= MAX_MEDIA_CHANGES:
            raise HTTPException(status_code=409, detail={
                "message": f"Ya usaste tus {MAX_MEDIA_CHANGES} cambios de archivo para esta publicación.",
                "media_changes_used": used,
                "media_changes_allowed": MAX_MEDIA_CHANGES,
            })

        screen = await db.screens.find_one({"id": campaign.get("screen_id")}, {"specs": 1, "name": 1, "id": 1})
        required = screen_orientation(screen)
        for mid in data.media_ids:
            media = await db.media.find_one({"id": mid})
            if not media:
                raise HTTPException(status_code=400, detail=f"Media not found: {mid}")
            found = media.get("orientation")
            if found and found != "square" and found != required:
                raise HTTPException(status_code=422, detail={
                    "message": ("Tu archivo es " + ("vertical" if found == "portrait" else "horizontal")
                                + " y esta pantalla es " + ("vertical" if required == "portrait" else "horizontal")
                                + ". Sube el archivo en la orientación correcta — este cambio no se ha consumido."),
                    "required_orientation": required,
                    "file_orientation": found,
                })

        now = datetime.utcnow()
        await db.campaigns.update_one({"id": campaign_id}, {"$set": {
            "media_ids": data.media_ids,
            "media_changes_used": used + 1,
            "needs_attention": False,
            "last_media_change_at": now,
            "updated_at": now,
        }})
        await bump_playlist_version(campaign.get("screen_id"), reason="customer replaced creative")
        return {
            "id": campaign_id,
            "media_ids": data.media_ids,
            "media_changes_used": used + 1,
            "media_changes_left": MAX_MEDIA_CHANGES - (used + 1),
        }

    @router.delete("/campaigns/{campaign_id}")
    async def delete_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
        """Owner removes their publication.

    Drafts are deleted outright. A publication that was already paid for is
    ARCHIVED instead: it disappears from the TV immediately and frees the slot,
    but the payment history is preserved (no refund is issued).
    """
        campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign["status"] == "draft":
            await db.campaigns.delete_one({"id": campaign_id})
            await bump_playlist_version(campaign.get("screen_id"), reason="campaign deleted")
            return {"message": "Campaign deleted", "refunded": False}
        now = datetime.utcnow()
        await db.campaigns.update_one({"id": campaign_id}, {"$set": {
            "status": "archived",
            "archived_at": now,
            "archived_by": current_user["id"],
            "updated_at": now,
        }})
        await bump_playlist_version(campaign.get("screen_id"), reason="customer deleted publication")
        return {"message": "Publication removed from the screen", "refunded": False}

    return router
