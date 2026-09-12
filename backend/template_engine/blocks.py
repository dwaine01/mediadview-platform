"""blocks.py — el vocabulario cerrado de bloques que compone cualquier plantilla.

Son diez. Cada uno sabe verse profesional solo: jerarquía, sombra, profundidad
y espaciado salen de los tokens del tema, no de valores sueltos. Una plantilla
nueva combina estos bloques en un JSON; nadie escribe CSS por plantilla.

Las medidas vienen en pixeles del lienzo de la plantilla (`rect: [x,y,w,h]`) y
los cuerpos de letra en pixeles también. Es deliberado: el escenario completo se
escala después con un único `transform`, así una plantilla diseñada para 1920x1080
se ve idéntica en 4K, en 720p y en la vista previa del celular.
"""
from __future__ import annotations

import html as html_lib
from urllib.parse import quote

MAX_ITEMS_PER_BLOCK = 40
_ANIMS = {"fade": "anim-fade", "pop": "anim-pop", "ken": "anim-ken",
          "rise": "anim-rise", "none": ""}


def esc(value) -> str:
    return html_lib.escape(str(value if value is not None else ""), quote=True)


def safe_url(value) -> str:
    text = str(value or "").strip()
    return esc(text) if text.startswith(("/api/", "https://")) else ""


def money(value, currency: str = "$") -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{currency}{int(number)}" if number == int(number) else f"{currency}{number:.2f}"


def _rect(block: dict) -> str:
    rect = block.get("rect") or [0, 0, 100, 100]
    try:
        x, y, w, h = (int(round(float(v))) for v in rect[:4])
    except (TypeError, ValueError):
        x, y, w, h = 0, 0, 100, 100
    return f"left:{x}px;top:{y}px;width:{max(1, w)}px;height:{max(1, h)}px"


def _animation(block: dict) -> str:
    """Clase de animación del bloque. La entrada se escalona con
    `animation-delay` en cada hijo, así la pantalla se compone en vez de
    aparecer de golpe."""
    return _ANIMS.get(str(block.get("anim") or "fade"), "")


def _binding(design: dict, path: str):
    """Lee `categories[0].products` del diseño del cliente."""
    node = design.get("bindings") or {}
    for part in str(path or "").replace("]", "").split("."):
        if not part:
            continue
        key, _, index = part.partition("[")
        node = (node or {}).get(key) if isinstance(node, dict) else None
        if index != "":
            if not isinstance(node, list):
                return None
            position = int(index) if index.isdigit() else 0
            node = node[position] if position < len(node) else None
    return node


def _field(design: dict, name: str, default: str = "") -> str:
    bindings = design.get("bindings") or {}
    brand = design.get("brand") or {}
    return str(bindings.get(name) or brand.get(name) or default)


def _resolve_products(ids, products: dict[str, dict]) -> list[dict]:
    return [products[str(pid)] for pid in (ids or [])[:MAX_ITEMS_PER_BLOCK]
            if str(pid) in products]


def _category(design: dict, block: dict, products: dict[str, dict]) -> tuple[str, list[dict]]:
    node = _binding(design, block.get("binds") or "")
    if isinstance(node, dict):
        return str(node.get("name") or ""), _resolve_products(node.get("product_ids"), products)
    if isinstance(node, list):
        return "", _resolve_products(node, products)
    return "", []


# ── bloques ───────────────────────────────────────────────────────────────

def _brand(block, design, theme, products) -> str:
    logo = safe_url((design.get("brand") or {}).get("logo_url"))
    name = esc(_field(design, "business_name"))
    size = int(block.get("size") or 54)
    img = f'<img src="{logo}" alt="">' if logo else ""
    label = (f'<div class="brand-name" data-fit style="font-size:{size}px">{name}</div>'
             if name else "")
    return f'<div class="blk brand" style="{_rect(block)}">{img}{label}</div>'


def _category_header(block, design, theme, products) -> str:
    name = esc(_category(design, block, products)[0] or block.get("label") or "")
    if not name:
        return ""
    size = int(block.get("size") or 38)
    rule = "" if block.get("rule") is False else '<div class="cat-rule"></div>'
    return (f'<div class="blk cat {_animation(block)}" style="{_rect(block)}">'
            f'<div class="cat-label" style="font-size:{size}px">{name}</div>{rule}</div>')


