"""
Seeds a realistic demo workspace: a pizzeria owner on the Starter plan with 3 screens
and a published pizza menu. Used to review the customer panel end to end.

Everything goes through the real public/workspace APIs — no direct DB writes except
the device heartbeat (which normally comes from a physical player).

Idempotent: re-running resets the demo org's screens and menus.

Run:  python scripts/seed_demo_pizzeria.py
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE = "http://localhost:8001"
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"
BUSINESS = "Pizzería Don Luis"

SCREENS = [
    {"name": "Mostrador", "location": "Sobre la caja", "orientation": "landscape"},
    {"name": "Sala", "location": "Pared del comedor", "orientation": "landscape"},
    {"name": "Vitrina", "location": "Ventana a la calle", "orientation": "portrait"},
]

MENU_ITEMS = [
    {"name": "Margherita", "price": 12.99, "category": "Pizzas", "description": "Tomate, mozzarella fresca y albahaca"},
    {"name": "Pepperoni", "price": 14.49, "category": "Pizzas", "description": "Doble pepperoni y mozzarella"},
    {"name": "Cuatro Quesos", "price": 15.99, "category": "Pizzas", "description": "Mozzarella, provolone, gorgonzola y parmesano"},
    {"name": "Prosciutto", "price": 16.50, "category": "Pizzas", "description": "Jamón serrano, rúcula y parmesano"},
    {"name": "Vegetariana", "price": 13.99, "category": "Pizzas", "description": "Pimiento, cebolla, champiñón y aceituna"},
    {"name": "BBQ Pollo", "price": 15.49, "category": "Pizzas", "description": "Pollo, salsa BBQ y cebolla morada"},
    {"name": "Ajo con Queso", "price": 6.50, "category": "Entradas", "description": "Pan de ajo horneado con mozzarella"},
    {"name": "Refresco", "price": 2.50, "category": "Bebidas", "description": "Lata 355 ml"},
]


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "mediaview")]

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as http:
        # ── account (create once, then just log in) ────────────────────────
        r = await http.post("/api/auth/customer-signup", json={
            "plan_id": "starter",
            "billing_cycle": "monthly",
            "business_name": BUSINESS,
            "contact_name": "Luis Ramírez",
            "contact_email": EMAIL,
            "password": PASSWORD,
            "phone": "+1 787 555 0134",
        })
        if r.status_code in (200, 201):
            token = r.json()["access_token"]
            print("signup: created")
        else:
            r = await http.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
            r.raise_for_status()
            token = r.json()["access_token"]
            print("signup: already existed — logged in")

        auth = {"Authorization": f"Bearer {token}"}

        ctx = (await http.get("/api/workspace/context", headers=auth)).json()
        org_id = ctx["organization"]["id"]

        # ── reset the demo content so re-runs stay clean ───────────────────
        await db.screens.delete_many({"organization_id": org_id})
        await db.menus.delete_many({"org_id": org_id})

        # ── 3 screens ──────────────────────────────────────────────────────
        screen_ids = []
        for spec in SCREENS:
            res = await http.post("/api/workspace/screens", json=spec, headers=auth)
            res.raise_for_status()
            screen_ids.append(res.json()["id"])
            print(f"screen: {spec['name']}")

        # ── pizza menu ─────────────────────────────────────────────────────
        res = await http.post("/api/workspace/menus", json={
            "name": "Menú Principal",
            "template": "pizza",
            "items": MENU_ITEMS,
        }, headers=auth)
        res.raise_for_status()
        menu_id = res.json()["id"]
        print(f"menu: Menú Principal ({len(MENU_ITEMS)} productos)")

        # ── publish to the two landscape screens ───────────────────────────
        res = await http.post(f"/api/workspace/menus/{menu_id}/publish",
                              json={"screen_ids": screen_ids[:2]}, headers=auth)
        print("publish:", res.status_code, res.json() if res.status_code < 400 else res.text[:120])

        # ── two players "online" (a real device sends this heartbeat) ──────
        now = datetime.utcnow()
        for i, sid in enumerate(screen_ids[:2]):
            await db.devices.update_one(
                {"screen_id": sid},
                {"$set": {
                    "screen_id": sid,
                    "name": SCREENS[i]["name"],
                    "status": "active",
                    "last_heartbeat": now,
                    "updated_at": now,
                }},
                upsert=True,
            )
            await db.screens.update_one({"id": sid}, {"$set": {"status": "active"}})
        print("devices: 2 online, 1 offline")

    client.close()
    print(f"\nDemo listo — entra en /account/login con {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
