"""rebuild_templates.py — las plantillas se arman, no se escriben a mano.

Hay tres FAMILIAS de diseño aprobadas por el dueño (A claro fast casual, B cine
oscuro, C latino sereno) y una vertical para tótem. Cada rubro aporta su
identidad —paleta, tipografías, fondo, fotos— y su contenido de muestra, que ya
vive en los archivos actuales y no se toca.

Así una familia se mejora en UN lugar y los veinte tableros mejoran con ella.

    cd /app/backend && python scripts/rebuild_templates.py
"""
import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed_templates"


# ─── Familias: la composición, sin color ni contenido ───────────────────────
def family_a(name_size=96):
    """Claro, con aire: el estrella en círculo, el resto en fotos redondas."""
    return {
        "canvas": {"w": 1920, "h": 1080, "orientation": "landscape"},
        "safe_zone": 56,
        "blocks": [
            {"type": "brand", "rect": [60, 44, 1000, 92], "size": 72},
            {"type": "text", "rect": [60, 142, 1000, 34], "field": "tagline",
             "size": 23, "upper": True, "accent": True},
            {"type": "feature", "rect": [60, 196, 1090, 470], "binds": "categories[0]",
             "name_size": name_size, "price_size": 60, "desc_size": 27, "ken": True,
             "rotate": 60, "anim": "pop"},
            {"type": "category", "rect": [60, 700, 1090, 48], "binds": "categories[0]", "size": 32},
            {"type": "product_grid", "rect": [60, 756, 1090, 268], "cols": 3, "rows": 1,
             "gap": 28, "binds": "categories[0]", "card": "bare", "skip": 1,
             "name_size": 30, "price_size": 38, "anim": "rise"},
            {"type": "category", "rect": [1210, 196, 650, 50], "binds": "categories[1]", "size": 32},
            {"type": "product_list", "rect": [1210, 256, 650, 220], "binds": "categories[1]",
             "size": 34, "gap": 12, "anim": "rise"},
            {"type": "category", "rect": [1210, 508, 650, 46], "binds": "categories[2]", "size": 30},
            {"type": "product_list", "rect": [1210, 564, 650, 200], "binds": "categories[2]",
             "size": 32, "gap": 10, "anim": "rise"},
            {"type": "promo", "rect": [1210, 800, 650, 224], "size": 40},
        ],
        "motion": {"preset": "pop-in"},
    }


def family_b(brand_size=86):
    """Cine: la foto ocupa media pantalla y se disuelve en el negro."""
    return {
        "canvas": {"w": 1920, "h": 1080, "orientation": "landscape"},
        "safe_zone": 60,
        "blocks": [
            {"type": "backdrop", "rect": [820, 0, 1100, 1080], "binds": "categories[0]",
             "fade": "left", "ken": True, "rotate": 60},
            {"type": "brand", "rect": [80, 84, 700, 118], "size": brand_size},
            {"type": "text", "rect": [80, 218, 700, 34], "field": "tagline",
             "size": 23, "upper": True, "accent": True},
            {"type": "category", "rect": [80, 300, 700, 56], "binds": "categories[0]", "size": 40},
            {"type": "product_list", "rect": [80, 376, 700, 460], "binds": "categories[0]",
             "size": 38, "gap": 14, "anim": "rise"},
            {"type": "category", "rect": [80, 856, 700, 46], "binds": "categories[1]", "size": 30},
            {"type": "product_list", "rect": [80, 912, 700, 148], "binds": "categories[1]",
             "size": 32, "gap": 10, "anim": "rise"},
            {"type": "promo", "rect": [1180, 792, 680, 232], "size": 44},
        ],
        "motion": {"preset": "subtle-fade"},
    }


