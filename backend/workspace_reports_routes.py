"""
workspace_reports_routes.py — "Reporte Semanal" dentro del panel del cliente:
qué se mostró, qué cambió y qué pantallas estuvieron caídas durante la semana.

Se calcula con datos reales: `play_logs` (lo que reprodujeron los reproductores),
`audit_logs` (cambios del equipo) y el último heartbeat de cada dispositivo.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from rbac import Role, get_effective_role

WORKSPACE_ROLES = (Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER, Role.SELF_SERVICE_STAFF)

CHANGE_LABELS = {
    "menu_item.updated": "Cambios en productos",
    "menu_item.sold_out": "Productos agotados",
    "menu_item.restored": "Productos reactivados",
    "menu_item.added": "Productos nuevos",
    "menu_item.deleted": "Productos eliminados",
    "menu_item.ai_photo": "Fotos generadas con IA",
    "menu.published": "Menús publicados",
    "media.uploaded": "Contenido subido",
    "playlist.published": "Playlists publicadas",
    "promo.launched": "Promos lanzadas",
    "screen.connected": "Pantallas conectadas",
    "team.member_created": "Personas agregadas al equipo",
}


def _week_bounds(offset: int) -> tuple[datetime, datetime]:
    """Monday 00:00 UTC → next Monday, `offset` weeks back (0 = current week)."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=max(0, offset))
    return monday, monday + timedelta(days=7)


def create_workspace_reports_routes(db, get_current_user):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Reportes"])

    async def require_workspace_user(current_user: dict = Depends(get_current_user)):
        if get_effective_role(current_user) not in WORKSPACE_ROLES:
            raise HTTPException(403, "Tu cuenta no tiene acceso al panel del negocio.")
        if not current_user.get("organization_id"):
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        if current_user.get("must_change_password"):
            raise HTTPException(428, "Debes crear tu propia contraseña antes de continuar.")
        return current_user

    @router.get("/reports/weekly", summary="Weekly summary: what played, what changed, what went down")
    async def weekly_report(weeks_ago: int = 0, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        start, end = _week_bounds(weeks_ago)
        now = datetime.utcnow()

        screens = await db.screens.find({"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1}).to_list(300)
        screen_ids = [s["id"] for s in screens]
        screen_names = {s["id"]: s.get("name") or "Pantalla" for s in screens}

        # ── Lo que se reprodujo ──
        plays = await db.play_logs.find(
            {"screen_id": {"$in": screen_ids}, "played_at": {"$gte": start, "$lt": end}},
            {"_id": 0, "media_id": 1, "screen_id": 1, "duration": 1, "played_at": 1},
        ).to_list(20_000)

        by_content: dict[str, dict] = {}
        by_screen: dict[str, dict] = {sid: {"plays": 0, "seconds": 0, "days": set()} for sid in screen_ids}
        for play in plays:
            ref = str(play.get("media_id") or "desconocido")
            seconds = int(play.get("duration") or 0)
            entry = by_content.setdefault(ref, {"plays": 0, "seconds": 0})
            entry["plays"] += 1
            entry["seconds"] += seconds
            screen_entry = by_screen.get(play.get("screen_id"))
            if screen_entry is not None:
                screen_entry["plays"] += 1
                screen_entry["seconds"] += seconds
                played_at = play.get("played_at")
                if isinstance(played_at, datetime):
                    screen_entry["days"].add(played_at.date().isoformat())

        media_ids = [ref for ref in by_content if not ref.startswith("menu:")]
        menu_ids = [ref.split(":", 1)[1] for ref in by_content if ref.startswith("menu:")]
        media_docs = await db.media.find({"id": {"$in": media_ids}}, {"_id": 0, "id": 1, "filename": 1}).to_list(500)
        menu_docs = await db.menus.find({"id": {"$in": menu_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        titles = {m["id"]: m.get("filename") or "Contenido" for m in media_docs}
        titles.update({f"menu:{m['id']}": m.get("name") or "Menú" for m in menu_docs})

        top_content = sorted(
            (
                {"title": titles.get(ref, "Contenido eliminado"),
                 "kind": "menu" if ref.startswith("menu:") else "media",
                 "plays": v["plays"], "minutes": round(v["seconds"] / 60, 1)}
                for ref, v in by_content.items()
            ),
            key=lambda row: row["plays"], reverse=True,
        )[:8]

        # ── Cambios del equipo ──
        events = await db.audit_logs.find(
            {"org_id": org_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0},
        ).sort("created_at", -1).to_list(2000)

        change_counts: dict[str, int] = {}
        by_person: dict[str, int] = {}
        price_changes = []
        for event in events:
            action = event.get("action", "")
            if action in CHANGE_LABELS:
                change_counts[action] = change_counts.get(action, 0) + 1
            who = event.get("user_email") or "desconocido"
            by_person[who] = by_person.get(who, 0) + 1
            details = event.get("details") or {}
            if action == "menu_item.updated" and "price_to" in details:
                price_changes.append({
                    "item": details.get("item"),
                    "from": details.get("price_from"),
                    "to": details.get("price_to"),
                    "who": who,
                    "at": event["created_at"].isoformat() if isinstance(event.get("created_at"), datetime) else None,
                })

        # ── Pantallas caídas ──
        devices = await db.devices.find(
            {"screen_id": {"$in": screen_ids}}, {"_id": 0, "screen_id": 1, "last_heartbeat": 1},
        ).to_list(500)
        last_beat: dict[str, datetime] = {}
        for device in devices:
            beat = device.get("last_heartbeat")
            if beat and (device["screen_id"] not in last_beat or beat > last_beat[device["screen_id"]]):
                last_beat[device["screen_id"]] = beat

        days_in_period = max(1, min(7, (min(end, now) - start).days + 1))
        screen_rows = []
        for sid in screen_ids:
            stats = by_screen[sid]
            beat = last_beat.get(sid)
            offline_seconds = int((now - beat).total_seconds()) if beat else None
            screen_rows.append({
                "screen_id": sid,
                "screen_name": screen_names[sid],
                "plays": stats["plays"],
                "minutes": round(stats["seconds"] / 60, 1),
                "active_days": len(stats["days"]),
                "silent_days": max(0, days_in_period - len(stats["days"])),
                "is_online": bool(offline_seconds is not None and offline_seconds < 120),
                "last_seen_seconds": offline_seconds,
                "never_connected": beat is None,
            })
        screen_rows.sort(key=lambda row: (row["is_online"], row["plays"]))

        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "label": f"{start.strftime('%d/%m')} – {(end - timedelta(days=1)).strftime('%d/%m/%Y')}",
                "is_current_week": weeks_ago == 0,
                "days_counted": days_in_period,
            },
            "totals": {
                "plays": len(plays),
                "minutes_on_air": round(sum(v["seconds"] for v in by_content.values()) / 60, 1),
                "screens": len(screen_ids),
                "screens_offline": sum(1 for row in screen_rows if not row["is_online"]),
                "changes": sum(change_counts.values()),
            },
            "top_content": top_content,
            "changes": [
                {"action": action, "label": CHANGE_LABELS[action], "count": count}
                for action, count in sorted(change_counts.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "price_changes": price_changes[:12],
            "team": [
                {"user_email": email, "actions": count}
                for email, count in sorted(by_person.items(), key=lambda kv: kv[1], reverse=True)[:8]
            ],
            "screens": screen_rows,
        }

    return router
