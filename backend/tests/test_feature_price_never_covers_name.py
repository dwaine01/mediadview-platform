"""El precio nunca vuelve a taparle el nombre al producto.

El disco del precio se apoya en la foto redonda del destacado y crece con el
cuerpo del precio. Con un precio grande el disco se sale del círculo y pisa el
título — así se rompieron las ofertas flash. La regla que lo impide, en un test:
si el destacado lleva foto redonda, el precio va en disco y se queda chico; si
el precio manda, la foto se va al fondo y el número entra en el texto.

    cd /app/backend && python -m pytest tests/test_feature_price_never_covers_name.py -q
"""
import json
from pathlib import Path

import pytest

from template_engine import render_design

SEED = Path(__file__).resolve().parents[1] / "seed_templates"
MAX_DISC_PRICE = 80  # px: más que esto y el disco se sale del círculo

TEMPLATES = [t for path in sorted(SEED.glob("*.json"))
             for t in json.loads(path.read_text())]
BY_ID = {t["id"]: t for t in TEMPLATES}


def features(template):
    return [b for b in template.get("blocks") or []
            if isinstance(b, dict) and b.get("type") == "feature"]


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t["id"])
def test_big_price_never_rides_on_the_photo(template):
    for block in features(template):
        with_photo = block.get("photo") is not False
        style = str(block.get("price_style") or ("disc" if with_photo else "plain"))
        if with_photo and style == "disc" and str(block.get("align") or "left") != "right":
            # Con la foto a la izquierda el disco cuelga hacia la columna de
            # texto. Con la foto a la derecha cuelga hacia el borde del tablero
            # y puede ser enorme sin molestar a nadie.
            assert int(block.get("price_size") or 56) <= MAX_DISC_PRICE, (
                f"{template['id']}: precio en disco de {block.get('price_size')}px sobre la "
                f"foto: se sale del círculo y tapa el nombre. Usá price_style/plain o "
                f"bajá el cuerpo a {MAX_DISC_PRICE}px.")


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t["id"])
def test_offer_boards_render_name_and_price(template):
    """Las cuatro ofertas flash tienen que mostrar nombre y precio, no uno solo."""
    if template.get("industry") != "offers":
        pytest.skip("no es una oferta flash")
    sample = template.get("sample") or (BY_ID.get(template.get("sample_from")) or {}).get("sample")
    assert sample, f"{template['id']}: sin contenido de muestra"
    products, categories = {}, []
    for category in sample["categories"]:
        ids = []
        for item in category["products"]:
            pid = f"{template['id']}:{item['key']}"
            products[pid] = {**item, "id": pid,
                             "image_url": f"/api/static/template-samples/{item['image']}"}
            ids.append(pid)
        categories.append({"name": category["name"], "product_ids": ids})
    design = {"brand": {"business_name": sample["business_name"]},
              "bindings": {**{k: v for k, v in sample.items() if isinstance(v, (str, int, float))},
                           "categories": categories}}
    html = render_design(design, template, products)
    first = sample["categories"][0]["products"][0]
    assert first["name"] in html
    assert "$7.99" in html or f"{first['price']}" in html
    # Un solo precio por producto: o el disco o el número del texto, nunca los dos.
    assert not ('class="disc"' in html and 'class="feat-price"' in html), (
        f"{template['id']}: el precio sale dos veces")