def _card(product: dict, block: dict, index: int) -> str:
    photo = safe_url(product.get("image_url"))
    name_size = int(block.get("name_size") or 26)
    price_size = int(block.get("price_size") or 30)
    desc_size = int(block.get("desc_size") or 15)
    badge_size = max(9, int(name_size * 0.42))

    # Sin foto no se deja un círculo vacío: se dibuja un monograma con la
    # inicial del producto. Un hueco blanco parece un error; una inicial
    # tipográfica parece una decisión de diseño.
    initial = esc((str(product.get("name") or "·").strip() or "·")[0].upper())
    media = (f'<img src="{photo}" alt="">' if photo
             else f'<div class="card-mono" style="font-size:{int(name_size * 1.9)}px">'
                  f'{initial}</div>')
    badge = ('<div class="badge" style="font-size:%dpx">%s</div>'
             % (badge_size, esc(product.get("badge")))
             if str(product.get("badge") or "").strip() else "")
    sold = ('<div class="sold" style="font-size:%dpx">Agotado</div>' % int(name_size * 0.8)
            if product.get("available") is False else "")

    variants = product.get("variants") or []
    if variants:
        price_html = '<div class="variants">' + "".join(
            f'<div class="variant" style="font-size:{int(price_size * 0.62)}px">'
            f'<span>{esc(v.get("label"))}</span><b>{esc(money(v.get("price")))}</b></div>'
            for v in variants[:4]) + "</div>"
    else:
        price_html = (f'<div class="card-price" style="font-size:{price_size}px">'
                      f'{esc(money(product.get("sale_price") or product.get("price")))}</div>')

    desc = (f'<div class="card-desc" style="font-size:{desc_size}px">'
            f'{esc(product.get("description"))}</div>'
            if block.get("show_desc") and product.get("description") else "")

    bare = " card-bare" if str(block.get("card") or "") == "bare" else ""
    return (f'<div class="card{bare} {_animation(block)}"'
            f' style="animation-delay:{min(index, 14) * 0.06:.2f}s">'
            f'<div class="card-photo">{badge}{media}{sold}</div>'
            f'<div class="card-body">'
            f'<div class="card-name" style="font-size:{name_size}px" data-fit>{esc(product.get("name"))}</div>'
            f'{desc}{price_html}</div></div>')


def _product_grid(block, design, theme, products) -> str:
    items = _category(design, block, products)[1]
    if not items:
        return ""
    cols = max(1, int(block.get("cols") or 3))
    rows = max(1, int(block.get("rows") or 3))
    gap = int(block.get("gap") or 24)
    # `skip` deja afuera los primeros productos: sirve cuando el estrella ya
    # está enorme arriba y la grilla tiene que mostrar los que siguen.
    skip = max(0, int(block.get("skip") or 0))
    visible = items[skip:] or items
    cards = "".join(_card(item, block, i) for i, item in enumerate(visible[:cols * rows]))
    return (f'<div class="blk grid" style="{_rect(block)};gap:{gap}px;'
            f'grid-template-columns:repeat({cols},1fr);'
            f'grid-template-rows:repeat({rows},1fr)">{cards}</div>')


def _product_list(block, design, theme, products) -> str:
    items = _category(design, block, products)[1]
    if not items:
        return ""
    size = int(block.get("size") or 24)
    thumbs = bool(block.get("thumbs"))
    rows = []
    for index, product in enumerate(items):
        thumb = safe_url(product.get("image_url"))
        picture = (f'<img class="row-thumb" src="{thumb}" alt="">' if thumbs and thumb else "")
        variants = product.get("variants") or []
        price = (" / ".join(esc(money(v.get("price"))) for v in variants[:3]) if variants
                 else esc(money(product.get("sale_price") or product.get("price"))))
        faded = ';opacity:.45' if product.get("available") is False else ''
        rows.append(
            f'<div class="row {_animation(block)}"'
            f' style="font-size:{size}px;animation-delay:{min(index, 14) * 0.05:.2f}s{faded}">'
            f'{picture}<div class="row-name">{esc(product.get("name"))}</div>'
            f'<div class="row-dots"></div><div class="row-price">{price}</div></div>')
    gap = int(block.get("gap") or 10)
    return (f'<div class="blk list" style="{_rect(block)};gap:{gap}px">'
            + "".join(rows) + "</div>")


