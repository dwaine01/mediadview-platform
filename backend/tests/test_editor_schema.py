"""test_editor_schema.py — la regla que impide plantillas con contenido fijo.

Cada bloque que se dibuja en el lienzo tiene que tener su campo en el panel. Si
alguien escribe una plantilla nueva con un texto literal adentro (un «Combo
familiar» hardcodeado, por ejemplo), este test falla: el cliente vería eso en
su tele sin poder cambiarlo.

    cd /app/backend && python -m pytest tests/test_editor_schema.py -q
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from template_engine.blocks import BLOCKS                      # noqa: E402
from template_engine.editor import (_category_index,           # noqa: E402
                                    editor_schema, literal_texts)

SEED_DIR = BACKEND / "seed_templates"
TEMPLATES = [template
             for path in sorted(SEED_DIR.glob("*.json"))
             for template in json.loads(path.read_text())]
PRODUCT_BLOCKS = ("product_grid", "product_list", "hero")


def _ids(template):
    return template["id"]


@pytest.fixture(params=TEMPLATES, ids=_ids)
def template(request):
    return request.param


def test_no_literal_text_in_blocks(template):
    """Ningún bloque dibuja texto propio de la plantilla."""
    assert literal_texts(template) == [], (
        f"{template['id']} tiene contenido fijo: {literal_texts(template)}. "
        "Ese texto tiene que venir de `sample` y ser editable.")


def test_every_block_type_exists(template):
    for block in template["blocks"]:
        assert block["type"] in BLOCKS, f"{template['id']}: bloque desconocido {block['type']}"


def test_every_text_field_has_an_editor_field(template):
    schema = editor_schema(template)
    paths = {field["path"] for group in schema["groups"] for field in group["fields"]}
    for block in template["blocks"]:
        if block["type"] == "text":
            assert f"bindings.{block['field']}" in paths, (
                f"{template['id']}: el texto «{block['field']}» no se puede editar")
        if block["type"] == "ticker":
            assert "bindings.ticker" in paths
        if block["type"] == "promo":
            assert {"bindings.promo_title", "bindings.promo_price"} <= paths
        if block["type"] == "qr":
            assert "bindings.qr_url" in paths
        if block["type"] == "brand":
            assert {"brand.business_name", "brand.logo_url"} <= paths


def test_every_product_block_has_its_section(template):
    schema = editor_schema(template)
    sections = {section["index"] for section in schema["categories"]}
    for block in template["blocks"]:
        if block["type"] not in PRODUCT_BLOCKS:
            continue
        index = _category_index(block.get("binds"))
        assert index is not None, f"{template['id']}: {block['type']} sin `binds`"
        assert index in sections
        fields = next(s for s in schema["categories"] if s["index"] == index)["product_fields"]
        assert "name" in fields and "price" in fields or block["type"] == "hero"
        if block.get("show_desc"):
            assert "description" in fields, (
                f"{template['id']}: dibuja la descripción pero no se puede editar")


def test_sample_covers_every_editable_text(template):
    """La muestra llena los campos: una plantilla recién usada se ve completa."""
    sample = template.get("sample")
    if not sample:      # hereda la muestra de otra plantilla del mismo rubro
        assert template.get("sample_from")
        return
    schema = editor_schema(template)
    assert sample.get("business_name"), f"{template['id']}: la muestra no tiene nombre"
    for group in schema["groups"]:
        for field in group["fields"]:
            if field["kind"] == "image" or not field["path"].startswith("bindings."):
                continue
            key = field["path"].split(".", 1)[1]
            assert key in sample, (
                f"{template['id']}: la muestra no trae «{key}», el hueco queda vacío")
    for section in schema["categories"]:
        categories = sample.get("categories") or []
        assert section["index"] < len(categories), (
            f"{template['id']}: la plantilla dibuja la sección {section['index']} "
            "pero la muestra no la trae")
        assert (categories[section['index']].get("products")), "sección de muestra vacía"
