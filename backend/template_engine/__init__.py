"""template_engine — convierte una plantilla declarativa en HTML de calidad de agencia.

La regla que sostiene todo: una plantilla nueva es un JSON nuevo, no código nuevo.
El motor sabe dibujar un vocabulario cerrado de bloques (`brand`, `category`,
`product_grid`, `product_list`, `hero`, `promo`, `qr`, `text`, `media`, `ticker`)
con tipografía, profundidad y jerarquía visual profesionales. Agregar la
plantilla número 500 es escribir un JSON más.

Cómo llega al TV: el resultado es HTML autocontenido posicionado en pixeles del
lienzo de la plantilla y escalado con un único `transform`. El reproductor
Android ya muestra cualquier ítem `content_type: "widget"` en un WebView, así
que no hace falta tocar el APK — es la misma técnica que ya funciona en los
menús sobre diseño propio.
"""
from __future__ import annotations

import html as html_lib
import json

from .blocks import render_block
from .editor import editor_schema, literal_texts
from .theme import background_css, font_link, palette_vars

__all__ = ["render_design", "editor_schema", "literal_texts"]


def esc(value) -> str:
    return html_lib.escape(str(value if value is not None else ""), quote=True)


def money(value, currency: str = "$") -> str:
    """Precio legible a 6 metros: sin ceros de más pero con centavos si los hay."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return f"{currency}{int(number)}"
    return f"{currency}{number:.2f}"


def _resolve(design: dict, template: dict) -> dict:
    """Tema de la plantilla con los overrides del cliente aplicados.

    Por defecto la composición profesional queda intacta: el cliente reemplaza
    contenido, no posiciones. Sólo si entra al modo avanzado puede pisar
    colores y tipografías puntuales, nunca la geometría.
    """
    theme = json.loads(json.dumps(template.get("theme") or {}))
    for path, value in (design.get("overrides") or {}).items():
        if not path.startswith("theme."):
            continue  # la geometría no se negocia
        node = theme
        parts = path.split(".")[1:]
        for key in parts[:-1]:
            node = node.setdefault(key, {})
        node[parts[-1]] = value
    return theme


def render_design(design: dict, template: dict, products: dict[str, dict]) -> str:
    """HTML completo de un diseño listo para un TV.

    `products` es un índice por id: el diseño guarda referencias, no precios, así
    que cambiar el precio de un producto una vez lo cambia en todas las pantallas
    donde aparece.
    """
    canvas = template.get("canvas") or {}
    width = max(320, int(canvas.get("w") or 1920))
    height = max(240, int(canvas.get("h") or 1080))
    theme = _resolve(design, template)
    safe = int(template.get("safe_zone") or 0)

    blocks = "".join(
        render_block(block, design, theme, products)
        for block in (template.get("blocks") or [])
        if isinstance(block, dict)
    )

    title = esc(design.get("name") or template.get("name") or "MediaView")
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{font_link(theme)}
<style>
:root{{{palette_vars(theme)}}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:#000;overflow:hidden;-webkit-font-smoothing:antialiased}}
#wrap{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}}
#stage{{position:relative;flex:0 0 auto;width:{width}px;height:{height}px;
  transform-origin:center center;overflow:hidden;{background_css(template, theme)}}}
.bg-layer{{position:absolute;inset:0;pointer-events:none}}
.blk{{position:absolute}}
.safe{{position:absolute;inset:{safe}px;pointer-events:none}}
{_BASE_CSS}
</style></head><body>
<div id="wrap"><div id="stage">
{blocks}
</div></div>
<script>
var W={width},H={height};
function fit(){{
  var s=document.getElementById('stage');
  s.style.transform='scale('+Math.min(window.innerWidth/W,window.innerHeight/H)+')';
}}
window.addEventListener('resize',fit);fit();
// El texto del cliente puede ser más largo que el de muestra. Lo encogemos
// hasta que entre, en vez de dejarlo desbordar y romper la composición.
function fitText(){{
  var nodes=document.querySelectorAll('[data-fit]');
  for(var i=0;i<nodes.length;i++){{
    var el=nodes[i],box=el.parentElement,guard=0;
    var bs=window.getComputedStyle(box);
    // Se compara contra la caja de contenido, no contra clientWidth: clientWidth
    // incluye el padding y por eso un ticker con padding se cortaba en el borde.
    var maxW=box.clientWidth-parseFloat(bs.paddingLeft||0)-parseFloat(bs.paddingRight||0);
    var maxH=box.clientHeight-parseFloat(bs.paddingTop||0)-parseFloat(bs.paddingBottom||0);
    var size=parseFloat(window.getComputedStyle(el).fontSize)||16;
    while((el.scrollWidth>maxW+1||el.scrollHeight>maxH+1)
          &&size>9&&guard<140){{
      size-=Math.max(0.5,size*0.035);el.style.fontSize=size+'px';guard++;
    }}
  }}
}}
if(document.fonts&&document.fonts.ready){{document.fonts.ready.then(fitText);}}
else{{window.addEventListener('load',fitText);}}
</script></body></html>"""


