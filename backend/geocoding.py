"""De la dirección al pin del mapa, sin pedirle coordenadas a nadie.

Nadie que instala una pantalla sabe su latitud. Sabe la calle, la ciudad y el
código postal. Esto convierte eso en un punto del mapa usando Nominatim (el
buscador de OpenStreetMap): gratis, sin llave de API y con la misma base de
datos que dibuja los mapas del marketplace.

Reglas de uso de Nominatim que se respetan acá:
- un `User-Agent` que identifique la aplicación,
- como máximo una consulta por segundo,
- resultados en caché para no volver a preguntar lo mismo.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

log = logging.getLogger("mediaview.geocoding")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "MediaView-DigitalSignage/1.0 (soporte@mediaview.com)"
_throttle = asyncio.Lock()
_last_call = 0.0


def address_key(location: dict) -> str:
    """La dirección normalizada: sirve de clave de caché y de consulta."""
    parts = [location.get("address"), location.get("postal_code"),
             location.get("city"), location.get("state"), location.get("country")]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


async def _ask_nominatim(query: str, postal_code: Optional[str],
                         country: Optional[str]) -> tuple[str, Optional[dict]]:
    """Devuelve ("ok", coords|None) o ("error", None).

    La diferencia importa: «esa dirección no existe» se puede recordar, pero
    «Nominatim no contestó» hay que volver a intentarlo en el próximo guardado.
    Cachear un error como si fuera un no-existe deja la pantalla sin pin para
    siempre."""
    global _last_call
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 0}
    if country and len(str(country)) <= 3:
        params["countrycodes"] = str(country).lower()
    async with _throttle:                      # una consulta por segundo
        wait = 1.0 - (asyncio.get_event_loop().time() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = asyncio.get_event_loop().time()
        try:
            async with httpx.AsyncClient(timeout=10,
                                         headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(NOMINATIM, params=params)
        except Exception as exc:
            log.warning("geocoding: no se pudo consultar Nominatim: %r", exc)
            return "error", None
    if response.status_code != 200:
        log.warning("geocoding: Nominatim respondió %s", response.status_code)
        return "error", None
    results = response.json()
    if not results:
        # Sin resultado exacto: el código postal solo suele alcanzar para
        # poner el pin en el barrio correcto, que es mejor que ningún pin.
        if postal_code:
            fallback = f"{postal_code}, {country or ''}".strip(", ")
            if fallback.lower() != query.lower():
                return await _ask_nominatim(fallback, None, country)
        return "ok", None
    first = results[0]
    return "ok", {"lat": float(first["lat"]), "lng": float(first["lon"]),
                  "display_name": first.get("display_name")}


async def geocode_location(db, location: dict) -> Optional[dict]:
    """Coordenadas de una dirección. Devuelve None si no se pudo ubicar.

    El fallo no es un error del usuario: la pantalla se guarda igual y queda
    en el listado, sólo no aparece en el mapa hasta que se corrija la
    dirección o se carguen las coordenadas a mano."""
    query = address_key(location)
    if not query:
        return None
    cached = await db.geocode_cache.find_one({"_id": query.lower()})
    if cached:
        return None if cached.get("miss") else {
            "lat": cached["lat"], "lng": cached["lng"],
            "display_name": cached.get("display_name"), "cached": True,
        }
    status, found = await _ask_nominatim(query, location.get("postal_code"),
                                         location.get("country"))
    if status == "error":
        # Un tropiezo de red no puede costarle el pin a la pantalla: un
        # segundo intento y, si tampoco, se reintenta en el próximo guardado.
        await asyncio.sleep(1.2)
        status, found = await _ask_nominatim(query, location.get("postal_code"),
                                             location.get("country"))
    if status == "error":
        return None
    await db.geocode_cache.update_one(
        {"_id": query.lower()},
        {"$set": {**(found or {"miss": True}), "query": query,
                  "updated_at": datetime.utcnow()}},
        upsert=True)
    return found
