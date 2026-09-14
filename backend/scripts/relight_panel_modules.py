"""Aclara los módulos del panel de administración (backend/web/*.js).

El shell del panel es CLARO (styles.css / design-system.css) desde hace tiempo,
pero varios módulos que arman su HTML en JavaScript quedaron con el tema oscuro
viejo: tarjetas `#111827`, bordes `#1f2937`, texto `#f3f4f6`/`#d1d5db`/`#9ca3af`
y el acento índigo/neón. Sobre blanco eso se ve «apagado» o directamente
ilegible, y mezclado con las páginas claras se ve mal combinado.

Sólo se reescriben literales de color: nada de markup ni de lógica. Los scrims
de los modales (`rgba(...)`), el visor de PDF (`#525659`) y el lightbox
(`background:#000`) se dejan oscuros a propósito.

Idempotente. Uso:  python scripts/relight_panel_modules.py [archivo.js ...]
"""
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

# Los módulos que carga index.html (el panel). app.js ya se aclaró antes con
# relight_admin_panel.py; se incluye igual porque el mapa es idempotente.
PANEL_MODULES = [
    "app.js", "playlists.js", "finance.js", "finance-extras.js",
    "admin-custorders.js", "admin-signpermits.js", "corporate-portal.js",
    "self-service.js", "advertising.js", "managed-portal.js",
    "signup.js", "workspace.js", "crm-admin.js",
]

MAP = {
    # ---- superficies oscuras -> superficies claras -------------------------
    "background:#111827": "background:#ffffff",
    "background:#0f172a": "background:#f1f5f9",
    "background:#020617": "background:#e2e8f0",
    "background:#0d1420": "background:#f1f5f9",
    "background:#0b1220": "background:#f1f5f9",
    "background:#0f0900": "background:#fffbeb",
    "background:#1f2937": "background:#f1f5f9",
    "background:#450a0a": "background:#fef2f2",
    "background:#064e3b": "background:#ecfdf5",
    "background:#78350f": "background:#fffbeb",
    # cajas de error/éxito y sus bordes
    "#7f1d1d": "#fecaca",
    "#065f46": "#a7f3d0",
    # bordes oscuros
    "#1e293b": "#e2e8f0",
    "#1f2937": "#e2e8f0",
    "#374151": "#cbd5e1",
    "#1a2234": "#e2e8f0",
    # ---- texto de bajo contraste sobre blanco -----------------------------
    "color:#f3f4f6": "color:#0f172a",
    "color:#f9fafb": "color:#0f172a",
    "color:#e2e8f0": "color:#0f172a",
    "color:#e5e7eb": "color:#0f172a",
    "color:#d1d5db": "color:#334155",
    "color:#cbd5e1": "color:#475569",
    "color:#9ca3af": "color:#64748b",
    "color:#334155": "color:#475569",
    "#94a3b8": "#64748b",
    'stroke="#334155"': 'stroke="#94a3b8"',
    # ---- índigo / neón -> cian de marca ------------------------------------
    "#6366f1": "#0891b2",
    "#818cf8": "#0891b2",
    "#a5b4fc": "#4338ca",
    "#4f46e5": "#0e7490",
    "#4338ca": "#0e7490",
    "#22d3ee": "#0891b2",
    "#a78bfa": "#0891b2",
    "#7c3aed": "#0e7490",
    "#c4b5fd": "#67e8f9",
    "99,102,241": "8,145,178",
    "139,92,246": "8,145,178",
    # ---- estados con contraste suficiente sobre blanco --------------------
    "#34d399": "#059669",
    "color:#10b981": "color:#047857",
    "#f87171": "#dc2626",
    "#fca5a5": "#dc2626",
    "#fbbf24": "#d97706",
    "#fcd34d": "#b45309",
    "#f59e0b": "#b45309",
    "color:#60a5fa": "color:#1d4ed8",
    "color:#93c5fd": "color:#1d4ed8",
}


def relight(path: Path) -> dict[str, int]:
    src = path.read_text()
    keys = sorted(MAP, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys), re.IGNORECASE)
    lookup = {k.lower(): v for k, v in MAP.items()}
    hits: dict[str, int] = {}

    def sub(m: re.Match) -> str:
        key = m.group(0).lower()
        hits[key] = hits.get(key, 0) + 1
        return lookup[key]

    out = pattern.sub(sub, src)
    if out != src:
        path.write_text(out)
    return hits


def main() -> None:
    targets = sys.argv[1:] or PANEL_MODULES
    total = 0
    for name in targets:
        path = WEB / name
        if not path.exists():
            print(f"  ?  {name} no existe")
            continue
        hits = relight(path)
        n = sum(hits.values())
        total += n
        print(f"{n:>4} cambios · {name}")
    print(f"\n{total} literales de color aclarados")


if __name__ == "__main__":
    main()
