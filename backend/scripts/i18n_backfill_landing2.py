"""
Second i18n pass: the long descriptive paragraphs of landing.html that were
still English-only, plus the Spanish-only SaaS CTA links.

Idempotent. Run once:  python scripts/i18n_backfill_landing2.py
"""
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
HTML = WEB / "landing.html"
JS = WEB / "i18n.js"

ENTRIES: dict[str, tuple[str, str]] = {
    "hero.livelbl": ("RESTAURANT · LIVE", "RESTAURANTES · LIVE"),
    "saas.cta2": ("See plans and pricing →", "Ver planes y precios →"),
    "saas.trial2": ("14-day free trial · no card required", "Prueba gratis 14 días · sin tarjeta"),
    "saas.has2": ("Already have an account?", "¿Ya tienes cuenta?"),

    "vs.p": ("Our Ultra Slim LED transforms your storefront window into a dynamic 24/7 advertisement "
             "that attracts more customers and increases sales.",
             "Nuestro LED Ultra Slim convierte tu vidriera en un anuncio dinámico 24/7 que atrae más "
             "clientes y aumenta tus ventas."),
    "srv.sub": ("Professional LED display installation and management for storefronts, churches, and outdoor spaces.",
                "Instalación y administración profesional de pantallas LED para vidrieras, iglesias y exteriores."),
    "srv.d4": ("Beautiful digital menu boards with 8 professional templates. Update prices and items from your phone. "
               "No more printing menus ever again.",
               "Pizarras de menú digitales con 8 plantillas profesionales. Cambia precios y productos desde tu celular. "
               "Nunca más imprimir menús."),
    "proc.d1": ("Select from our marketplace of premium LED displays. Indoor, outdoor, window-facing — we have the "
                "perfect screen for your needs.",
                "Elige entre nuestro catálogo de pantallas LED premium. Interior, exterior o para vidriera — tenemos "
                "la pantalla perfecta para ti."),
    "proc.d2": ("Use our drag-and-drop dashboard to upload images, videos, menus, or widgets. Schedule when and where "
                "your content plays.",
                "Usa nuestro panel de arrastrar y soltar para subir imágenes, videos, menús o widgets. Programa cuándo "
                "y dónde se reproduce tu contenido."),
    "proc.d3": ("Your content goes live instantly. Monitor performance with real-time analytics, proof-of-play reports, "
                "and remote device management.",
                "Tu contenido sale al aire al instante. Monitorea el rendimiento con analítica en tiempo real, reportes "
                "de reproducción y administración remota."),
    "dm.sub": ("Replace static printed menus with stunning digital displays. Update prices instantly. "
               "No reprinting ever again.",
               "Reemplaza los menús impresos por pantallas digitales espectaculares. Cambia precios al instante. "
               "Nunca más reimprimir."),
    "dm.d1": ("Classic, Modern, Fast Food, Mexican, Sushi, Pizza, Bar, Healthy — pick the perfect design for your restaurant.",
              "Clásico, Moderno, Comida Rápida, Mexicano, Sushi, Pizza, Bar, Saludable — elige el diseño perfecto para tu negocio."),
    "dm.d2": ("Change prices from your phone or computer. Updates appear on the screen instantly. No waiting, no reprinting.",
              "Cambia precios desde tu celular o computadora. Los cambios aparecen en la pantalla al instante. Sin esperas, sin reimprimir."),
    "dm.d3": ("Upload mouth-watering photos of your dishes. Add promotional videos that auto-play at the bottom of the menu.",
              "Sube fotos apetitosas de tus platos. Agrega videos promocionales que se reproducen solos al pie del menú."),
    "dm.d4": ("Edit your menu from any device — phone, tablet, or computer. Changes go live in seconds across all your screens.",
              "Edita tu menú desde cualquier dispositivo — celular, tablet o computadora. Los cambios salen en segundos en todas tus pantallas."),
    "dm.d5": ("Show breakfast menu in the morning, lunch at noon, dinner at night. Set it once, it runs automatically.",
              "Muestra el desayuno en la mañana, el almuerzo al mediodía y la cena en la noche. Configúralo una vez y corre solo."),
    "dm.d6": ("Menus with many categories auto-slide every 12 seconds. Your customers see everything without scrolling.",
              "Los menús con muchas categorías rotan solos cada 12 segundos. Tus clientes ven todo sin desplazarse."),
    "pf.c2d": ("Control all your screens remotely. Restart, update, and monitor from anywhere in the world.",
               "Controla todas tus pantallas de forma remota. Reinicia, actualiza y monitorea desde cualquier parte del mundo."),
    "pf.c4d": ("Set automatic on/off schedules. Save energy and extend screen life with smart power management.",
               "Programa el encendido y apagado automático. Ahorra energía y alarga la vida de tus pantallas."),
    "cta.sub": ("Join hundreds of businesses already using MediAd View to attract more customers and increase revenue.",
                "Únete a cientos de negocios que ya usan MediAd View para atraer más clientes y aumentar sus ingresos."),
    "cta.call": ("Call 1-877-202-8181", "Llama al 1-877-202-8181"),
    "ft.about": ("Enterprise-grade digital signage solutions for businesses of all sizes. From LED screens to "
                 "cloud-managed content platforms.",
                 "Soluciones de señalización digital de nivel empresarial para negocios de todos los tamaños. "
                 "Desde pantallas LED hasta plataformas de contenido en la nube."),
}


def main() -> None:
    html = HTML.read_text()
    added = 0
    for key, (en, es) in sorted(ENTRIES.items(), key=lambda kv: -max(len(kv[1][0]), len(kv[1][1]))):
        for text in (en, es):
            needle = f">{text}<"
            pos = html.find(needle)
            while pos != -1:
                tag_start = html.rfind("<", 0, pos)
                tag = html[tag_start:pos + 1]
                if "data-i18n" in tag or tag.startswith("</"):
                    pos = html.find(needle, pos + 1)
                    continue
                new_tag = tag[:-1].rstrip() + f' data-i18n="{key}">'
                html = html[:tag_start] + new_tag + html[pos + 1:]
                added += 1
                pos = html.find(needle, tag_start + len(new_tag))
    HTML.write_text(html)
    print(f"data-i18n attributes added: {added}")

    js = JS.read_text()
    if '"ft.about"' in js:
        print("i18n.js already has pass-2 keys — skipped")
        return
    en_lines = "".join(f'      "{k}": {v[0]!r},\n'.replace("'", '"') for k, v in ENTRIES.items())
    es_lines = "".join(f'      "{k}": {v[1]!r},\n'.replace("'", '"') for k, v in ENTRIES.items())
    js = js.replace('      "lang.toggle": "ES"', en_lines + '      "lang.toggle": "ES"', 1)
    js = js.replace('      "lang.toggle": "EN"', es_lines + '      "lang.toggle": "EN"', 1)
    JS.write_text(js)
    print(f"i18n.js keys added: {len(ENTRIES)} x2")


if __name__ == "__main__":
    main()
