"""Pone en el mapa las pantallas que ya estaban cargadas sin coordenadas.

Las pantallas viejas se crearon antes de que el sistema buscara el pin solo.
Esto recorre las que tienen dirección y todavía no tienen punto en el mapa y se
lo busca. Respeta el límite de una consulta por segundo de Nominatim, así que
con muchas pantallas tarda: se puede volver a correr, es idempotente.

    cd /app/backend && python scripts/backfill_screen_coords.py            # todas
    cd /app/backend && python scripts/backfill_screen_coords.py --public   # solo publicas
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from geocoding import address_key, geocode_location  # noqa: E402


async def main(only_public: bool) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    query = {"status": "active",
             "$or": [{"location.lat": None}, {"location.lat": {"$exists": False}}]}
    if only_public:
        query["operation_type"] = "PUBLIC_ADVERTISING"
    screens = await db.screens.find(query).to_list(500)
    print(f"{len(screens)} pantallas sin ubicación en el mapa")

    found = 0
    for screen in screens:
        location = screen.get("location") or {}
        if not address_key(location):
            print(f"  · {screen.get('name')}: sin dirección cargada")
            continue
        result = await geocode_location(db, location)
        if not result:
            print(f"  ✗ {screen.get('name')}: no se pudo ubicar «{address_key(location)}»")
            continue
        await db.screens.update_one({"id": screen["id"]}, {"$set": {
            "location.lat": result["lat"], "location.lng": result["lng"],
            "location.geocoded_from": address_key(location),
            "location.geocoded_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }})
        found += 1
        print(f"  ✓ {screen.get('name')}: {result['lat']:.4f}, {result['lng']:.4f}")
    print(f"{found} pantallas ubicadas")


if __name__ == "__main__":
    asyncio.run(main("--public" in sys.argv))
