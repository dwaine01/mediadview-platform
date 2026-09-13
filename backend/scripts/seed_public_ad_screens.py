"""Cuatro pantallas públicas de demostración con su ficha comercial completa.

Sin esto el catálogo del anunciante es una lista de nombres de prueba
(«TEST_B PUBLIC_ADVERTISING Screen») y no se puede juzgar la experiencia que
vive quien escanea el QR. Acá quedan cuatro locales reales con foto de la
pantalla instalada, referencia de cómo llegar y tráfico estimado.

Idempotente: se puede correr todas las veces que haga falta.

    cd /app/backend && python scripts/seed_public_ad_screens.py
"""
import asyncio
import base64
import io
import os
import random
import string
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

PHOTOS = ROOT / "static" / "venue-photos"

VENUES = [
    {
        "name": "Supermercado La Colonia — Caja central",
        "photo": "supermercado.jpg",
        "establishment_name": "Supermercado La Colonia",
        "location_reference": "Frente al parque central, entrando por la calle peatonal",
        "audience_min": 800, "audience_max": 1200,
        "audience_note": "Mayor tráfico de 5 a 8 pm y los sábados todo el día",
        "location": {"city": "Tegucigalpa", "state": "Francisco Morazán",
                     "address": "Av. Cervantes, Barrio La Plazuela", "country": "HN"},
        "description": "Pantalla de 55\" sobre las cajas: todos los clientes la ven mientras esperan para pagar.",
        "prices": (120, 400, 4000),
    },
    {
        "name": "Farmacia San Rafael — Mostrador",
        "photo": "farmacia.jpg",
        "establishment_name": "Farmacia San Rafael",
        "location_reference": "A media cuadra del Hospital Mario Rivas, sobre la 3ª avenida",
        "audience_min": 400, "audience_max": 600,
        "audience_note": "Público familiar, pico de 8 a 11 am",
        "location": {"city": "San Pedro Sula", "state": "Cortés",
                     "address": "3ª Avenida, Barrio Guamilito", "country": "HN"},
        "description": "Pantalla frente al mostrador de atención, a la altura de la vista.",
        "prices": (90, 300, 3000),
    },
    {
        "name": "Gimnasio Fuerza Fit — Zona de cardio",
        "photo": "gimnasio.jpg",
        "establishment_name": "Gimnasio Fuerza Fit",
        "location_reference": "Dentro del Mall Multiplaza, nivel 2, al lado de la escalera",
        "audience_min": 300, "audience_max": 500,
        "audience_note": "Socios de 18 a 45 años, pico de 6 a 9 pm",
        "location": {"city": "Tegucigalpa", "state": "Francisco Morazán",
                     "address": "Mall Multiplaza, nivel 2", "country": "HN"},
        "description": "Pantalla frente a las máquinas de cardio: el anuncio se ve durante 30 o 40 minutos seguidos.",
        "prices": (100, 350, 3500),
    },
    {
        "name": "Llantera El Camino — Sala de espera",
        "photo": "gomeria.jpg",
        "establishment_name": "Llantera El Camino",
        "location_reference": "Salida a Olancho, km 12, antes del puente",
        "audience_min": 180, "audience_max": 260,
        "audience_note": "Clientes esperando montaje, 20 a 40 minutos por visita",
        "location": {"city": "Tegucigalpa", "state": "Francisco Morazán",
                     "address": "Carretera a Olancho km 12", "country": "HN"},
        "description": "Pantalla en la sala de espera del taller: audiencia cautiva mientras atienden su vehículo.",
        "prices": (70, 240, 2400),
    },
]

# Nombres que dejaron las pruebas automatizadas. No se borran (los tests los
# usan), se sacan del catálogo público con el mismo interruptor del panel.
TEST_PREFIXES = ("TEST_B", "TEST_H", "TEST_", "RBAC Test Screen", "MgrScreen-",
                 "CHAIN ", "DISKLESS ", "ORIENT TEST", "VIDEO ", "ITER36 ", "DBG ",
                 "Test Screen", "Screen Test")


def photo_data_url(filename: str) -> str | None:
    """Foto reducida a 1280 px: en Mongo va el base64, no un archivo de 900 KB."""
    path = PHOTOS / filename
    if not path.exists():
        return None
    image = Image.open(path).convert("RGB")
    if image.width > 1280:
        image = image.resize((1280, round(image.height * 1280 / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def ad_code() -> str:
    return "MV-ADV-" + "".join(random.choice(string.ascii_uppercase + string.digits)
                               for _ in range(6))


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    for venue in VENUES:
        existing = await db.screens.find_one({"name": venue["name"]})
        advertising = {
            "is_public": True,
            "price_per_ad_per_month": venue["prices"][1],
            "establishment_name": venue["establishment_name"],
            "location_reference": venue["location_reference"],
            "audience_min": venue["audience_min"],
            "audience_max": venue["audience_max"],
            "audience_note": venue["audience_note"],
        }
        photo = photo_data_url(venue["photo"])
        if photo:
            advertising["photo_base64"] = photo
        week, month, year = venue["prices"]
        doc = {
            "name": venue["name"],
            "description": venue["description"],
            "location": venue["location"],
            "specs": {"size": "55\"", "type": "LED", "resolution": "1920x1080",
                      "orientation": "landscape"},
            "status": "active",
            "operation_type": "PUBLIC_ADVERTISING",
            "max_ad_slots": 4,
            "advertising_pricing": {"price_per_week": week, "price_per_month": month,
                                    "price_per_year": year},
            "pricing": {"per_month": month, "per_day": round(month / 30, 2),
                        "per_hour": round(month / 30 / 14, 2), "per_slot": 5.0,
                        "currency": "USD"},
            "advertising": advertising,
            "active": True,
            "updated_at": datetime.utcnow(),
        }
        if existing:
            await db.screens.update_one({"id": existing["id"]}, {"$set": doc})
            print(f"  ~ {venue['name']} ({existing.get('public_screen_code')})")
        else:
            import uuid
            code = ad_code()
            while await db.screens.find_one({"public_screen_code": code}):
                code = ad_code()
            doc.update({"id": str(uuid.uuid4()), "public_screen_code": code,
                        "created_at": datetime.utcnow()})
            await db.screens.insert_one(doc)
            print(f"  + {venue['name']} ({code})")

    hidden = 0
    for prefix in TEST_PREFIXES:
        result = await db.screens.update_many(
            {"name": {"$regex": f"^{prefix}"}, "operation_type": "PUBLIC_ADVERTISING"},
            {"$set": {"advertising.is_public": False}})
        hidden += result.modified_count
    print(f"  − {hidden} pantallas de prueba fuera del catálogo público")


if __name__ == "__main__":
    asyncio.run(main())
