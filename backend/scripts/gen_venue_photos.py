"""Fotos de las pantallas instaladas en el local, para la ficha del anunciante.

El anunciante no compra una «pantalla»: compra estar en la pared de ese negocio.
Sin la foto de la pantalla montada en el local, la ficha es un formulario y nadie
paga a ciegas. Estas fotos son de MediaView (demo del catálogo) y se guardan en
el repo, no dependen de que haya saldo de IA en cada despliegue.

    cd /app/backend && python scripts/gen_venue_photos.py
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(__file__).resolve().parents[1] / "static" / "venue-photos"

# Un solo set: la misma cámara, la misma luz, el mismo encuadre. La pantalla
# siempre se ve montada Y se ve el local alrededor, que es lo que el anunciante
# quiere evaluar.
STYLE = ("realistic interior photography of the place, wide angle from customer "
         "eye level, natural daylight mixed with store lighting, a large wall "
         "mounted flat digital screen clearly visible and switched on showing a "
         "colourful generic promotional layout, people blurred in motion in the "
         "background, sharp on the screen and its surroundings, no text legible, "
         "no logos, no watermark, 16:9 crop")

VENUES = {
    "supermercado": "inside a busy neighbourhood supermarket, near the checkout lanes",
    "farmacia": "inside a clean modern pharmacy, near the service counter",
    "gimnasio": "inside a gym, screen on the wall in front of the cardio machines",
    "restaurante": "inside a casual restaurant dining room, screen on the brick wall",
    "gomeria": "inside a tire shop waiting area, screen on the wall above the counter",
}


async def generate(force: bool = False) -> None:
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise SystemExit("EMERGENT_LLM_KEY no está configurada")
    OUT.mkdir(parents=True, exist_ok=True)
    from menu_ai_routes import IMAGE_MODEL
    for name, subject in VENUES.items():
        target = OUT / f"{name}.jpg"
        if target.exists() and not force:
            print(f"  = {target.name} (ya existe)")
            continue
        chat = LlmChat(
            api_key=key, session_id=f"venue-photo-{name}",
            system_message="Generas fotografías de locales con carteleras digitales instaladas.",
        ).with_model("gemini", IMAGE_MODEL).with_params(modalities=["image", "text"])
        try:
            _text, images = await chat.send_message_multimodal_response(
                UserMessage(text=f"{subject}. {STYLE}"))
        except Exception as exc:
            print(f"  ! {name}: {exc}")
            continue
        if not images:
            print(f"  ! {name}: sin imagen")
            continue
        target.write_bytes(base64.b64decode(images[0]["data"]))
        print(f"  + {target.name} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(generate(force="--force" in sys.argv))