# CSS compartido por todos los bloques. Vive acá y no en cada bloque para que
# el espaciado, las sombras y la jerarquía sean consistentes entre plantillas.
_BASE_CSS = """
.brand{display:flex;align-items:center;gap:var(--gap)}
.brand img{height:100%;width:auto;object-fit:contain;filter:drop-shadow(0 4px 12px rgba(0,0,0,.45))}
.brand-name{font-family:var(--f-display);font-weight:900;color:var(--c-ink);
  letter-spacing:-.02em;line-height:.95;text-shadow:var(--sh)}

.cat{display:flex;align-items:center;gap:18px}
/* El título de sección va con el color de texto de la plantilla, NO con el del
   acento: `accent_ink` es el color que va ENCIMA del acento (una promo dorada
   lleva texto oscuro) y usarlo acá dejaba «ENTRADAS» invisible sobre el fondo. */
.cat-label{font-family:var(--f-display);font-weight:900;color:var(--c-ink);
  letter-spacing:.14em;text-transform:uppercase;line-height:1;white-space:nowrap}
.cat-rule{flex:1;height:3px;border-radius:3px;
  background:linear-gradient(90deg,var(--c-accent),transparent)}

.grid{display:grid;height:100%}
.card{position:relative;display:flex;flex-direction:column;overflow:hidden;
  border-radius:var(--radius);background:var(--c-card);
  box-shadow:0 18px 40px -18px rgba(0,0,0,.75),inset 0 1px 0 rgba(255,255,255,.07)}
.card-photo{position:relative;flex:1;min-height:0;overflow:hidden;background:var(--c-card-2)}
.card-photo img{width:100%;height:100%;object-fit:cover;display:block}
.card-photo::after{content:'';position:absolute;inset:0;
  background:linear-gradient(180deg,transparent 45%,rgba(0,0,0,.72) 100%)}
.card-body{padding:var(--pad) var(--pad) calc(var(--pad) * 1.1)}
.card-name{font-family:var(--f-display);font-weight:900;color:var(--c-ink);
  line-height:1.03;letter-spacing:-.01em;overflow:hidden;
  text-shadow:var(--sh)}
/* Legibilidad a distancia: la descripción es secundaria pero tiene que leerse,
   así que sube de peso y de contraste y se corta a dos renglones para que nunca
   le robe altura a la foto ni desborde la tarjeta. */
.card-desc{font-family:var(--f-body);font-weight:500;color:var(--c-muted);
  line-height:1.25;margin-top:.28em;overflow:hidden;display:-webkit-box;
  -webkit-box-orient:vertical;-webkit-line-clamp:2}
.card-price{font-family:var(--f-body);font-weight:900;color:var(--c-price);
  line-height:1;margin-top:.4em;letter-spacing:-.01em;
  text-shadow:var(--sh)}
.variants{display:flex;flex-wrap:wrap;gap:.4em .78em;margin-top:.45em}
.variant{display:flex;align-items:baseline;gap:.28em;font-family:var(--f-body);line-height:1}
.variant b{font-weight:900;color:var(--c-price);text-shadow:var(--sh)}
.variant span{font-weight:800;color:var(--c-ink);opacity:.72;
  text-transform:uppercase;letter-spacing:.06em}
.badge{position:absolute;top:var(--pad);left:var(--pad);z-index:2;
  padding:.3em .7em;border-radius:999px;background:var(--c-accent);color:var(--c-accent-ink);
  font-family:var(--f-body);font-weight:900;text-transform:uppercase;letter-spacing:.1em;
  box-shadow:0 8px 20px -6px rgba(0,0,0,.6)}
.sold{position:absolute;inset:0;z-index:3;display:flex;align-items:center;justify-content:center;
  background:rgba(8,6,6,.68);color:var(--c-ink);font-family:var(--f-display);font-weight:900;
  text-transform:uppercase;letter-spacing:.18em}

.list{display:flex;flex-direction:column;height:100%}
.row{display:flex;align-items:baseline;gap:.6em;flex:1;min-height:0}
.row-name{font-family:var(--f-body);font-weight:800;color:var(--c-ink);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;text-shadow:var(--sh)}
.row-dots{flex:1;border-bottom:3px dotted var(--c-rule);transform:translateY(-.22em)}
.row-price{font-family:var(--f-body);font-weight:900;color:var(--c-price);white-space:nowrap;
  text-shadow:var(--sh)}
.row-thumb{width:1.9em;height:1.9em;border-radius:10px;object-fit:cover;flex:0 0 auto;
  align-self:center;box-shadow:0 6px 14px -6px rgba(0,0,0,.7)}

/* Sin `position:relative` a propósito: estos bloques ya son `.blk` (absolutos).
   Si se lo ponen acá, `position` sobrescribe al de `.blk` por orden de cascada,
   el bloque vuelve al flujo y empuja a los que vienen después — así se perdía
   la promo del tótem vertical debajo del hero. */
.hero{display:flex;height:100%;overflow:hidden;border-radius:var(--radius)}
.hero img,.hero video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.hero::after{content:'';position:absolute;inset:0;
  background:linear-gradient(105deg,rgba(0,0,0,.86) 0%,rgba(0,0,0,.42) 52%,transparent 100%)}
.hero-body{position:relative;z-index:2;align-self:flex-end;padding:calc(var(--pad) * 2)}
.hero-kicker{font-family:var(--f-body);font-weight:900;color:var(--c-accent);
  text-transform:uppercase;letter-spacing:.2em;margin-bottom:.5em}
.hero-name{font-family:var(--f-display);font-weight:900;color:var(--c-photo-ink);line-height:.98;
  letter-spacing:-.02em;text-shadow:0 4px 30px rgba(0,0,0,.65)}
.hero-price{font-family:var(--f-body);font-weight:900;color:var(--c-photo-price);line-height:1;
  margin-top:.3em}

.promo{display:flex;flex-direction:column;justify-content:center;
  height:100%;padding:calc(var(--pad) * 1.5);border-radius:var(--radius);overflow:hidden;
  background:linear-gradient(135deg,var(--c-accent) 0%,var(--c-accent-2) 100%);
  box-shadow:0 24px 50px -20px rgba(0,0,0,.8)}
.promo::before{content:'';position:absolute;inset:-40% -10% auto auto;width:70%;height:180%;
  background:radial-gradient(circle,rgba(255,255,255,.22),transparent 65%)}
/* ── Composición sin recuadros ──────────────────────────────────────────────
   El producto estrella no vive en una tarjeta: la foto se recorta en círculo,
   se apoya en el fondo con sombra y el precio va en un disco girado. */
.feat{display:flex;align-items:center;gap:calc(var(--pad) * 1.8)}
.feat-right{flex-direction:row-reverse}
.feat-photo{position:relative;flex:0 0 44%;aspect-ratio:1}
.feat-photo img{width:100%;height:100%;object-fit:cover;display:block;border-radius:50%;
  box-shadow:0 34px 90px rgba(0,0,0,.45),0 0 0 10px rgba(255,255,255,.07)}
.feat-copy{flex:1;min-width:0}
.feat-kicker{font-family:var(--f-body);font-weight:900;color:var(--c-accent);
  text-transform:uppercase;letter-spacing:.22em;margin-bottom:.5em}
.feat-name{font-family:var(--f-display);font-weight:900;color:var(--c-ink);
  line-height:.96;letter-spacing:-.02em;text-shadow:var(--sh)}
.feat-desc{font-family:var(--f-body);font-weight:500;color:var(--c-muted);
  line-height:1.3;margin-top:.5em;max-width:22em}
.disc{position:absolute;right:-.5em;bottom:.3em;display:flex;align-items:center;justify-content:center;
  width:2.9em;height:2.9em;border-radius:50%;background:var(--c-accent);
  color:var(--c-accent-ink);font-family:var(--f-body);font-weight:900;
  transform:rotate(-9deg);box-shadow:0 20px 46px rgba(0,0,0,.45);z-index:3}
/* La tarjeta «desnuda»: foto redonda y texto centrado, sin caja. */
.card-bare{background:none;box-shadow:none;border:0;align-items:center;text-align:center}
.card-bare .card-name{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:1}
.card-bare .card-photo{flex:0 0 auto;height:58%;width:auto;aspect-ratio:1;border-radius:50%;
  align-self:center;box-shadow:0 18px 40px rgba(0,0,0,.38)}
.card-bare .badge,.card-bare .card-photo::after{display:none}
.card-bare .card-body{padding:calc(var(--pad) * .7) 0 0;align-items:center;text-align:center}
.card-bare .variants{justify-content:center}
/* Fotografía de fondo: se disuelve hacia el lado del texto. */
.back{overflow:hidden}
.back img{width:100%;height:100%;object-fit:cover;display:block;filter:saturate(1.06) contrast(1.04)}
.back-right img{-webkit-mask-image:linear-gradient(90deg,#000 38%,transparent 100%);
  mask-image:linear-gradient(90deg,#000 38%,transparent 100%)}
.back-left img{-webkit-mask-image:linear-gradient(270deg,#000 38%,transparent 100%);
  mask-image:linear-gradient(270deg,#000 38%,transparent 100%)}
.back-bottom img{-webkit-mask-image:linear-gradient(180deg,#000 34%,transparent 100%);
  mask-image:linear-gradient(180deg,#000 34%,transparent 100%)}
.back-top img{-webkit-mask-image:linear-gradient(0deg,#000 34%,transparent 100%);
  mask-image:linear-gradient(0deg,#000 34%,transparent 100%)}

.promo-kicker{position:relative;font-family:var(--f-body);font-weight:900;
  color:var(--c-accent-ink);opacity:.85;text-transform:uppercase;letter-spacing:.2em}
.promo-copy{position:relative;min-width:0}
.promo-wide{flex-direction:row;align-items:center;gap:calc(var(--pad) * 1.5)}
.promo-wide .promo-copy{flex:1}
.promo-wide .promo-price{margin-top:0;white-space:nowrap}
.promo-title{position:relative;font-family:var(--f-display);font-weight:900;
  color:var(--c-accent-ink);line-height:1;margin-top:.25em;letter-spacing:-.02em}
.promo-price{position:relative;font-family:var(--f-body);font-weight:900;
  color:var(--c-accent-ink);line-height:1;margin-top:.2em}

.qr{display:flex;flex-direction:column;align-items:center;gap:.4em;height:100%}
.qr img{flex:1;min-height:0;aspect-ratio:1;background:#fff;padding:6px;border-radius:12px}
.qr-label{font-family:var(--f-body);font-weight:700;color:var(--c-muted);
  text-transform:uppercase;letter-spacing:.12em}

.txt{font-family:var(--f-body);color:var(--c-ink);overflow:hidden}
.media img,.media video{width:100%;height:100%;object-fit:cover;border-radius:var(--radius)}

@keyframes mv-fade{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes mv-pop{0%{transform:scale(.82);opacity:0}70%{transform:scale(1.04)}100%{transform:scale(1);opacity:1}}
@keyframes mv-ken{from{transform:scale(1)}to{transform:scale(1.09)}}
.anim-fade{animation:mv-fade .7s both cubic-bezier(.2,.7,.3,1)}
.anim-pop{animation:mv-pop .6s both cubic-bezier(.2,.9,.3,1)}
.anim-ken img{animation:mv-ken 18s ease-in-out infinite alternate}
"""
