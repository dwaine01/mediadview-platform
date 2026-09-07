"""
workspace_routes.py — Tenant-scoped Customer Workspace API.
Phase 2C P1: Routes for SELF_SERVICE_OWNER / SELF_SERVICE_MANAGER roles.
All data is strictly scoped to user.organization_id — NO cross-tenant leakage.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from org_branding_routes import OrgLogoUpload, delete_org_logo, save_org_logo
from rbac import Role, get_effective_role

_WORKSPACE_ROLES = frozenset({
    Role.SELF_SERVICE_OWNER,
    Role.SELF_SERVICE_MANAGER,
})


def _norm_orientation(value) -> str:
    """portrait or landscape — anything else falls back to landscape."""
    return "portrait" if str(value or "").strip().lower() == "portrait" else "landscape"


def _ser(doc):
    if isinstance(doc, list):
        return [_ser(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                continue
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                out[k] = _ser(v)
            else:
                out[k] = v
        return out
    return doc


def create_workspace_routes(db, get_current_user, require_admin):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Phase 2C"])

    async def require_workspace_user(current_user: dict = Depends(get_current_user)):
        """Gate: only SELF_SERVICE_OWNER and SELF_SERVICE_MANAGER can access workspace routes."""
        role = get_effective_role(current_user)
        if role not in _WORKSPACE_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Workspace access requires SELF_SERVICE_OWNER or SELF_SERVICE_MANAGER role",
            )
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(
                status_code=403,
                detail="You must be associated with an organization. Complete account setup first.",
            )
        return current_user

    @router.get("/context", summary="Workspace context: org + subscription + plan stats")
    async def workspace_context(current_user: dict = Depends(require_workspace_user)):
        """Full workspace context: org info, subscription lifecycle, plan config, and stats."""
        org_id = current_user["organization_id"]

        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Phase 2C subscription (latest)
        sub = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2},
            sort=[("created_at", -1)],
        )

        # Current pricing agreement
        pricing = None
        if sub and sub.get("current_pricing_agreement_id"):
            pricing = await db.pricing_agreements.find_one(
                {"id": sub["current_pricing_agreement_id"]}
            )

        # Plan config from plans collection
        plan_id = None
        if pricing:
            plan_id = pricing.get("plan_id")
        elif sub:
            plan_id = sub.get("plan")
        else:
            plan_id = org.get("plan", "free")

        plan_config = await db.plans.find_one({"plan_id": plan_id}) if plan_id else None

        # Stats (parallel-friendly counts)
        screen_count = await db.screens.count_documents({"organization_id": org_id})
        user_count   = await db.users.count_documents({"organization_id": org_id})

        # Devices — scoped through org screens
        org_screen_ids = [
            s["id"]
            for s in await db.screens.find(
                {"organization_id": org_id}, {"id": 1}
            ).to_list(1000)
        ]
        device_count = (
            await db.devices.count_documents({"screen_id": {"$in": org_screen_ids}})
            if org_screen_ids else 0
        )
        # Online = heartbeat within the last 2 minutes (same window the admin panel uses).
        online_count = (
            await db.devices.count_documents({
                "screen_id": {"$in": org_screen_ids},
                "last_heartbeat": {"$gte": datetime.utcnow() - timedelta(minutes=2)},
            })
            if org_screen_ids else 0
        )

        return {
            "organization": _ser(org),
            "subscription": _ser(sub),
            "pricing_agreement": _ser(pricing),
            "plan_config": _ser(plan_config),
            "stats": {
                "screens": screen_count,
                "users": user_count,
                "devices": device_count,
                "devices_online": online_count,
                "devices_offline": max(0, device_count - online_count),
            },
            "current_user": {
                "id": current_user.get("id"),
                "name": current_user.get("name"),
                "email": current_user.get("email"),
                "rbac_role": current_user.get("rbac_role"),
                "organization_id": org_id,
            },
        }

    @router.post("/logo", summary="Upload or replace the organization logo")
    async def workspace_upload_logo(data: OrgLogoUpload, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organización no encontrada")

        new_url = save_org_logo(data.logo_filename, data.logo_base64)
        await db.organizations.update_one(
            {"id": org_id}, {"$set": {"logo_url": new_url, "updated_at": datetime.utcnow()}}
        )
        delete_org_logo(org.get("logo_url"))
        return {"logo_url": new_url}

    @router.delete("/logo", summary="Remove the organization logo")
    async def workspace_delete_logo(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organización no encontrada")

        await db.organizations.update_one(
            {"id": org_id}, {"$set": {"logo_url": None, "updated_at": datetime.utcnow()}}
        )
        delete_org_logo(org.get("logo_url"))
        return {"logo_url": None}

    @router.get("/screens", summary="List org-scoped screens")
    async def workspace_screens(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        screens = await db.screens.find(
            {"organization_id": org_id}
        ).sort("created_at", -1).to_list(500)
        return _ser(screens)

    @router.get("/devices", summary="List org-scoped devices (via org screens)")
    async def workspace_devices(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        org_screens = await db.screens.find(
            {"organization_id": org_id}, {"id": 1, "name": 1}
        ).to_list(500)
        if not org_screens:
            return []
        screen_map = {s["id"]: s.get("name", "Unknown") for s in org_screens}
        screen_ids = list(screen_map.keys())
        devices = await db.devices.find(
            {"screen_id": {"$in": screen_ids}}
        ).sort("created_at", -1).to_list(500)
        result = []
        for d in devices:
            dd = _ser(d)
            dd["screen_name"] = screen_map.get(d.get("screen_id"), "Unknown")
            result.append(dd)
        return result

    @router.get("/media", summary="List org media library")
    async def workspace_media(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        # Collect all user IDs in this org
        org_user_ids = [
            u["id"]
            for u in await db.users.find(
                {"organization_id": org_id}, {"id": 1}
            ).to_list(500)
        ]
        # Fallback: also include the current user
        uid = current_user.get("id")
        if uid and uid not in org_user_ids:
            org_user_ids.append(uid)
        media = await db.media.find(
            {"user_id": {"$in": org_user_ids}}
        ).sort("created_at", -1).to_list(1000)
        return _ser(media)

    @router.get("/playlists", summary="List org-scoped playlists")
    async def workspace_playlists(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        screen_ids = [
            s["id"]
            for s in await db.screens.find(
                {"organization_id": org_id}, {"id": 1}
            ).to_list(500)
        ]
        if not screen_ids:
            return []
        playlists = await db.playlists.find(
            {"screen_ids": {"$in": screen_ids}}
        ).sort("created_at", -1).to_list(500)
        return _ser(playlists)

    @router.get("/schedules", summary="List org-scoped campaigns/schedules")
    async def workspace_schedules(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        screen_ids = [
            s["id"]
            for s in await db.screens.find(
                {"organization_id": org_id}, {"id": 1}
            ).to_list(500)
        ]
        if not screen_ids:
            return []
        campaigns = await db.campaigns.find(
            {"screen_id": {"$in": screen_ids}}
        ).sort("created_at", -1).to_list(500)
        return _ser(campaigns)

    @router.get("/users", summary="List org users (excluding password hashes)")
    async def workspace_users(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        users = await db.users.find(
            {"organization_id": org_id},
            {"password_hash": 0, "_id": 0},
        ).sort("created_at", -1).to_list(500)
        return _ser(users)

    @router.get("/billing", summary="Billing: subscription + pricing agreement history")
    async def workspace_billing(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]

        sub = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2},
            sort=[("created_at", -1)],
        )

        pricing_history = []
        if sub:
            pas = await db.pricing_agreements.find(
                {"subscription_id": sub["id"]}
            ).sort("version", 1).to_list(50)
            pricing_history = _ser(pas)

        current_pa = None
        if sub and sub.get("current_pricing_agreement_id"):
            current_pa = await db.pricing_agreements.find_one(
                {"id": sub["current_pricing_agreement_id"]}
            )

        plan_id = (current_pa or {}).get("plan_id") or (sub or {}).get("plan")
        plan_config = await db.plans.find_one({"plan_id": plan_id}) if plan_id else None

        return {
            "subscription": _ser(sub),
            "current_pricing_agreement": _ser(current_pa),
            "pricing_history": pricing_history,
            "plan_config": _ser(plan_config),
        }

    # ══════════════════════════════════════════════════════════════════════
    # SCREEN MANAGEMENT — customer-side
    # ══════════════════════════════════════════════════════════════════════

    @router.post("/screens", summary="Create a new screen for the org", status_code=201)
    async def workspace_create_screen(data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        now = datetime.utcnow()

        screen_name = (data.get("name") or "").strip()
        if not screen_name:
            raise HTTPException(status_code=400, detail="Screen name is required")

        screen = {
            "id": str(_uuid.uuid4()),
            "name": screen_name,
            "organization_id": org_id,
            "location": data.get("location"),
            "status": "offline",
            "code": None,
            "active_menu_id": None,
            "active_playlist_id": None,
            # Stored inside `specs` like admin screens do: the player and the
            # marketplace both read specs.orientation.
            "specs": {"orientation": _norm_orientation(data.get("orientation"))},
            "created_by": current_user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await db.screens.insert_one(screen)
        return _ser(screen)

    @router.patch("/screens/{screen_id}", summary="Rename a screen or change its orientation")
    async def workspace_update_screen(screen_id: str, data: dict,
                                      current_user: dict = Depends(require_workspace_user)):
        if get_effective_role(current_user) not in _SCREEN_ADMIN_ROLES:
            raise HTTPException(403, "Tu rol no puede editar pantallas. Pide ayuda al dueño.")
        org_id = current_user["organization_id"]
        screen = await db.screens.find_one({"id": screen_id, "organization_id": org_id})
        if not screen:
            raise HTTPException(404, "Screen not found")

        update: dict = {"updated_at": datetime.utcnow()}
        if "name" in data:
            name = (data.get("name") or "").strip()
            if not name:
                raise HTTPException(400, "Screen name is required")
            update["name"] = name
        orientation_changed = False
        if "orientation" in data:
            orientation = _norm_orientation(data.get("orientation"))
            specs = dict(screen.get("specs") or {})
            specs["orientation"] = orientation
            update["specs"] = specs
            # Legacy top-level value would keep shadowing the new one.
            orientation_changed = orientation != (screen.get("specs") or {}).get("orientation")

        await db.screens.update_one({"id": screen_id}, {"$set": update, "$unset": {"orientation": ""}})
        await _log(current_user, "screen.updated", "screen", screen_id,
                   {k: v for k, v in update.items() if k != "updated_at"})
        # The player reads the orientation from the playlist, so bump the version
        # to make the TV rotate on its next sync instead of waiting for a change.
        if orientation_changed and bump_playlist_version:
            await bump_playlist_version(screen_id, reason="screen orientation changed")

        fresh = await db.screens.find_one({"id": screen_id})
        return _ser(fresh)

    def _assert_owner(user: dict, detail: str) -> None:
        if get_effective_role(user) != Role.SELF_SERVICE_OWNER:
            raise HTTPException(403, detail)

    @router.post("/screens/connect", summary="Connect pending device to org using 6-char activation code")
    async def workspace_connect_screen(data: dict, current_user: dict = Depends(require_workspace_user)):
        """
        Customer enters the code shown on their TV/device + a name for the screen.
        Finds the pending device, creates a screen, and links them — atomically.
        """
        org_id = current_user["organization_id"]
        now = datetime.utcnow()

        activation_code = (data.get("activation_code") or "").strip().upper()
        screen_name = (data.get("screen_name") or "").strip()

        if len(activation_code) < 6:
            raise HTTPException(status_code=400, detail="Activation code must be 6 characters")
        if not screen_name:
            raise HTTPException(status_code=400, detail="Screen name is required")

        device = await db.devices.find_one({"activation_code": activation_code, "status": "pending"})
        if not device:
            raise HTTPException(
                status_code=404,
                detail="Code not found or already used. Make sure the code on screen is correct and the device hasn't been connected yet.",
            )

        # Check plan screen limit
        sub = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2}, sort=[("created_at", -1)]
        )
        current_pa = None
        if sub and sub.get("current_pricing_agreement_id"):
            current_pa = await db.pricing_agreements.find_one(
                {"id": sub["current_pricing_agreement_id"]}
            )
        plan_config = None
        if current_pa:
            plan_config = await db.plans.find_one({"plan_id": current_pa.get("plan_id")})

        current_count = await db.screens.count_documents({"organization_id": org_id})
        screens_limit = (current_pa or {}).get("screens_limit") or (plan_config or {}).get("screens_limit")
        if screens_limit and current_count >= screens_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Screen limit reached ({screens_limit}). Upgrade your plan or add screen capacity.",
            )

        # Create screen
        screen = {
            "id": str(_uuid.uuid4()),
            "name": screen_name,
            "organization_id": org_id,
            "status": "active",
            "code": activation_code,
            "active_menu_id": None,
            "specs": {"orientation": _norm_orientation(data.get("orientation"))},
            "created_by": current_user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await db.screens.insert_one(screen)

        # Activate device
        await db.devices.update_one(
            {"id": device["id"]},
            {"$set": {
                "screen_id": screen["id"],
                "status": "active",
                "device_name": screen_name,
                "activated_at": now,
            }},
        )

        return {
            "screen": _ser(screen),
            "device_id": device["id"],
            "message": f"Screen '{screen_name}' connected successfully!",
        }

    # ══════════════════════════════════════════════════════════════════════
    # MENU MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════

    @router.get("/menus", summary="List org menus")
    async def workspace_list_menus(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menus = await db.menus.find({"org_id": org_id}).sort("updated_at", -1).to_list(200)
        return _ser(menus)

    @router.post("/menus", summary="Create a menu", status_code=201)
    async def workspace_create_menu(data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        now = datetime.utcnow()

        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Menu name is required")

        items = []
        for item_in in (data.get("items") or []):
            items.append({
                "id": str(_uuid.uuid4()),
                "name": (item_in.get("name") or "Item").strip(),
                "price": float(item_in.get("price", 0)),
                "description": item_in.get("description"),
                "category": item_in.get("category"),
                "available": bool(item_in.get("available", True)),
                "media_id": item_in.get("media_id"),
                "image_url": item_in.get("image_url"),
            })

        menu = {
            "id": str(_uuid.uuid4()),
            "org_id": org_id,
            "name": name,
            "description": data.get("description"),
            "items": items,
            "categories": list({i["category"] for i in items if i.get("category")}),
            "status": "draft",
            "source": data.get("source", "blank"),
            "screen_ids": [],
            "created_by": current_user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await db.menus.insert_one(menu)
        return _ser(menu)

    @router.get("/menus/{menu_id}", summary="Get a single menu with items")
    async def workspace_get_menu(menu_id: str, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        return _ser(menu)

    @router.put("/menus/{menu_id}", summary="Update menu name/description")
    async def workspace_update_menu(menu_id: str, data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        now = datetime.utcnow()
        update: dict = {"updated_at": now}
        if "name" in data:
            update["name"] = (data["name"] or "").strip()
        if "description" in data:
            update["description"] = data["description"]
        await db.menus.update_one({"id": menu_id}, {"$set": update})
        return _ser({**menu, **update})

    @router.delete("/menus/{menu_id}", summary="Delete a menu")
    async def workspace_delete_menu(menu_id: str, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        await db.menus.delete_one({"id": menu_id})
        return {"message": "Menu deleted", "menu_id": menu_id}

    @router.post("/menus/{menu_id}/items", summary="Add item to menu", status_code=201)
    async def workspace_add_menu_item(menu_id: str, data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Item name is required")
        item = {
            "id": str(_uuid.uuid4()),
            "name": name,
            "price": float(data.get("price", 0)),
            "description": data.get("description"),
            "category": data.get("category"),
            "available": bool(data.get("available", True)),
            "media_id": data.get("media_id"),
            "image_url": data.get("image_url"),
        }
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id},
            {"$push": {"items": item}, "$set": {"updated_at": now}},
        )
        return _ser(item)

    @router.put("/menus/{menu_id}/items/{item_id}", summary="Update a menu item")
    async def workspace_update_menu_item(
        menu_id: str, item_id: str, data: dict, current_user: dict = Depends(require_workspace_user)
    ):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        now = datetime.utcnow()
        upd: dict = {"updated_at": now}
        for f in ["name", "price", "description", "category", "available", "media_id", "image_url"]:
            if f in data:
                upd[f"items.$.{f}"] = data[f]
        await db.menus.update_one(
            {"id": menu_id, "items.id": item_id},
            {"$set": upd},
        )
        return {"message": "Item updated", "item_id": item_id}

    @router.delete("/menus/{menu_id}/items/{item_id}", summary="Remove a menu item")
    async def workspace_delete_menu_item(
        menu_id: str, item_id: str, current_user: dict = Depends(require_workspace_user)
    ):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id},
            {"$pull": {"items": {"id": item_id}}, "$set": {"updated_at": now}},
        )
        return {"message": "Item removed", "item_id": item_id}

    @router.post("/menus/{menu_id}/publish", summary="Publish menu to screens")
    async def workspace_publish_menu(menu_id: str, data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        screen_ids = data.get("screen_ids") or []
        # Default: publish to all org screens
        if not screen_ids:
            org_screens = await db.screens.find({"organization_id": org_id}, {"id": 1}).to_list(100)
            screen_ids = [s["id"] for s in org_screens]
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id},
            {"$set": {"status": "published", "screen_ids": screen_ids, "published_at": now, "updated_at": now}},
        )
        if screen_ids:
            await db.screens.update_many(
                {"id": {"$in": screen_ids}, "organization_id": org_id},
                {"$set": {"active_menu_id": menu_id, "updated_at": now}},
            )
        return {
            "message": f"Menu '{menu['name']}' published to {len(screen_ids)} screen(s)",
            "menu_id": menu_id,
            "screen_ids": screen_ids,
        }

    # ══════════════════════════════════════════════════════════════════════
    # BILLING — add screens + cost preview
    # ══════════════════════════════════════════════════════════════════════

    @router.get("/billing/screen-cost", summary="Preview cost for adding more screens")
    async def workspace_screen_cost(additional_screens: int = 1, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        if additional_screens < 1:
            raise HTTPException(status_code=400, detail="Must specify at least 1 additional screen")
        sub = await db.subscriptions.find_one({"org_id": org_id, "schema_version": 2}, sort=[("created_at", -1)])
        if not sub:
            raise HTTPException(status_code=404, detail="No subscription found")
        pa = None
        if sub.get("current_pricing_agreement_id"):
            pa = await db.pricing_agreements.find_one({"id": sub["current_pricing_agreement_id"]})
        if not pa:
            raise HTTPException(status_code=400, detail="No pricing agreement found")
        plan_config = await db.plans.find_one({"plan_id": pa.get("plan_id")}) if pa.get("plan_id") else None
        current_count = await db.screens.count_documents({"organization_id": org_id})
        new_total = current_count + additional_screens
        extra_price = float(pa.get("overage_price_per_screen") or (plan_config or {}).get("price_per_extra_screen") or 0)
        base_price = float(pa.get("agreed_monthly_price") or 0)
        added_cost = extra_price * additional_screens
        new_monthly = base_price + added_cost
        screens_limit = pa.get("screens_limit") or (plan_config or {}).get("screens_limit")
        if screens_limit and new_total > screens_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Adding {additional_screens} screen(s) would exceed your plan limit ({screens_limit}).",
            )
        return {
            "current_screens": current_count,
            "additional_screens": additional_screens,
            "new_total_screens": new_total,
            "current_monthly": base_price,
            "added_cost": added_cost,
            "new_monthly": new_monthly,
            "extra_price_per_screen": extra_price,
            "screens_included": pa.get("screens_included", 0),
            "screens_limit": screens_limit,
            "currency": "USD",
        }

    @router.post("/billing/add-screens", summary="Add screens — creates new PricingAgreement version")
    async def workspace_add_screens(data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        additional_screens = int(data.get("additional_screens", 1))
        if additional_screens < 1:
            raise HTTPException(status_code=400, detail="Must add at least 1 screen")
        sub = await db.subscriptions.find_one({"org_id": org_id, "schema_version": 2}, sort=[("created_at", -1)])
        if not sub:
            raise HTTPException(status_code=404, detail="No active subscription found")
        pa = None
        if sub.get("current_pricing_agreement_id"):
            pa = await db.pricing_agreements.find_one({"id": sub["current_pricing_agreement_id"]})
        if not pa:
            raise HTTPException(status_code=400, detail="No pricing agreement found")
        plan_config = await db.plans.find_one({"plan_id": pa.get("plan_id")}) if pa.get("plan_id") else None
        screens_limit = pa.get("screens_limit") or (plan_config or {}).get("screens_limit")
        current_count = await db.screens.count_documents({"organization_id": org_id})
        if screens_limit and (current_count + additional_screens) > screens_limit:
            raise HTTPException(status_code=400, detail=f"Screen limit {screens_limit} would be exceeded")
        extra_price = float(pa.get("overage_price_per_screen") or (plan_config or {}).get("price_per_extra_screen") or 0)
        base_price = float(pa.get("agreed_monthly_price") or 0)
        added_cost = extra_price * additional_screens
        new_monthly = base_price + added_cost
        new_screens_included = (pa.get("screens_included") or 0) + additional_screens
        now = datetime.utcnow()
        # Create new PA version (preserves history)
        new_pa = {
            k: v for k, v in pa.items() if k != "_id"
        }
        new_pa.update({
            "id": str(_uuid.uuid4()),
            "version": (pa.get("version") or 1) + 1,
            "screens_included": new_screens_included,
            "agreed_monthly_price": new_monthly,
            "effective_from": now.isoformat(),
            "created_at": now,
            "notes": f"Added {additional_screens} screen(s). Was: {pa.get('screens_included')} screens @ ${base_price:.2f}/mo",
            "created_by": current_user.get("email", "workspace"),
        })
        await db.pricing_agreements.insert_one(new_pa)
        await db.subscriptions.update_one(
            {"id": sub["id"]},
            {"$set": {"current_pricing_agreement_id": new_pa["id"], "updated_at": now}},
        )
        return {
            "message": f"Added {additional_screens} screen(s). New monthly: ${new_monthly:.2f}",
            "added_screens": additional_screens,
            "new_monthly": new_monthly,
            "new_screens_included": new_screens_included,
            "pricing_agreement": _ser(new_pa),
        }

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC: Player content endpoint (device_id as auth token)
    # ══════════════════════════════════════════════════════════════════════

    @router.get("/player/{device_id}/content", summary="Player fetches its active content (public)")
    async def player_content(device_id: str):
        """No auth — device_id (UUID) acts as the access token. Returns pending code or active menu."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        if device.get("status") != "active" or not device.get("screen_id"):
            return {
                "status": "pending",
                "activation_code": device.get("activation_code"),
                "device_id": device_id,
                "message": "Enter this code in your MediaView workspace to activate this screen.",
            }
        screen = await db.screens.find_one({"id": device["screen_id"]})
        if not screen:
            return {"status": "no_screen", "device_id": device_id}
        menu = None
        if screen.get("active_menu_id"):
            menu = await db.menus.find_one({"id": screen["active_menu_id"]})
        if menu:
            return {"status": "menu", "screen": _ser(screen), "menu": _ser(menu)}
        return {"status": "no_content", "screen": _ser(screen), "device_id": device_id,
                "message": "Connected! Waiting for content to be published."}

    return router