def family_c():
    """Sereno: crema, color en dosis chicas y fotos redondas sin recuadro."""
    return {
        "canvas": {"w": 1920, "h": 1080, "orientation": "landscape"},
        "safe_zone": 52,
        "blocks": [
            {"type": "brand", "rect": [56, 46, 980, 98], "size": 80},
            {"type": "text", "rect": [56, 152, 980, 36], "field": "tagline",
             "size": 24, "upper": True, "accent": True},
            {"type": "feature", "rect": [1000, 60, 864, 420], "binds": "categories[0]",
             "align": "right", "name_size": 72, "price_size": 48, "desc_size": 23,
             "ken": True, "rotate": 60, "anim": "pop"},
            {"type": "category", "rect": [56, 226, 900, 50], "binds": "categories[0]", "size": 34},
            {"type": "product_grid", "rect": [56, 300, 900, 330], "cols": 3, "rows": 1,
             "gap": 28, "binds": "categories[0]", "card": "bare", "skip": 1,
             "name_size": 30, "price_size": 38, "anim": "rise"},
            {"type": "category", "rect": [56, 690, 900, 48], "binds": "categories[2]", "size": 32},
            {"type": "product_list", "rect": [56, 748, 900, 204], "binds": "categories[2]",
             "size": 34, "gap": 10, "anim": "rise"},
            {"type": "category", "rect": [1000, 512, 864, 48], "binds": "categories[1]", "size": 32},
            {"type": "product_list", "rect": [1000, 570, 864, 150], "binds": "categories[1]",
             "size": 34, "gap": 10, "anim": "rise"},
            {"type": "promo", "rect": [1000, 742, 864, 192], "size": 36},
            {"type": "ticker", "rect": [56, 976, 1808, 72], "size": 26},
        ],
        "motion": {"preset": "pop-in"},
    }


def family_v():
    """Tótem vertical: estrella arriba, cuatro fotos redondas y la lista abajo."""
    return {
        "canvas": {"w": 1080, "h": 1920, "orientation": "portrait"},
        "safe_zone": 44,
        "blocks": [
            {"type": "brand", "rect": [44, 44, 992, 104], "size": 78},
            {"type": "text", "rect": [44, 156, 992, 36], "field": "tagline",
             "size": 25, "upper": True, "accent": True, "align": "center"},
            {"type": "feature", "rect": [44, 214, 992, 470], "binds": "categories[0]",
             "name_size": 78, "price_size": 54, "desc_size": 25, "ken": True,
             "rotate": 60, "anim": "pop"},
            {"type": "category", "rect": [44, 716, 992, 52], "binds": "categories[0]", "size": 36},
            {"type": "product_grid", "rect": [44, 782, 992, 620], "cols": 2, "rows": 2,
             "gap": 26, "binds": "categories[0]", "card": "bare", "skip": 1,
             "name_size": 34, "price_size": 42, "anim": "rise"},
            {"type": "category", "rect": [44, 1434, 992, 48], "binds": "categories[1]", "size": 32},
            {"type": "product_list", "rect": [44, 1492, 992, 190], "binds": "categories[1]",
             "size": 34, "gap": 10, "anim": "rise"},
            {"type": "promo", "rect": [44, 1716, 992, 168], "size": 34},
        ],
        "motion": {"preset": "pop-in"},
    }


FAMILY_LABEL = {
    "a": ("Vitrina clara", "El plato estrella en grande y todo el menú de un vistazo"),
    "b": ("Cine oscuro", "La foto ocupa media pantalla y la carta se lee al costado"),
    "c": ("Sereno", "Fondo claro, color en dosis chicas y fotos redondas"),
    "v": ("Tótem vertical", "Para la pared o la fila de la caja"),
}
FAMILIES = {"a": family_a, "b": family_b, "c": family_c, "v": family_v}


# ─── Identidad de cada rubro: dos paletas (clara y oscura) y tipografías ────
def theme(palette, display, body, mood, background):
    return {"palette": palette, "fonts": {"display": display, "body": body}, "mood": mood}, background


LIGHT_BG = lambda a: [{"type": "color", "value": a[0]},
                      {"type": "diagonal", "angle": 200, "from": a[1], "to": a[2], "split": 58},
                      {"type": "texture", "asset": a[3]}]