def _hero(block, design, theme, products) -> str:
    items = _category(design, block, products)[1]
    product = items[0] if items else {}
    photo = safe_url(product.get("image_url") or block.get("image_url"))
    video = safe_url(product.get("video_url") or block.get("video_url"))
    kicker = esc(block.get("kicker") or _field(design, "hero_kicker"))
    name = esc(block.get("title") or product.get("name") or _field(design, "hero_title"))
    price = esc(money(block.get("price") or product.get("sale_price") or product.get("price")))
    name_size = int(block.get("name_size") or 76)
    price_size = int(block.get("price_size") or 88)

    if video:
        media = f'<video src="{video}" autoplay muted loop playsinline></video>'
    elif photo:
        media = f'<img src="{photo}" alt="">'
    else:
        media = ""
    ken = " anim-ken" if block.get("ken") and photo else ""
    return (f'<div class="blk hero{ken}" style="{_rect(block)}">{media}'
            f'<div class="hero-body">'
            + (f'<div class="hero-kicker" style="font-size:{int(name_size * 0.26)}px">{kicker}</div>'
               if kicker else "")
            + f'<div class="hero-name" style="font-size:{name_size}px" data-fit>{name}</div>'
            + (f'<div class="hero-price" style="font-size:{price_size}px">{price}</div>'
               if price else "")
            + "</div></div>")


def _feature(block, design, theme, products) -> str:
    """El producto estrella, sin tarjeta: foto redonda, texto al lado, precio en disco.

    Con `rotate` (segundos) va cambiando solo entre los productos de su
    sección: la pantalla se siente viva y el cliente ve más de un plato sin
    que el tablero se llene de fotos chicas.
    """
    items = _category(design, block, products)[1]
    if not items:
        return ""
    rotate = int(block.get("rotate") or 0)
    shown = items[:4] if rotate else items[:1]
    kicker = esc(_field(design, "hero_kicker"))
    name_size = int(block.get("name_size") or 86)
    price_size = int(block.get("price_size") or 56)
    desc_size = int(block.get("desc_size") or 26)
    side = "right" if str(block.get("align") or "left") == "right" else "left"
    ken = " anim-ken" if block.get("ken") else ""
    # La foto redonda se apaga cuando la fotografía ya está en el fondo
    # (`backdrop`): dos veces el mismo plato en la misma pantalla es ruido.
    with_photo = block.get("photo") is not False
    # Un precio enorme no cabe en un disco apoyado en la foto: se sale del
    # círculo y se come el título. Cuando el precio manda, va en el texto y
    # puede ir incluso antes del nombre (`lead`).
    style = str(block.get("price_style") or ("disc" if with_photo else "plain"))
    if style not in ("disc", "plain", "lead"):
        style = "plain"
    if style == "disc" and not with_photo:
        style = "plain"

    slides = []
    for index, product in enumerate(shown):
        photo = safe_url(product.get("image_url")) if with_photo else ""
        name = esc(product.get("name") or _field(design, "hero_title"))
        description = esc(product.get("description"))
        price = esc(money(product.get("sale_price") or product.get("price")))
        disc = (f'<div class="disc" style="font-size:{price_size}px">{price}</div>'
                if price and style == "disc" else "")
        media = (f'<div class="feat-photo{ken}"><img src="{photo}" alt="">{disc}</div>'
                 if photo else "")
        big = (f'<div class="feat-price" style="font-size:{price_size}px" data-fit>{price}</div>'
               if price and style in ("plain", "lead") else "")
        copy = (
            (big if style == "lead" else "")
            + (f'<div class="feat-kicker" style="font-size:{int(name_size * 0.22)}px">{kicker}</div>'
               if kicker else "")
            + f'<div class="feat-name" style="font-size:{name_size}px" data-fit>{name}</div>'
            + (f'<div class="feat-desc" style="font-size:{desc_size}px">{description}</div>'
               if description else "")
            + (big if style == "plain" else "")
        )
        slides.append(f'<div class="slide{" on" if index == 0 else ""}">{media}'
                      f'<div class="feat-copy">{copy}</div></div>')
    rotation = f' data-rotate="{max(8, rotate) * 1000}"' if rotate and len(slides) > 1 else ""
    return (f'<div class="blk feat feat-{side} {_animation(block)}"{rotation}'
            f' style="{_rect(block)}">' + "".join(slides) + "</div>")


def _backdrop(block, design, theme, products) -> str:
    """Foto de fondo que se disuelve en el fondo de la plantilla.

    Nada de una foto metida en un rectángulo: la imagen se desvanece con una
    máscara hacia el lado donde va el texto, así la fotografía es parte de la
    composición y el texto sigue legible.
    """
    items = _category(design, block, products)[1]
    rotate = int(block.get("rotate") or 0)
    photos = [safe_url(item.get("image_url")) for item in (items[:4] if rotate else items[:1])]
    photos = [photo for photo in photos if photo] or [safe_url(block.get("photo"))]
    if not photos[0]:
        return ""
    fade = str(block.get("fade") or "right")
    if fade not in ("right", "left", "bottom", "top"):
        fade = "right"
    ken = " anim-ken" if block.get("ken") else ""
    slides = "".join(f'<div class="slide{" on" if i == 0 else ""}{ken}">'
                     f'<img src="{photo}" alt=""></div>'
                     for i, photo in enumerate(photos))
    rotation = f' data-rotate="{max(8, rotate) * 1000}"' if rotate and len(photos) > 1 else ""
    return (f'<div class="blk back back-{fade}"{rotation} style="{_rect(block)};z-index:0">'
            f'{slides}</div>')


