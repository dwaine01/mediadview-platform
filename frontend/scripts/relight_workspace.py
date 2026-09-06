"""
One-shot color migration: MediaView Customer Workspace from the old dark/indigo
palette to the official light Cyan + Navy brand palette.

Only style *values* are rewritten — no logic, no JSX structure, no props.
Run:  python scripts/relight_workspace.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# dark value  ->  light brand value
MAP = {
    # surfaces
    "#0B0F1A": "#F8FAFC",   # app background
    "#111827": "#FFFFFF",   # card
    "#0F172A": "#FFFFFF",   # sidebar / elevated
    "#1F2937": "#F1F5F9",   # elevated
    "#1A2234": "#F1F5F9",
    "#1C1917": "#F8FAFC",
    # borders
    "#1E293B": "#E2E8F0",
    "#374151": "#CBD5E1",
    "#4B5563": "#94A3B8",
    # text
    "#F1F5F9": "#0F172A",   # primary text
    "#E2E8F0": "#1E293B",
    "#D1D5DB": "#334155",
    "#9CA3AF": "#64748B",
    "#6B7280": "#64748B",
    "#94A3B8": "#64748B",
    "#334155": "#0F172A",
    # brand: indigo -> cyan
    "#6366F1": "#0891B2",
    "#818CF8": "#0891B2",
    "#4F46E5": "#0E7490",
    "#312E81": "#CFFAFE",
    "#1E1B4B": "#ECFEFF",
    "#22D3EE": "#06B6D4",
    # status greens
    "#34D399": "#059669",
    "#064E3B": "#D1FAE5",
    "#0C4A22": "#D1FAE5",
    # status reds
    "#F87171": "#DC2626",
    "#1C1115": "#FEF2F2",
    "#7F1D1D": "#FECACA",
    # status amber
    "#F59E0B": "#D97706",
    "#FB923C": "#EA580C",
    "#431407": "#FFEDD5",
    # info blues -> cyan family
    "#60A5FA": "#0891B2",
    "#93C5FD": "#0E7490",
    "#1E3A5F": "#ECFEFF",
    "#1E40AF": "#A5F3FC",
    # rgba
    "rgba(99,102,241,0.12)": "rgba(6,182,212,0.10)",
    "rgba(0,0,0,0.7)": "rgba(15,23,42,0.45)",
}


def main() -> None:
    targets = sorted(ROOT.glob("app/workspace/*.tsx"))
    if not targets:
        print("no workspace files found")
        sys.exit(1)

    # single-pass simultaneous replacement so mappings never cascade
    keys = sorted(MAP, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys), re.IGNORECASE)
    lookup = {k.upper(): v for k, v in MAP.items()}

    for path in targets:
        src = path.read_text()
        out = pattern.sub(lambda m: lookup[m.group(0).upper()], src)
        if out != src:
            path.write_text(out)
            print(f"relit {path.relative_to(ROOT)}")
        else:
            print(f"unchanged {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