DARK_BG = lambda a: [{"type": "color", "value": a[0]},
                     {"type": "texture", "asset": a[1]},
                     {"type": "gradient", "shape": "radial", "at": a[2], "from": a[3],
                      "to": "#00000000"}]

RUBROS = {
    "pizzeria": {
        "industry": "pizzeria", "brand": "Trattoria Forno",
        "display": "Fraunces", "body": "Manrope", "mood": "artesanal-horno",
        "light": {"bg": "#FFF8EE", "bg2": "#F5E7D2", "ink": "#241611", "muted": "#6B5546",
                  "accent": "#C1440E", "accent2": "#8E2F06", "accent_ink": "#FFFFFF",
                  "price": "#1E3A2B", "card": "#FFFFFF", "card2": "#FBF1E2", "rule": "#E2CDB0"},
        "dark": {"bg": "#120C0A", "bg2": "#1D1411", "ink": "#FFF6E8", "muted": "#E3D2C2",
                 "accent": "#E2711D", "accent2": "#A8410A", "accent_ink": "#1A0E06",
                 "price": "#FFC94A", "card": "#1D1411", "card2": "#261A15", "rule": "#4A3428"},
        "light_bg": ["#FFF8EE", "#FFFDF8", "#F3E4CE", "paper-warm"],
        "dark_bg": ["#120C0A", "linen", "50% 0%", "#E2711D2E"],
    },
    "fast_food": {
        "industry": "fast_food", "brand": "Burger Station",
        "display": "Archivo Black", "body": "Manrope", "mood": "fast-casual",
        "light": {"bg": "#FAF7F2", "bg2": "#F0E8DC", "ink": "#141110", "muted": "#6B625B",
                  "accent": "#E23E2C", "accent2": "#B32619", "accent_ink": "#FFFFFF",
                  "price": "#141110", "card": "#FFFFFF", "card2": "#F4EFE8", "rule": "#DED5C9"},
        "dark": {"bg": "#141210", "bg2": "#221D19", "ink": "#FFFDF7", "muted": "#C9BCAE",
                 "accent": "#FFC400", "accent2": "#E0102A", "accent_ink": "#1A1110",
                 "price": "#FFC400", "card": "#221D19", "card2": "#2E2721", "rule": "#4A4038"},
        "light_bg": ["#FAF7F2", "#FFFFFF", "#F0E8DC", "gloss"],
        "dark_bg": ["#141210", "tile", "50% 2%", "#FFC40033"],
    },
    "restaurant": {
        "industry": "restaurant", "brand": "Casa Aurora",
        "display": "Cormorant Garamond", "body": "Manrope", "mood": "fine-dining",
        "light": {"bg": "#FBF9F4", "bg2": "#F0EAE0", "ink": "#1A1C22", "muted": "#6D6A63",
                  "accent": "#9C7B26", "accent2": "#6B5214", "accent_ink": "#FFFFFF",
                  "price": "#1A1C22", "card": "#FFFFFF", "card2": "#F6F2EA", "rule": "#DDD5C6"},
        "dark": {"bg": "#07090C", "bg2": "#0E1116", "ink": "#F6F1E7", "muted": "#A79C8C",
                 "accent": "#C9A227", "accent2": "#8A6D12", "accent_ink": "#0B0E12",
                 "price": "#E8D7A8", "card": "#0E1116", "card2": "#141922", "rule": "#2E2A22"},
        "light_bg": ["#FBF9F4", "#FFFFFF", "#EFE8DC", "linen"],
        "dark_bg": ["#07090C", "linen", "16% 12%", "#C9A22721"],
    },
    "latin_honduras": {
        "industry": "latin_honduras", "brand": "Comedor La Catracha",
        "display": "Fraunces", "body": "Nunito", "mood": "comedor-catracho",
        "light": {"bg": "#FFF9EC", "bg2": "#F6E9CE", "ink": "#23160E", "muted": "#6D5748",
                  "accent": "#0E7C86", "accent2": "#0A5A61", "accent_ink": "#FFFFFF",
                  "price": "#B42318", "card": "#FFFFFF", "card2": "#FFF3DE", "rule": "#E0C9A8"},
        "dark": {"bg": "#1B1108", "bg2": "#2A1C10", "ink": "#FFF3DE", "muted": "#D3BCA4",
                 "accent": "#12A3A3", "accent2": "#0A6C6C", "accent_ink": "#10201F",
                 "price": "#FFC94A", "card": "#2A1C10", "card2": "#352415", "rule": "#5A4228"},
        "light_bg": ["#FFF9EC", "#FFFDF6", "#F4E4C6", "paper-warm"],
        "dark_bg": ["#1B1108", "linen", "50% 0%", "#12A3A32E"],
    },
    "latin_salvador": {
        "industry": "latin_salvador", "brand": "Pupusería Doña Tere",
        "display": "Oswald", "body": "Nunito", "mood": "pupuseria-comal",
        "light": {"bg": "#FAF8F2", "bg2": "#EDE7DA", "ink": "#15202E", "muted": "#5F6A78",
                  "accent": "#2447A8", "accent2": "#14295F", "accent_ink": "#FFFFFF",
                  "price": "#B57A00", "card": "#FFFFFF", "card2": "#F3F6FC", "rule": "#D5DCE6"},
        "dark": {"bg": "#13100F", "bg2": "#1E1917", "ink": "#FFF3DC", "muted": "#CBB9A4",
                 "accent": "#F2B705", "accent2": "#C08C00", "accent_ink": "#1A1406",
                 "price": "#F2B705", "card": "#1E1917", "card2": "#28211E", "rule": "#4A3F3A"},
        "light_bg": ["#FAF8F2", "#FFFFFF", "#EAE2D3", "linen"],
        "dark_bg": ["#13100F", "chalk", "50% 2%", "#F2B70526"],
    },
    "latin_panama": {
        "industry": "latin_panama", "brand": "Fonda El Istmo",
        "display": "Baloo 2", "body": "Manrope", "mood": "fonda-tropical",
        "light": {"bg": "#FFFBF2", "bg2": "#F1E8D8", "ink": "#10243F", "muted": "#5B6B7C",
                  "accent": "#C2263F", "accent2": "#0B3DA0", "accent_ink": "#FFFFFF",
                  "price": "#0B3DA0", "card": "#FFFFFF", "card2": "#F4F8FF", "rule": "#D3DEEC"},
        "dark": {"bg": "#08203C", "bg2": "#0E2E53", "ink": "#FFFDF6", "muted": "#B7CBE2",
                 "accent": "#E8536B", "accent2": "#8E0A22", "accent_ink": "#1A0508",
                 "price": "#FFD34E", "card": "#0E2E53", "card2": "#143A66", "rule": "#2D577F"},
        "light_bg": ["#FFFBF2", "#FFFFFF", "#EFE5D2", "tile"],
        "dark_bg": ["#08203C", "tile", "50% 100%", "#E8536B26"],
    },
    "latin_venezuela": {
        "industry": "latin_venezuela", "brand": "Arepera La Esquina",
        "display": "Baloo 2", "body": "Nunito", "mood": "latino-sereno",
        "light": {"bg": "#FBF6EC", "bg2": "#F2E7D3", "ink": "#22303D", "muted": "#6E7B8A",
                  "accent": "#C4703A", "accent2": "#2F5D8A", "accent_ink": "#FFFFFF",
                  "price": "#2F5D8A", "card": "#FFFFFF", "card2": "#F7F1E5", "rule": "#DCCFB8"},
        "dark": {"bg": "#120E08", "bg2": "#1F1810", "ink": "#FFF8E1", "muted": "#D6C5A6",
                 "accent": "#F0B429", "accent2": "#B88A00", "accent_ink": "#1A1406",
                 "price": "#F0B429", "card": "#1F1810", "card2": "#291F15", "rule": "#4E3D26"},
        "light_bg": ["#FBF6EC", "#FFFDF8", "#F1E6D2", "linen"],
        "dark_bg": ["#120E08", "chalk", "50% 0%", "#F0B42926"],
    },
    "mexican": {
        "industry": "mexican", "brand": "Taquería El Güero",
        "display": "Baloo 2", "body": "Nunito", "mood": "taqueria",
        "light": {"bg": "#FDF8EF", "bg2": "#F0E6D5", "ink": "#1B2A20", "muted": "#5F6E62",
                  "accent": "#D2552B", "accent2": "#A62F16", "accent_ink": "#FFFFFF",
                  "price": "#1B5E3A", "card": "#FFFFFF", "card2": "#F5F1E6", "rule": "#DCD2BE"},
        "dark": {"bg": "#0E2B1B", "bg2": "#15412A", "ink": "#FFF6E0", "muted": "#C3D6C2",
                 "accent": "#F2A03E", "accent2": "#A62F16", "accent_ink": "#20130A",
                 "price": "#F2C14E", "card": "#15412A", "card2": "#1C5033", "rule": "#37694A"},
        "light_bg": ["#FDF8EF", "#FFFFFF", "#EFE4D0", "tile"],
        "dark_bg": ["#0E2B1B", "tile", "50% 0%", "#F2A03E24"],
    },
    "ice_cream": {
        "industry": "ice_cream", "brand": "Heladería Frescura",
        "display": "Baloo 2", "body": "Nunito", "mood": "heladeria",
        "light": {"bg": "#FFF9FB", "bg2": "#FBEAF2", "ink": "#2A1430", "muted": "#7A5C74",
                  "accent": "#E8468C", "accent2": "#B92A6A", "accent_ink": "#FFFFFF",
                  "price": "#6B3FC0", "card": "#FFFFFF", "card2": "#FFF2F8", "rule": "#F1CFE0"},
        "dark": {"bg": "#140E1E", "bg2": "#1F1630", "ink": "#FFF3FA", "muted": "#C9B4DA",
                 "accent": "#FF6FB5", "accent2": "#8B5CF6", "accent_ink": "#190D22",
                 "price": "#63E6E2", "card": "#1F1630", "card2": "#291C3D", "rule": "#4A3763"},
        "light_bg": ["#FFF9FB", "#FFFFFF", "#FBE7F1", "gloss"],
        "dark_bg": ["#140E1E", "gloss", "50% 4%", "#FF6FB52E"],
    },
    "seafood": {
        "industry": "seafood", "brand": "Marisquería El Faro",
        "display": "Fraunces", "body": "Manrope", "mood": "marisqueria",
        "light": {"bg": "#F7FBFD", "bg2": "#E7F1F6", "ink": "#0C2432", "muted": "#5A7484",
                  "accent": "#0E7C99", "accent2": "#095A70", "accent_ink": "#FFFFFF",
                  "price": "#B4740A", "card": "#FFFFFF", "card2": "#F1F7FA", "rule": "#CFE0E8"},
        "dark": {"bg": "#04121D", "bg2": "#0A2233", "ink": "#EFFAFF", "muted": "#9DBACC",
                 "accent": "#FFD166", "accent2": "#C79A2E", "accent_ink": "#12200C",
                 "price": "#FFD166", "card": "#0A2233", "card2": "#0E2C42", "rule": "#265068"},
        "light_bg": ["#F7FBFD", "#FFFFFF", "#E5EFF5", "linen"],
        "dark_bg": ["#04121D", "linen", "50% 2%", "#FFD16626"],
    },
    "tires": {
        "industry": "tires", "brand": "Llantera El Camino",
        "display": "Oswald", "body": "Manrope", "mood": "taller",
        "light": {"bg": "#F6F7F8", "bg2": "#E6E9EC", "ink": "#15181C", "muted": "#5C6570",
                  "accent": "#E2A011", "accent2": "#A87100", "accent_ink": "#15181C",
                  "price": "#15181C", "card": "#FFFFFF", "card2": "#EEF1F4", "rule": "#D2D8DE"},
        "dark": {"bg": "#0D0F11", "bg2": "#15181C", "ink": "#F2F5F8", "muted": "#A6B0BA",
                 "accent": "#F2B01E", "accent2": "#B07A00", "accent_ink": "#14100A",
                 "price": "#F2B01E", "card": "#15181C", "card2": "#1D2126", "rule": "#3A4249"},
        "light_bg": ["#F6F7F8", "#FFFFFF", "#E4E8EC", "tile"],
        "dark_bg": ["#0D0F11", "tile", "50% 0%", "#F2B01E24"],
    },
    "pharmacy": {
        "industry": "pharmacy", "brand": "Farmacia San Rafael",
        "display": "Manrope", "body": "Manrope", "mood": "farmacia",
        "light": {"bg": "#F7FCFB", "bg2": "#E8F4F2", "ink": "#0F2A28", "muted": "#5A7472",
                  "accent": "#0E9384", "accent2": "#07695F", "accent_ink": "#FFFFFF",
                  "price": "#0F2A28", "card": "#FFFFFF", "card2": "#F0F8F7", "rule": "#D0E4E1"},
        "dark": {"bg": "#04140F", "bg2": "#0A2119", "ink": "#EFFBF7", "muted": "#A2C4BC",
                 "accent": "#32D5AE", "accent2": "#0E9384", "accent_ink": "#04140F",
                 "price": "#32D5AE", "card": "#0A2119", "card2": "#0F2C22", "rule": "#25514A"},
        "light_bg": ["#F7FCFB", "#FFFFFF", "#E6F3F1", "linen"],
        "dark_bg": ["#04140F", "linen", "50% 2%", "#32D5AE24"],
    },
}

