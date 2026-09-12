"""Reordena la muestra de farmacia para que ninguna foto redonda quede vacía.

El set fotográfico del rubro tiene cinco fotos (vitaminas, mascarillas, alcohol,
curitas, analgésico). La grilla de «Promociones» mostraba tensiómetro, pañales y
jarabe, que no tienen foto, y salían tres círculos en blanco. Los productos con
foto van a la grilla; los que se leen igual de bien en una lista, a las listas.

    cd /app/backend && python scripts/fix_pharmacy_sample.py
"""
import json
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed_templates" / "pharmacy.json"

CATEGORIES = [
    {"name": "Promociones", "products": [
        {"key": "vitaminas", "name": "Vitaminas y suplementos",
         "description": "Llevando dos, 30% en la segunda.", "price": 14.9, "badge": "Promo"},
        {"key": "mascarillas", "name": "Mascarillas x50",
         "description": "Caja de cincuenta unidades.", "price": 6.9},
        {"key": "alcohol", "name": "Alcohol 70%",
         "description": "Botella de un litro.", "price": 2.5},
        {"key": "curitas", "name": "Curitas surtidas",
         "description": "Tres medidas en la misma caja.", "price": 3.2},
    ]},
    {"name": "Cuidado diario", "products": [
        {"key": "presion", "name": "Tensiómetro digital", "price": 39.9},
        {"key": "panales", "name": "Pañales, paquete grande", "price": 18.5},
        {"key": "jarabe", "name": "Jarabe para la tos", "price": 7.9},
        {"key": "termometro", "name": "Termómetro digital", "price": 8.9},
    ]},
    {"name": "Servicios", "products": [
        {"key": "analgesico", "name": "Analgésicos", "price": 4.5},
        {"key": "presion_toma", "name": "Toma de presión", "price": 0},
        {"key": "inyeccion", "name": "Aplicación de inyección", "price": 3},
    ]},
]

templates = json.loads(SEED.read_text())
for template in templates:
    if template.get("sample"):
        template["sample"]["categories"] = CATEGORIES
        print(f"  ~ {template['id']}: muestra reordenada")
SEED.write_text(json.dumps(templates, ensure_ascii=False, indent=2) + "\n")
