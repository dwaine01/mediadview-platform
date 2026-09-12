"""theme.py — tokens visuales de una plantilla.

Las texturas son CSS, no imágenes: un gradiente cónico repetido pesa cero bytes,
escala a 4K sin pixelarse y no depende de que un asset esté subido a R2. Las
tipografías se piden a Google Fonts con `display=swap` y con una pila de
respaldo, así un TV sin salida a internet igual muestra el menú legible.
"""
from __future__ import annotations

import html as html_lib
import re
from urllib.parse import quote

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

DEFAULT_PALETTE = {
    "bg": "#0E0B0A",
    "bg2": "#1A1412",
    "ink": "#FFF7EC",
    "muted": "#C4B5A6",
    "accent": "#C1440E",
    "accent2": "#7A2208",
    "accent_ink": "#FFF7EC",
    "price": "#F2C14E",
    "card": "#1C1614",
    "card2": "#241C19",
    "rule": "#4A3B33",
}

FALLBACKS = {
    "Playfair Display": "Georgia,'Times New Roman',serif",
    "Inter": "'Helvetica Neue',Arial,sans-serif",
    "Bebas Neue": "Impact,'Arial Black',sans-serif",
    "Fraunces": "Georgia,serif",
    "Outfit": "'Helvetica Neue',Arial,sans-serif",
    "Archivo Black": "'Arial Black',Impact,sans-serif",
    "Manrope": "'Helvetica Neue',Arial,sans-serif",
    "Cormorant Garamond": "Garamond,Georgia,serif",
    "DM Serif Display": "Georgia,serif",
    "Oswald": "Impact,'Arial Narrow',sans-serif",
    "Baloo 2": "'Trebuchet MS',Verdana,sans-serif",
    "Nunito": "'Helvetica Neue',Arial,sans-serif",
}

# Texturas puramente CSS. Cada una es la firma visual de un rubro.
TEXTURES = {
    "wood-dark": (
        "repeating-linear-gradient(92deg,rgba(0,0,0,.5) 0 3px,"
        "rgba(255,255,255,.035) 3px 7px,rgba(0,0,0,.42) 7px 13px)"
    ),
    "paper-warm": (
        "radial-gradient(circle at 22% 18%,rgba(255,255,255,.09),transparent 55%),"
        "repeating-linear-gradient(45deg,rgba(0,0,0,.035) 0 2px,transparent 2px 5px)"
    ),
    "linen": "repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 4px)",
    "chalk": (
        "radial-gradient(ellipse at 50% 0%,rgba(255,255,255,.12),transparent 62%),"
        "repeating-linear-gradient(118deg,rgba(255,255,255,.02) 0 2px,transparent 2px 6px)"
    ),
    "tile": (
        "repeating-linear-gradient(0deg,rgba(255,255,255,.045) 0 2px,transparent 2px 56px),"
        "repeating-linear-gradient(90deg,rgba(255,255,255,.045) 0 2px,transparent 2px 56px)"
    ),
    "gloss": "linear-gradient(160deg,rgba(255,255,255,.16) 0%,transparent 38%)",
    "none": "",
}


def colour(value, fallback: str) -> str:
    text = str(value or "").strip()
    return text if _HEX.match(text) else fallback