PLAN = {  # qué familias recibe cada rubro y con qué nombre de archivo
    "pizzeria": ["a", "b", "v"],
    "fast_food": ["a", "b", "c", "v"],
    "restaurant": ["b", "a", "c"],
    "latin_honduras": ["a", "b", "v"],
    "latin_salvador": ["a", "b", "v"],
    "latin_panama": ["c", "b", "v"],
    "latin_venezuela": ["a", "b", "c", "v"],
    "mexican": ["a", "b", "v"],
    "ice_cream": ["a", "c", "v"],
    "seafood": ["b", "a"],
    "tires": ["a", "b"],
    "pharmacy": ["a", "c"],
}


def existing_sample(path: Path) -> dict | None:
    """La muestra de contenido ya escrita para ese rubro: no se reinventa."""
    if not path.exists():
        return None
    for template in json.loads(path.read_text()):
        if template.get("sample"):
            return template["sample"]
    return None


def build() -> int:
    written = 0
    for key, families in PLAN.items():
        path = SEED / f"{key}.json"
        sample = existing_sample(path)
        if not sample:
            print(f"  ! {key}: sin muestra de contenido, se saltea")
            continue
        rubro = RUBROS[key]
        out = []
        for order, family in enumerate(families):
            shape = FAMILIES[family]()
            label, tagline = FAMILY_LABEL[family]
            dark = family == "b"
            palette = rubro["dark" if dark else "light"]
            background = (DARK_BG(rubro["dark_bg"]) if dark
                          else LIGHT_BG(rubro["light_bg"]))
            template = {
                "id": f"{key.replace('_', '-')}-{family}",
                "kind": "menu_board",
                "industry": rubro["industry"],
                "name": f"{rubro['brand'].split()[0]} — {label}",
                "tagline": tagline,
                "canvas": shape["canvas"],
                "safe_zone": shape["safe_zone"],
                "capacity": {"products": 14, "categories": 3},
                "animated": True,
                "theme": {"palette": palette,
                          "fonts": {"display": rubro["display"], "body": rubro["body"]},
                          "mood": rubro["mood"] + ("-noche" if dark else "")},
                "background": background,
                "blocks": shape["blocks"],
                "motion": shape["motion"],
            }
            if order == 0:
                template["sample"] = sample
            else:
                template["sample_from"] = f"{key.replace('_', '-')}-{families[0]}"
            out.append(template)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        written += len(out)
        print(f"  + {path.name}: {len(out)} plantillas ({', '.join(families)})")
    return written


if __name__ == "__main__":
    print(f"{build()} plantillas escritas")
    sys.exit(0)
