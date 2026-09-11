# Fase 2 del refactor — propuesta (Maxx, pendiente de acordar con Claude + duarte)

## Punto de partida (medido, no estimado)

`backend/server.py` tras la fase 1: **6923 líneas y 169 rutas**. Reparto por primer segmento:

| Rutas | Grupo | Rutas | Grupo |
|---|---|---|---|
| 46 | `/admin/*` | 6 | `/customer/*` |
| 15 | `/menus/*` | 6 | `/campaigns/*` |
| 13 | `/media/*` | 5 | `/superadmin/*` |
| 12 | `/playlists/*` | 4 | `/auth/*` |
| 9 | `/player/*` | 3 | `/payments/*` |
| 8 | `/screens/*` | 2+2+2 | `/widgets`, `/certification`, `/screen` |
| 8 | `/public/*` | 1 cada | `/health`, `/analytics`, `/playlog`, `/client-errors`, `/s` |
| 7 | `/devices/*` | | |

Alrededor de esas rutas viven los helpers compartidos que hoy hacen que `server.py` sea
imposible de partir sin dolor: `db`, `get_current_user`, `require_admin`, `require_superadmin`,
`bump_playlist_version`, `build_playlist_items`, `media_orientation`, `_media_has_inline_bytes`,
`_ip`, `MEDIA_DIR`/`WEB_DIR`.

## Por qué NO empezar moviendo archivos a carpetas

Los ~40 módulos de `backend/*.py` se importan planos (`from workspace_routes import ...`).
Moverlos a `backend/playlists/`, `backend/screens/`, etc. **antes** de vaciar `server.py`:
- toca decenas de imports en un solo golpe (conflicto garantizado con cualquier trabajo en curso),
- no reduce ni una línea del archivo que causa el 27 % de los conflictos históricos,
- y deja `server.py` igual de acoplado.

Propongo el orden inverso: **primero vaciar `server.py` por dominio, después agrupar carpetas.**

## Fase 2A — Red de seguridad (primero, sin mover nada)

1. `backend/tests/test_route_inventory.py`: congela el inventario de rutas
   (método + path + si va en `app` o en `api_router`) generado desde `trunk`. Cualquier
   extracción posterior que cambie, pierda o reordene una ruta **falla el test**.
   Es lo que convierte "relocalización pura" en algo demostrable y no en una promesa.
2. `backend/deps.py`: mover ahí los helpers compartidos (`get_current_user`, `require_admin`,
   `require_superadmin`, `_ip`) y `backend/media_utils.py` (`media_orientation`,
   `_media_has_inline_bytes`, `build_playlist_items`, `bump_playlist_version`).
   Sin este paso, cada extracción necesita una factory con 6-8 parámetros.

## Fase 2B — Extracción por dominio, un módulo por PR

Cada PR: inventario de rutas antes/después + sondas HTTP de cada ruta + suite completa.
Orden de menor a mayor riesgo:

| # | Módulo nuevo | Qué se lleva | Riesgo | Por qué ese orden |
|---|---|---|---|---|
| 1 | `menus_routes.py` | 15 rutas `/menus/*` + render + QR | 🟢 | Dominio cerrado, ya tiene su propio módulo de IA (`menu_ai_routes.py`) |
| 2 | `media_routes.py` | 13 `/media/*` (upload, chunks, presign, serve, miniaturas) | 🟡 | Toca R2; hay que probar los dos caminos (con y sin bucket) |
| 3 | `screens_routes.py` | 8 `/screens/*` + las de `/admin/screens*` | 🟡 | La orientación vive aquí; hay que revalidar la cadena admin → marketplace → player |
| 4 | `playlists_routes.py` | 12 `/playlists/*` + `/playlog` | 🟠 | Comparte `bump_playlist_version` con el SSE |
| 5 | `player_routes.py` | 9 `/player/*` + 7 `/devices/*` | 🔴 | Es el contrato con el APK en la calle: se prueba con un dispositivo real antes de fusionar |
| 6 | `admin_panel_routes.py` | las 46 `/admin/*` + 5 `/superadmin/*` | 🔴 | El bloque más grande; se parte en 2-3 PRs (dashboard, campañas, finanzas) |

Al terminar, `server.py` debería quedar en ~1500 líneas: arranque, middleware, CORS,
montaje de routers y el catch-all del SPA.

## Fase 2C — Agrupar en carpetas (solo al final)

Con `server.py` ya delgado, mover los módulos a `backend/domains/<dominio>/` y actualizar los
imports en un único commit, un único deploy. Antes de eso no aporta nada.

## Reglas de trabajo acordadas

- Todo sale de `trunk`, cada PR en su rama `refactor/fase2-<n>-<dominio>`.
- Nada a `production` sin OK explícito de duarte.
- Cada PR anota su entrada en `docs/AGENT_COORDINATION.md` antes del push.
- `/apk`, `/apk.apk`, `/mediaview.apk` y `/download.apk` se comprueban en cada PR: van montadas
  en `app` y **antes** del catch-all `@app.get("/{full_path:path}")`; si se cuelan detrás, la TV
  box deja de poder descargar el APK.
- El orden de declaración importa donde hay rutas genéricas: `/media/serve` tiene que ir antes
  de `/media/{media_id}`, y `/events/{channel}/{rid}` es la única implementación de SSE.
