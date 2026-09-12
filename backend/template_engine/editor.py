"""editor.py — los campos del editor salen de la plantilla, no de una lista a mano.

La regla que esto hace cumplir: si un bloque se dibuja en el lienzo, tiene que
tener su campo en el panel. Nada fijo, nada que el cliente vea en la tele y no
pueda cambiar. Por eso el panel no sabe nada de «pizzería»: le pregunta a la
plantilla qué campos mostrar y los dibuja.

La otra mitad de la regla vive en `backend/tests/test_editor_schema.py`: una
plantilla nueva que meta un texto literal en un bloque hace fallar el test.
"""
from __future__ import annotations

# Etiquetas en el idioma del dueño del negocio, no del programador.
TEXT_FIELDS: dict[str, tuple[str, str]] = {
    "tagline": ("Frase debajo del nombre", "Horno de leña · desde 1998"),
    "ticker": ("Mensaje en movimiento", "Delivery gratis en pedidos de $25 o más"),
    "hero_kicker": ("Etiqueta de la foto grande", "La más pedida"),
    "hero_title": ("Título de la foto grande", ""),
    "promo_kicker": ("Etiqueta de la promoción", "Combo familiar"),
    "promo_title": ("Qué incluye la promoción", "2 grandes + refresco 2L"),
    "promo_price": ("Precio de la promoción", "$29.99"),
    "qr_url": ("Enlace del código QR", "https://mi-negocio.com/menu"),
    "qr_label": ("Texto debajo del QR", "Escaneá el menú"),
    "hours": ("Horario", "Lun a Dom · 11:00 a 23:00"),
    "address": ("Dirección", ""),
    "phone": ("Teléfono", ""),
    "footer": ("Texto del pie", ""),
    "note": ("Aviso", ""),
}

PROMO_FIELDS = ("promo_kicker", "promo_title", "promo_price")
PRODUCT_BLOCKS = ("product_grid", "product_list", "hero", "feature", "backdrop")


def _category_index(binds) -> int | None:
    """`categories[2]` → 2."""
    text = str(binds or "")
    if not text.startswith("categories[") or not text.endswith("]"):
        return None
    inner = text[len("categories["):-1]
    return int(inner) if inner.isdigit() else None


def _text_field(name: str) -> dict:
    label, placeholder = TEXT_FIELDS.get(name, (f"Texto «{name}»", ""))
    return {
        "path": f"bindings.{name}",
        "label": label,
        "placeholder": placeholder,
        "kind": "url" if name.endswith("_url") else "text",
        # Todo texto suelto se puede dejar vacío: el bloque desaparece del
        # diseño en vez de quedar con el texto de muestra puesto.
        "removable": True,
    }


def editor_schema(template: dict) -> dict:
    """Qué puede editar el cliente en esta plantilla, en el orden en que lo ve."""
    blocks = [b for b in (template.get("blocks") or []) if isinstance(b, dict)]
    business: list[dict] = []
    promo: list[dict] = []
    qr: list[dict] = []
    seen: set[str] = set()
    categories: dict[int, dict] = {}

    def add(target: list[dict], field: dict) -> None:
        if field["path"] in seen:
            return
        seen.add(field["path"])
        target.append(field)

    def category(index: int) -> dict:
        return categories.setdefault(index, {
            "index": index,
            "name_path": f"bindings.categories[{index}].name",
            "has_header": False,
            "product_fields": [],
            "slots": None,
        })

    def allow(index: int, *names: str) -> None:
        fields = category(index)["product_fields"]
        for name in names:
            if name not in fields:
                fields.append(name)

    for block in blocks:
        kind = str(block.get("type") or "")

        if kind == "brand":
            add(business, {"path": "brand.business_name", "label": "Nombre del negocio",
                           "placeholder": "Mi negocio", "kind": "text", "removable": False})
            add(business, {"path": "brand.logo_url", "label": "Logo",
                           "kind": "image", "removable": True})

        elif kind == "text":
            name = str(block.get("field") or "")
            if name:
                add(promo if name in PROMO_FIELDS else qr if name == "qr_url" else business,
                    _text_field(name))

        elif kind == "ticker":
            add(business, _text_field("ticker"))

        elif kind == "promo":
            for name in PROMO_FIELDS:
                add(promo, _text_field(name))

        elif kind == "qr":
            add(qr, _text_field("qr_url"))
            add(qr, _text_field("qr_label"))

        elif kind == "media":
            add(business, {"path": f"bindings.media_{len(seen)}", "label": "Imagen o video",
                           "kind": "image", "removable": True})

        index = _category_index(block.get("binds"))
        if index is None:
            continue
        if kind == "category":
            category(index)["has_header"] = True
        elif kind == "product_grid":
            allow(index, "name", "price", "image", "badge")
            if block.get("show_desc"):
                allow(index, "description")
            slots = max(1, int(block.get("cols") or 1)) * max(1, int(block.get("rows") or 1))
            current = category(index)["slots"]
            category(index)["slots"] = slots if current is None else current + slots
        elif kind == "product_list":
            allow(index, "name", "price")
            if block.get("thumbs"):
                allow(index, "image")
        elif kind in ("hero", "feature"):
            allow(index, "name", "image")
            if kind == "feature":
                allow(index, "price", "description")
            add(business, _text_field("hero_kicker"))
            if not block.get("binds"):
                add(business, _text_field("hero_title"))
        elif kind == "backdrop":
            allow(index, "image")

    groups = [group for group in (
        {"title": "Tu negocio", "fields": business},
        {"title": "Promoción", "fields": promo},
        {"title": "Código QR", "fields": qr},
    ) if group["fields"]]

    return {
        "groups": groups,
        "categories": [categories[key] for key in sorted(categories)],
    }


# Claves que harían que un bloque dibuje texto propio de la plantilla, sin
# campo en el editor. El test del schema las prohíbe.
LITERAL_KEYS = ("value", "title", "kicker", "price", "label", "image_url", "video_url")


def literal_texts(template: dict) -> list[str]:
    """Textos que la plantilla dibuja por su cuenta. Tiene que dar vacío."""
    offenders = []
    for block in (template.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        for key in LITERAL_KEYS:
            if str(block.get(key) or "").strip():
                offenders.append(f"{block.get('type')}.{key}")
    return offenders


__all__ = ["editor_schema", "literal_texts", "TEXT_FIELDS"]