def _promo(block, design, theme, products) -> str:
    kicker = esc(block.get("kicker") or _field(design, "promo_kicker"))
    title = esc(block.get("title") or _field(design, "promo_title"))
    price = esc(money(block.get("price") or _field(design, "promo_price")))
    if not (title or price):
        return ""
    title_size = int(block.get("size") or 42)
    # Una promo ancha y baja se lee mejor con el precio al costado; una angosta,
    # apilada. Lo decide la forma del hueco, no una opción más en el JSON.
    rect = block.get("rect") or [0, 0, 100, 100]
    try:
        wide = float(rect[2]) / max(1.0, float(rect[3])) >= 3.4
    except (TypeError, ValueError, IndexError):
        wide = False
    copy = (
        (f'<div class="promo-kicker" style="font-size:{int(title_size * 0.34)}px">{kicker}</div>'
         if kicker else "")
        + (f'<div class="promo-title" style="font-size:{title_size}px" data-fit>{title}</div>'
           if title else "")
    )
    return (f'<div class="blk promo anim-pop{" promo-wide" if wide else ""}" style="{_rect(block)}">'
            f'<div class="promo-copy">{copy}</div>'
            + (f'<div class="promo-price" style="font-size:{int(title_size * 1.5)}px">{price}</div>'
               if price else "")
            + "</div>")


def _qr(block, design, theme, products) -> str:
    target = str(_field(design, "qr_url") or block.get("url") or "").strip()
    if not target.startswith(("http://", "https://")):
        return ""
    src = ("https://api.qrserver.com/v1/create-qr-code/?size=360x360&margin=0&data="
           + quote(target, safe=""))
    label = esc(_field(design, "qr_label") or block.get("label") or "Escaneá el menú")
    return (f'<div class="blk qr" style="{_rect(block)}"><img src="{esc(src)}" alt="">'
            f'<div class="qr-label" style="font-size:{int(block.get("size") or 13)}px">{label}</div></div>')


def _text(block, design, theme, products) -> str:
    content = esc(block.get("value") or _field(design, str(block.get("field") or "")))
    if not content.strip():
        return ""
    align = str(block.get("align") or "left")
    align = align if align in ("left", "center", "right") else "left"
    weight = int(block.get("weight") or 600)
    colour_token = "var(--c-accent)" if block.get("accent") else "var(--c-ink)"
    upper = "text-transform:uppercase;letter-spacing:.12em;" if block.get("upper") else ""
    return (f'<div class="blk txt" style="{_rect(block)};text-align:{align};font-weight:{weight};'
            f'color:{colour_token};{upper}">'
            f'<span data-fit style="font-size:{int(block.get("size") or 22)}px">{content}</span></div>')


def _media(block, design, theme, products) -> str:
    video = safe_url(block.get("video_url"))
    image = safe_url(block.get("image_url"))
    if video:
        inner = f'<video src="{video}" autoplay muted loop playsinline></video>'
    elif image:
        inner = f'<img src="{image}" alt="">'
    else:
        return ""
    return f'<div class="blk media" style="{_rect(block)}">{inner}</div>'


def _ticker(block, design, theme, products) -> str:
    content = esc(block.get("value") or _field(design, "ticker"))
    if not content.strip():
        return ""
    size = int(block.get("size") or 22)
    return (f'<div class="blk txt" style="{_rect(block)};display:flex;align-items:center;'
            f'background:var(--c-accent);color:var(--c-accent-ink);padding:0 var(--pad);'
            f'border-radius:999px;font-weight:900;text-transform:uppercase;letter-spacing:.16em">'
            f'<span data-fit style="font-size:{size}px;white-space:nowrap">{content}</span></div>')


BLOCKS = {
    "brand": _brand,
    "feature": _feature,
    "backdrop": _backdrop,
    "category": _category_header,
    "product_grid": _product_grid,
    "product_list": _product_list,
    "hero": _hero,
    "promo": _promo,
    "qr": _qr,
    "text": _text,
    "media": _media,
    "ticker": _ticker,
}


def render_block(block: dict, design: dict, theme: dict, products: dict[str, dict]) -> str:
    handler = BLOCKS.get(str(block.get("type") or ""))
    return handler(block, design, theme, products) if handler else ""
