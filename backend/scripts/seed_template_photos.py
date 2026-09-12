"""Genera las fotos genéricas de producto del catálogo de plantillas.

Sin fotos buenas una plantilla no se ve de agencia y el cliente no entiende qué
va en cada hueco. Estas son fotos de MediaView, iguales para todos, y el cliente
las reemplaza por las suyas al llenar la plantilla.

Se corre a mano y el resultado se versiona en el repo: el catálogo no puede
depender de que haya saldo de IA en cada despliegue.

    cd /app/backend && python scripts/seed_template_photos.py pizzeria
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(__file__).resolve().parents[1] / "static" / "template-samples"

# Un único "set fotográfico" para todo el rubro: mismo ángulo, misma luz, mismo
# fondo y sin utilería. Es lo que hace que doce fotos generadas por separado se
# vean como una sola sesión de fotos y la cartelera no parezca un collage.
STYLE = ("professional food photography for a digital menu board, camera at a fixed "
         "45 degree angle, single soft warm key light from the upper left with a subtle "
         "fill, dark charred wood surface background, identical framing and identical "
         "lighting across the whole series, subject centered and filling the frame, "
         "shallow depth of field, rich warm tones, appetizing, no props, no cutlery, "
         "no napkins, no hands, no people, no text, no watermark, square crop")

PROMPTS = {
    "pizzeria": {
        "pepperoni": "a whole pepperoni pizza, crispy cupped pepperoni, bubbling mozzarella, wood fired crust",
        "margherita": "a whole margherita pizza with san marzano tomato, fresh mozzarella and basil leaves",
        "meatlovers": "a whole meat lovers pizza loaded with pepperoni, italian sausage, ham and bacon",
        "quattro": "a whole four cheese pizza, molten cheese pull, golden blistered crust",
        "veggie": "a whole vegetable pizza with roasted peppers, mushrooms, red onion and black olives",
        "prosciutto": "a whole pizza topped with prosciutto, fresh arugula and shaved parmesan",
        "combo_lunch": "a personal pizza with a soft drink, lunch combo on a wooden board",
        "combo_family": "two large pizzas with a two liter soda bottle, family combo",
        "combo_duo": "two medium pizzas with a basket of french fries",
        "combo_kids": "a small kids pizza with apple slices and a juice box",
        "combo_calzone": "a golden baked calzone cut open with melted cheese, next to a drink",
        "coke": "a cold glass bottle of cola with condensation and ice",
        "sprite": "a cold glass bottle of clear lemon lime soda with condensation",
        "water": "a bottle of sparkling mineral water with condensation",
        "lemonade": "a tall glass of fresh homemade lemonade with mint and ice",
    },
}


async def generate(industry: str) -> None:
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise SystemExit("EMERGENT_LLM_KEY no está configurada")
    prompts = PROMPTS.get(industry)
    if not prompts:
        raise SystemExit(f"No hay prompts para el rubro «{industry}»")

    folder = OUT / industry
    folder.mkdir(parents=True, exist_ok=True)
    for key_name, subject in prompts.items():
        target = folder / f"{key_name}.jpg"
        if target.exists():
            print(f"  = {target.name} (ya existe)")
            continue
        from menu_ai_routes import IMAGE_MODEL
        chat = LlmChat(
            api_key=key, session_id=f"tpl-photo-{industry}-{key_name}",
            system_message="Generas fotografías de comida para menús digitales.",
        ).with_model("gemini", IMAGE_MODEL).with_params(modalities=["image", "text"])
        try:
            _text, images = await chat.send_message_multimodal_response(
                UserMessage(text=f"{subject}. {STYLE}"))
        except Exception as exc:
            print(f"  ! {key_name}: {exc}")
            continue
        if not images:
            print(f"  ! {key_name}: sin imagen")
            continue
        target.write_bytes(base64.b64decode(images[0]["data"]))
        print(f"  + {target.name} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(generate(sys.argv[1] if len(sys.argv) > 1 else "pizzeria"))
