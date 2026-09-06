"""
Adds bilingual (data-i18n) coverage to the legacy sections of landing.html that
were still English-only (or Spanish-only), and appends the matching keys to i18n.js.

Idempotent: skips any element that already carries data-i18n.
Run once:  python scripts/i18n_backfill_landing.py
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
HTML = WEB / "landing.html"
JS = WEB / "i18n.js"

# key -> (english, spanish)   ... source text in the HTML may be either one.
ENTRIES: dict[str, tuple[str, str]] = {
    # SaaS CTA card (currently Spanish-only)
    "saas.badge": ("For Restaurants · Retail · Business", "Para Restaurantes · Retail · Negocios"),
    "saas.t1": ("Your digital menu on any TV.", "Tu menú digital en cualquier TV."),
    "saas.t2": ("In minutes. From $0.", "En minutos. Desde $0."),
    "saas.p1": ("Connect your screen, upload your menu, schedule your content.",
                "Conecta tu pantalla, sube tu menú, programa el contenido."),
    "saas.p2": ("No special hardware. No technicians. No contracts.",
                "Sin hardware especial. Sin técnicos. Sin contratos."),
    "saas.cta": ("See plans and pricing →", "Ver planes y precios →"),
    "saas.trial": ("14-day free trial · no card required", "Prueba gratis 14 días · sin tarjeta"),
    "saas.has": ("Already have an account?", "¿Ya tienes cuenta?"),
    "saas.login": ("Log in →", "Inicia sesión →"),
    # stats
    "stat.screens": ("Screens Installed", "Pantallas Instaladas"),
    "stat.churches": ("Churches Served", "Iglesias Atendidas"),
    "stat.trust": ("Businesses Trust Us", "Negocios Confían en Nosotros"),
    "stat.uptime": ("Uptime Guarantee", "Uptime Garantizado"),
    # video showcase
    "vs.badge": ("See The Difference", "Mira La Diferencia"),
    "vs.title": ("Why Digital Beats Paper", "Por Qué lo Digital Supera al Papel"),
    "vs.b1": ("Higher brightness than any printed poster", "Más brillo que cualquier cartel impreso"),
    "vs.b2": ("Animated content that catches every eye", "Contenido animado que atrapa todas las miradas"),
    "vs.b3": ("Update content instantly from your phone", "Actualiza el contenido al instante desde tu celular"),
    "vs.b4": ("No more printing costs — ever", "Nunca más gastos de impresión"),
    "vs.cta": ("Get a Free Quote →", "Pide una Cotización Gratis →"),
    # services
    "srv.badge": ("Our Specialties", "Nuestras Especialidades"),
    "srv.title": ("What We Do Best", "Lo Que Hacemos Mejor"),
    "srv.s1": ("Storefront Window Displays", "Pantallas para Vidrieras"),
    "srv.s2": ("Church LED Screens", "Pantallas LED para Iglesias"),
    "srv.s3": ("Outdoor Wall Displays", "Pantallas Exteriores de Pared"),
    "srv.s4": ("Digital Restaurant Menus", "Menús Digitales para Restaurantes"),
    # managed LED process steps
    "proc.p1": ("Choose Your Screen", "Elige Tu Pantalla"),
    "proc.p2": ("Upload Your Content", "Sube Tu Contenido"),
    "proc.p3": ("Go Live & Track Results", "Sal al Aire y Mide Resultados"),
    # digital menus feature list
    "dm.badge": ("For Restaurants", "Para Restaurantes"),
    "dm.title": ("Digital Menus That Drive Sales", "Menús Digitales Que Venden Más"),
    "dm.f1": ("8 Professional Templates", "8 Plantillas Profesionales"),
    "dm.f2": ("Real-Time Price Updates", "Cambios de Precio en Tiempo Real"),
    "dm.f3": ("Photos & Promo Videos", "Fotos y Videos Promocionales"),
    "dm.f4": ("Manage From Anywhere", "Administra Desde Donde Sea"),
    "dm.f5": ("Scheduled Content", "Contenido Programado"),
    "dm.f6": ("Auto-Rotating Slides", "Slides que Rotan Solos"),
    # platform
    "pf.badge": ("Cloud Platform", "Plataforma en la Nube"),
    "pf.title": ("Powerful Management Dashboard", "Panel de Administración Potente"),
    "pf.sub": ("Everything you need to manage your digital signage network from a single interface.",
               "Todo lo que necesitas para administrar tu red de pantallas desde una sola interfaz."),
    "pf.c1": ("Real-Time Analytics", "Analítica en Tiempo Real"),
    "pf.c1d": ("Track impressions, proof-of-play, and campaign performance with detailed reports.",
               "Mide impresiones, prueba de reproducción y rendimiento de campañas con reportes detallados."),
    "pf.c2": ("Remote Management", "Administración Remota"),
    "pf.c3": ("Smart Scheduling", "Programación Inteligente"),
    "pf.c3d": ("Schedule content by date, time, and day of week. Automate your entire content calendar.",
               "Programa contenido por fecha, hora y día de la semana. Automatiza todo tu calendario."),
    "pf.c4": ("Power Control", "Control de Encendido"),
    "pf.c5": ("Secure & Reliable", "Seguro y Confiable"),
    "pf.c5d": ("99.9% uptime with automatic crash recovery. Your content never stops playing.",
               "99.9% de uptime con recuperación automática. Tu contenido nunca deja de reproducirse."),
    "pf.c6": ("Multi-User Access", "Acceso Multiusuario"),
    "pf.c6d": ("Admin, manager, and customer roles. Give your team the access they need, nothing more.",
               "Roles de admin, gerente y cliente. Dale a tu equipo solo el acceso que necesita."),
    # final CTA
    "cta.badge": ("Get Started Today", "Empieza Hoy"),
    "cta.title": ("Ready to Go Digital?", "¿Listo para Digitalizarte?"),
    "cta.free": ("Free", "Gratis"),
    "cta.consult": ("Consultation", "Consulta"),
    "cta.support": ("Support", "Soporte"),
    "cta.custom": ("Custom", "A Medida"),
    "cta.solutions": ("Solutions", "Soluciones"),
    # footer
    "ft.services": ("Services", "Servicios"),
    "ft.window": ("Window Displays", "Pantallas para Vidrieras"),
    "ft.church": ("Church Screens", "Pantallas para Iglesias"),
    "ft.outdoor": ("Outdoor Displays", "Pantallas Exteriores"),
    "ft.menus": ("Restaurant Menus", "Menús para Restaurantes"),
    "ft.platform": ("Cloud Platform", "Plataforma en la Nube"),
    "ft.company": ("Company", "Empresa"),
    "ft.how": ("How It Works", "Cómo Funciona"),
    "ft.plat": ("Platform", "Plataforma"),
    "ft.contactus": ("Contact Us", "Contáctanos"),
    "ft.dash": ("Dashboard Login", "Ingresar al Panel"),
    "ft.contact": ("Contact", "Contacto"),
    "ft.rights": ("© 2026 MediAd View LLC. All rights reserved.",
                  "© 2026 MediAd View LLC. Todos los derechos reservados."),
    "ft.tag": ("Digital Signage & LED Advertising Solutions",
               "Soluciones de Señalización Digital y Publicidad LED"),
}


def add_attrs(html: str) -> tuple[str, int]:
    added = 0
    # longest first so "Cloud Platform" inside a longer phrase isn't matched wrongly
    ordered = sorted(ENTRIES.items(), key=lambda kv: -max(len(kv[1][0]), len(kv[1][1])))
    for key, (en, es) in ordered:
        for text in (en, es):
            idx = 0
            while True:
                needle = f">{text}<"
                pos = html.find(needle, idx)
                if pos == -1:
                    break
                idx = pos + 1
                tag_start = html.rfind("<", 0, pos)
                tag = html[tag_start:pos + 1]
                if "data-i18n" in tag or tag.startswith("</"):
                    continue
                # insert the attribute right before the closing '>' of the opening tag
                new_tag = tag[:-1].rstrip() + f' data-i18n="{key}">'
                html = html[:tag_start] + new_tag + html[pos + 1:]
                added += 1
                idx = tag_start + len(new_tag)
    return html, added


def add_keys(js: str) -> str:
    en_lines = "".join(f'      "{k}": {v[0]!r},\n'.replace("'", '"') for k, v in ENTRIES.items())
    es_lines = "".join(f'      "{k}": {v[1]!r},\n'.replace("'", '"') for k, v in ENTRIES.items())
    js = js.replace('      "lang.toggle": "ES"', en_lines + '      "lang.toggle": "ES"', 1)
    js = js.replace('      "lang.toggle": "EN"', es_lines + '      "lang.toggle": "EN"', 1)
    return js


def main() -> None:
    html = HTML.read_text()
    html, added = add_attrs(html)
    HTML.write_text(html)
    print(f"data-i18n attributes added: {added}")

    js = JS.read_text()
    if '"ft.rights"' in js:
        print("i18n.js already contains the backfilled keys — skipped")
    else:
        JS.write_text(add_keys(js))
        print(f"i18n.js keys added: {len(ENTRIES)} x2")


if __name__ == "__main__":
    main()
