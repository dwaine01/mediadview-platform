"""
Localises the public plan feature bullets to Spanish so /pricing reads
consistently with the rest of the customer-facing UI.

Idempotent — safe to re-run.  Run:  python scripts/localize_plans_es.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PLANS = {
    "free": {
        "highlight_text": "",
        "features": [
            "1 pantalla",
            "Programación básica",
            "1 GB de almacenamiento",
            "Reproductor web",
            "Soporte de la comunidad",
        ],
    },
    "starter": {
        "highlight_text": "",
        "features": [
            "3 pantallas",
            "Playlists y programación",
            "10 GB de almacenamiento",
            "Reproductor web y Android",
            "Hasta 2 miembros del equipo",
            "Soporte por correo",
        ],
    },
    "pro": {
        "highlight_text": "Más Popular",
        "features": [
            "10 pantallas",
            "Playlists y programación",
            "50 GB de almacenamiento",
            "Todos los reproductores",
            "Widgets e integraciones",
            "Hasta 10 miembros del equipo",
            "Panel de analítica",
            "Soporte prioritario",
        ],
    },
    "enterprise": {
        "highlight_text": "",
        "features": [
            "50+ pantallas (add-ons ilimitados)",
            "Playlists y programación ilimitadas",
            "500 GB de almacenamiento",
            "Todos los reproductores + acceso API",
            "Marca personalizada",
            "Miembros del equipo ilimitados",
            "Analítica avanzada",
            "Ejecutivo de cuenta dedicado",
            "Garantía de SLA",
        ],
    },
}


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "mediaview")]
    for plan_id, patch in PLANS.items():
        res = await db.plans.update_one({"plan_id": plan_id}, {"$set": patch})
        print(f"{plan_id}: matched={res.matched_count} modified={res.modified_count}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
