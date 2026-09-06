"""
Relights the legacy admin panel's inline styles (backend/web/app.js) so the content
matches the light design system already used by its shell (styles.css / design-system.css).

The shell was migrated to light long ago but many blocks built in JS still carried
dark surfaces, near-invisible text on white and the old indigo accent. This maps them
onto the MediaView palette: light surfaces + cyan/navy accents.

Only colour literals are rewritten — no markup, no logic.
Run once:  python scripts/relight_admin_panel.py
"""
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
TARGET = WEB / "app.js"

MAP = {
    # dark surfaces -> light surfaces
    "background:#0f172a": "background:#f1f5f9",
    "background:#020617": "background:#e2e8f0",
    "background:#000": "background:#0f172a",   # media lightbox stays dark on purpose
    "#1e293b": "#e2e8f0",                      # only ever used as a border here
    # low-contrast text on white
    "color:#e2e8f0": "color:#0f172a",
    "color:#334155": "color:#64748b",
    "#94a3b8": "#64748b",
    'stroke="#334155"': 'stroke="#94a3b8"',
    # indigo / neon accents -> brand cyan
    "#6366f1": "#0891b2",
    "#818cf8": "#0891b2",
    "#4338ca": "#0e7490",
    "#22d3ee": "#0891b2",
    "#a78bfa": "#0891b2",
    "#c4b5fd": "#67e8f9",
    "99,102,241": "8,145,178",
    "139,92,246": "8,145,178",
    # status colours with enough contrast on white
    "#34d399": "#059669",
    "#f87171": "#dc2626",
    "#fbbf24": "#d97706",
}


def main() -> None:
    if not TARGET.exists():
        print(f"{TARGET} not found")
        sys.exit(1)

    src = TARGET.read_text()
    keys = sorted(MAP, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys), re.IGNORECASE)
    lookup = {k.lower(): v for k, v in MAP.items()}

    hits: dict[str, int] = {}

    def sub(m: re.Match) -> str:
        key = m.group(0).lower()
        hits[key] = hits.get(key, 0) + 1
        return lookup[key]

    out = pattern.sub(sub, src)
    if out == src:
        print("nothing to change")
        return

    TARGET.write_text(out)
    for key in sorted(hits, key=lambda k: -hits[k]):
        print(f"{hits[key]:>3} x {key}")
    print(f"\nrelit {TARGET.relative_to(WEB.parent)}")


if __name__ == "__main__":
    main()
