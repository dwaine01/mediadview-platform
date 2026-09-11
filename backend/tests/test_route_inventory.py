"""Fase 2A safety net (see docs/REFACTOR_FASE2_PLAN.md): freezes the exact
set of routes MediaView exposes - method(s) + resolved path + route kind -
as they exist on `trunk` today, captured from the real, fully-wired FastAPI
`app` object (not a hand-maintained list, so it can't silently drift from
reality).

Fase 2B will move ~169 route handlers out of server.py into per-domain
modules (menus_routes.py, media_routes.py, screens_routes.py, ...), each
mounted back onto `app`/`api_router` exactly as before. Every one of those
PRs is supposed to be a *pure relocation*: same path, same method(s), same
mount point, zero behavior change. This test is what makes that a provable
property instead of a promise - any extraction that changes, drops,
duplicates, or reorders a route's (method, path) pair fails this test.

Usage:
    pytest backend/tests/test_route_inventory.py

To (re)generate the frozen snapshot after a deliberate, reviewed route
change (a real new endpoint, a real rename - NOT as a way to silence a
failure you haven't understood):
    python -m tests.test_route_inventory --write
    # or, from backend/:
    python tests/test_route_inventory.py --write

Notes:
  * `/api/...` paths are the ones mounted via `api_router` (prefix="/api");
    everything else was mounted directly on `app`. The prefix is already
    baked into `route.path` by the time `app.routes` is inspected, so a
    single (kind, methods, path) tuple fully captures both "which router"
    and "which path" - no separate app-vs-api_router flag is needed.
  * Routes contributed by already-extracted modules (public_pages_routes,
    workspace_routes, stripe_routes, colorlight, finance, ...) are included
    too. They're not server.py's concern for Fase 2B, but keeping them in
    the same snapshot means this test protects the *whole* app's route
    surface, not just whatever still happens to live in server.py today.
  * Static file mounts (e.g. StaticFiles) and websocket routes are included
    as their own `kind` so a change there is caught too, even though they
    have no HTTP `methods` set.
"""
import json
import sys
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent / "route_inventory_snapshot.json"


def _current_inventory() -> list:
    """Introspect the real, fully-wired app and return a deterministic,
    JSON-serializable list of every mounted route."""
    from server import app  # imported lazily so --write works standalone

    entries = []
    for route in app.routes:
        methods = sorted(getattr(route, "methods", None) or [])
        path = getattr(route, "path", None) or getattr(route, "path_format", None)
        entries.append({
            "kind": type(route).__name__,
            "methods": methods,
            "path": path,
        })
    entries.sort(key=lambda e: (e["path"] or "", e["kind"], e["methods"]))
    return entries


def _diff(old: list, new: list) -> str:
    """Human-readable summary of what changed between two inventories."""
    def _key(e):
        return (e["kind"], tuple(e["methods"]), e["path"])

    old_keys = {_key(e) for e in old}
    new_keys = {_key(e) for e in new}
    removed = sorted(old_keys - new_keys)
    added = sorted(new_keys - old_keys)

    lines = []
    if removed:
        lines.append(f"  {len(removed)} route(s) MISSING vs. the frozen snapshot:")
        lines += [f"    - {k[0]} {' '.join(k[1]) or '-'} {k[2]}" for k in removed]
    if added:
        lines.append(f"  {len(added)} route(s) NEW vs. the frozen snapshot:")
        lines += [f"    + {k[0]} {' '.join(k[1]) or '-'} {k[2]}" for k in added]
    return "\n".join(lines) if lines else "  (no per-route diff - check ordering/duplicates)"


def test_route_inventory_matches_snapshot():
    if not SNAPSHOT_PATH.exists():
        pytest.fail(
            f"{SNAPSHOT_PATH.name} does not exist yet. Generate it once with:\n"
            f"    python -m tests.test_route_inventory --write\n"
            f"then commit the file alongside this test."
        )
    snapshot = json.loads(SNAPSHOT_PATH.read_text())
    current = _current_inventory()
    assert current == snapshot, (
        "The live route table no longer matches the frozen snapshot "
        f"({SNAPSHOT_PATH.name}). If this extraction was meant to be a pure "
        "relocation, this is a real regression - a route's path, method(s), "
        "or mount point changed, or a route was dropped/duplicated.\n"
        "If the change is real and intended (a genuine new/renamed route, "
        "reviewed and approved), regenerate the snapshot with:\n"
        "    python -m tests.test_route_inventory --write\n\n"
        f"{_diff(snapshot, current)}"
    )


if __name__ == "__main__":
    if "--write" in sys.argv:
        inventory = _current_inventory()
        SNAPSHOT_PATH.write_text(json.dumps(inventory, indent=2) + "\n")
        print(f"Wrote {len(inventory)} routes to {SNAPSHOT_PATH}")
    else:
        print(__doc__)


# Rutas donde el ORDEN de registro decide quién responde. El snapshot está
# ordenado por path, así que NO detecta cambios de orden: si una extracción
# mueve un router y una ruta genérica empieza a comerse a una concreta, el
# snapshot sigue pasando. Esto lo cubre resolviendo la ruta de verdad.
SHADOWING_SENSITIVE = [
    ("/api/media/serve", "GET", "serve_r2_media"),        # antes de /api/media/{media_id}
    ("/api/media/abc123", "GET", "get_media"),
    ("/api/events/screen/abc123", "GET", "sse_endpoint"), # única implementación de SSE
    ("/api/menus/abc123/render", "GET", "render_menu"),
    ("/api/menus", "GET", "get_menus"),
    ("/apk", "GET", "apk_short_url"),                     # antes del catch-all del SPA
    ("/mediaview.apk", "GET", "mediaview_apk"),
    ("/marketplace", "GET", "_marketplace"),
    ("/cualquier/cosa/inventada", "GET", "expo_spa_catchall"),
]


def test_shadowing_sensitive_paths_resolve_to_the_right_handler():
    from server import app

    for path, method, expected in SHADOWING_SENSITIVE:
        winner = None
        for route in app.routes:
            match = getattr(route, "path_regex", None)
            if match is None or method not in (getattr(route, "methods", None) or set()):
                continue
            if match.match(path):
                winner = getattr(route, "name", None) or getattr(route, "endpoint", None)
                break
        assert winner == expected, (
            f"{method} {path} lo resuelve '{winner}' y deberia resolverlo '{expected}': "
            "alguna extraccion cambio el orden de registro y una ruta generica se esta "
            "comiendo a una concreta."
        )
