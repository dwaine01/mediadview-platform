"""Recompone las dos ofertas flash que tenían el precio encima del título.

El disco del precio se apoya en la foto redonda; con un precio de 96 px o más
el disco se sale del círculo y tapa el nombre del producto. En una oferta el
precio es enorme por definición, así que estas dos plantillas dejan la foto en
el fondo (`backdrop`) y llevan el precio dentro de la columna de texto.

    cd /app/backend && python scripts/fix_offer_layouts.py
"""
import json
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed_templates" / "offers.json"

# Cine: la foto ocupa la mitad derecha y se disuelve hacia el texto.
CINE = [
    {"type": "backdrop", "rect": [880, 0, 1040, 1080], "binds": "categories[0]",
     "fade": "left", "ken": True, "rotate": 45},
    {"type": "brand", "rect": [88, 84, 720, 92], "size": 58},
    {"type": "text", "rect": [88, 194, 720, 34], "field": "tagline",
     "size": 24, "upper": True, "accent": True},
    {"type": "feature", "rect": [88, 296, 760, 480], "binds": "categories[0]",
     "photo": False, "name_size": 112, "price_size": 116, "desc_size": 30,
     "rotate": 45, "anim": "pop"},
    {"type": "promo", "rect": [88, 830, 760, 194], "size": 42},
    {"type": "ticker", "rect": [980, 936, 860, 88], "size": 30},
]

# Precio gigante: el número va primero, antes del nombre, y se lee de la calle.
PRECIO = [
    {"type": "backdrop", "rect": [940, 0, 980, 1080], "binds": "categories[0]",
     "fade": "left", "ken": True, "rotate": 45},
    {"type": "brand", "rect": [72, 62, 760, 92], "size": 58},
    {"type": "text", "rect": [72, 172, 760, 34], "field": "tagline",
     "size": 24, "upper": True, "accent": True},
    {"type": "feature", "rect": [72, 264, 820, 520], "binds": "categories[0]",
     "photo": False, "price_style": "lead", "name_size": 84, "price_size": 240,
     "desc_size": 28, "rotate": 45, "anim": "pop"},
    {"type": "promo", "rect": [72, 836, 820, 188], "size": 42},
    {"type": "ticker", "rect": [960, 940, 880, 84], "size": 30},
]

# Tótem: la foto arriba disolviéndose hacia abajo y el texto en el zócalo.
TOTEM = [
    {"type": "backdrop", "rect": [0, 0, 1080, 1200], "binds": "categories[0]",
     "fade": "bottom", "ken": True, "rotate": 45},
    {"type": "brand", "rect": [48, 952, 984, 88], "size": 54},
    {"type": "feature", "rect": [48, 1120, 984, 520], "binds": "categories[0]",
     "photo": False, "name_size": 112, "price_size": 150, "desc_size": 32,
     "rotate": 45, "anim": "pop"},
    {"type": "promo", "rect": [48, 1688, 984, 184], "size": 46},
]

BLOCKS = {"offers-flash-cine": CINE, "offers-flash-precio": PRECIO,
          "offers-flash-totem": TOTEM}

templates = json.loads(SEED.read_text())
for template in templates:
    if template["id"] in BLOCKS:
        template["blocks"] = BLOCKS[template["id"]]
        print(f"  ~ {template['id']}: {len(template['blocks'])} bloques")
SEED.write_text(json.dumps(templates, ensure_ascii=False, indent=2) + "\n")