def _luminance(hex_colour: str) -> float:
    """0 = negro, 1 = blanco. Sirve para saber si la plantilla es clara."""
    value = hex_colour.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    try:
        red, green, blue = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return 0.0
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def palette_vars(theme: dict) -> str:
    """Las variables CSS que consumen todos los bloques."""
    given = theme.get("palette") or {}
    p = {key: colour(given.get(key), default) for key, default in DEFAULT_PALETTE.items()}
    fonts = theme.get("fonts") or {}
    display = str(fonts.get("display") or "Playfair Display")[:60]
    body = str(fonts.get("body") or "Inter")[:60]
    # La sombra que despega el texto del fondo sólo tiene sentido en plantillas
    # oscuras. En una clara (una hamburguesería, por ejemplo) el mismo truco
    # deja un halo sucio alrededor de cada letra.
    shadow = ("0 2px 12px rgba(0,0,0,.55)" if _luminance(p["bg"]) < 0.5
              else "0 1px 0 rgba(255,255,255,.5)")
    # El texto del hero va SIEMPRE sobre una foto con velo oscuro, así que no
    # puede heredar el color de texto de la plantilla: en una paleta clara
    # (un comedor, una hamburguesería) quedaba tinta oscura sobre foto oscura.
    photo_price = p["price"] if _luminance(p["bg"]) < 0.5 else "#FFD84D"
    return (
        f"--c-bg:{p['bg']};--c-bg-2:{p['bg2']};--c-ink:{p['ink']};--c-muted:{p['muted']};"
        f"--c-accent:{p['accent']};--c-accent-2:{p['accent2']};--c-accent-ink:{p['accent_ink']};"
        f"--c-price:{p['price']};--c-card:{p['card']};--c-card-2:{p['card2']};--c-rule:{p['rule']};"
        f"--f-display:'{_css_name(display)}',{FALLBACKS.get(display, 'serif')};"
        f"--f-body:'{_css_name(body)}',{FALLBACKS.get(body, 'sans-serif')};"
        f"--sh:{shadow};--c-photo-ink:#FFF8EE;--c-photo-price:{photo_price};"
        "--gap:20px;--pad:18px;--radius:18px;"
    )


def _css_name(name: str) -> str:
    return re.sub(r"[^\w \-]", "", name)


def font_link(theme: dict) -> str:
    fonts = theme.get("fonts") or {}
    families = []
    for key, weights in (("display", "400;700;800;900"), ("body", "400;600;700;800;900")):
        name = _css_name(str(fonts.get(key) or ""))[:60]
        if name:
            families.append(f"family={quote(name)}:wght@{weights}")
    if not families:
        return ""
    query = "&".join(sorted(set(families)))
    return ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?{query}&display=swap" rel="stylesheet">')


def background_css(template: dict, theme: dict) -> str:
    """Capas de fondo, de atrás hacia adelante, en un único `background`.

    Un solo shorthand en vez de divs apilados: el TV compone una capa y no
    cuatro, que en un Android TV barato es la diferencia entre 60 y 20 fps.
    """
    layers: list[str] = []
    base = colour((theme.get("palette") or {}).get("bg"), DEFAULT_PALETTE["bg"])
    for layer in reversed(template.get("background") or []):
        if not isinstance(layer, dict):
            continue
        kind = layer.get("type")
        if kind == "color":
            base = colour(layer.get("value"), base)
        elif kind == "texture":
            css = TEXTURES.get(str(layer.get("asset") or "none"))
            if css:
                layers.append(css)
        elif kind == "diagonal":
            # Un corte en diagonal: da estructura al fondo sin dibujar cajas.
            start = colour(layer.get("from"), "#00000000")
            end = colour(layer.get("to"), "#000000CC")
            angle = int(layer.get("angle") or 200)
            split = max(5, min(int(layer.get("split") or 48), 95))
            layers.append(f"linear-gradient({angle}deg,{start} 0 {split}%,{end} {split}% 100%)")
        elif kind == "gradient":
            start = colour(layer.get("from"), "#00000000")
            end = colour(layer.get("to"), "#000000CC")
            angle = int(layer.get("angle") or 180)
            shape = layer.get("shape")
            if shape == "radial":
                at = html_lib.escape(str(layer.get("at") or "50% 0%"), quote=True)[:24]
                layers.append(f"radial-gradient(ellipse at {at},{start},{end})")
            else:
                layers.append(f"linear-gradient({angle}deg,{start},{end})")
        elif kind == "image" and str(layer.get("url") or "").startswith(("/api/", "https://")):
            url = html_lib.escape(str(layer["url"]), quote=True)
            layers.append(f"url('{url}') center/cover no-repeat")
    layers.append(f"linear-gradient({base},{base})")
    return "background:" + ",".join(layers) + ";"
