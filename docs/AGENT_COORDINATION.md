# Bitácora de coordinación entre agentes — MediAd View

Objetivo: que dos (o más) agentes trabajen el mismo repo sin pisarse.

## Reglas acordadas

1. **Antes de empezar a trabajar**: `git fetch --all` + leer este archivo completo.
2. **Antes de cualquier push**: añadir una entrada nueva en "Bitácora" (rama, commit base,
   archivos tocados, qué cambió, cómo se validó).
3. **Nadie hace push directo a `production`** sin confirmación explícita de duarte.
   `production` es la rama que Render despliega (`render.yaml` → `branch: production`).
4. **Un archivo, un dueño a la vez**: si un archivo aparece en una entrada abierta
   (`Estado: EN CURSO`) de otro agente, no se toca; se coordina primero.
5. **Cerrar la entrada** al terminar: `Estado: CERRADA` + commit final.

## Estado real de las ramas (auditado 2026-09-08, solo lectura)

| Rama | Tip | Qué contiene | Se despliega |
|---|---|---|---|
| `production` | `73d7d50` | Snapshot estable + hotfixes por *cherry-pick*. **NO** tiene Sprint 1 del player (tokens de dispositivo, `/api/events/screen/{id}` propio, progreso real) ni los routers de workspace (`team`, `menu-ai`, `promo`, `reports`, `signup`). | ✅ Render (`render.yaml` → `branch: production`) |
| `main` | `c1fbe12` | Snapshot viejo del backend + `android-player/**` al día (fuente del APK). | ❌ (solo compila el APK en Actions) |
| `fix/panel-perf` (rama de trabajo de Maxx) | `727a624` | **Superset funcional**: todo lo de `production` + Sprint 1 + workspace SaaS + frontend Expo completo. | ❌ |

Verificado con `git cherry` + `git diff --name-status`: **no hay ni un archivo ni un fix que exista
en `production` y falte en la rama de trabajo** (los 4 commits que `git cherry` marca como
"solo en production" son las versiones adaptadas de trabajo ya hecho en la rama de trabajo:
orientación en 3 niveles, marketplace orientation-safe, PATCH de pantallas y playlist sin disco).

Diferencias comprobadas contra el backend vivo (`https://mediadview.com`):
- `/api/plans` 200, `/api/workspace/screens` 401, `/api/ready` 200 → coincide con `production`.
- `/api/workspace/team` 404 → los routers de workspace/team **no** están en producción.
- `/api/events/screen/{id}` responde SSE, pero lo sirve el router genérico
  `realtime.py → /api/events/{channel}/{rid}`, **no** la ruta de Sprint 1.
  ⚠️ Al unificar habrá **dos** implementaciones de SSE para el mismo path
  (`server.py` de Sprint 1 y `realtime.py`), con managers pub/sub distintos: hay que quedarse con
  una sola, o el player escuchará el canal equivocado y no verá los cambios.
- El player Sprint 1 manda `X-Device-Token` solo si lo tiene y `authenticate_device()` tiene
  **modo gracia** (adopta el token del primer heartbeat), así que unificar no deja fuera a los
  dispositivos ya emparejados.
- ⚠️ Consecuencia para la prueba física del APK v3.4.0: en producción **no** hay backend de
  Sprint 1, así que esa prueba valida reproducción/orientación/video, **no** tokens ni progreso real.

## Reservas activas (quién tiene tomado qué)

| Archivo / carpeta | Agente | Rama | Estado |
|---|---|---|---|
| `android-player/**` | Maxx (E1) | `main`, `player-v3.4.0` | CERRADA |
| `backend/web/customer.html` | Maxx (E1) | `production` | CERRADA |

## Plantilla de entrada

```
### <fecha> — <agente> — <título corto>
- Rama: <rama>
- Commit base: <sha> (`git merge-base`/`git fetch` verificado)
- Archivos tocados: <lista>
- Qué cambió: <resumen funcional, no técnico-verboso>
- Validación: <tests / pytest / testing_agent / prueba física>
- Riesgo para el otro agente: <archivos compartidos, migraciones, .env>
- Estado: EN CURSO | CERRADA
- Commit final: <sha>
```

## Bitácora

### 2026-09-08 — Maxx (E1) — Preparación de la unificación de ramas (sin desplegar nada)
- Ramas creadas: `trunk` (= rama de trabajo, fuente única de verdad) y
  `release/unify-2026-09-08` (rama de REVISIÓN: mismo árbol que `trunk` pero con `production`
  como primer padre, para que el próximo deploy sea un merge normal y no otro cherry-pick).
- `production` **no se tocó** más allá de este documento.
- Plan de unificación (3 pasos, el paso 3 necesita OK de duarte + QA):
  1. `trunk` = `fix/panel-perf` (superset verificado). Todo el trabajo nuevo sale de `trunk`.
  2. `main` se reapunta a `trunk` para que el APK y el backend salgan del mismo árbol
     (hoy `main` solo tiene el player al día).
  3. Deploy de unificación: mergear `release/unify-2026-09-08` a `production`. Eso **activa en
     producción** el workspace SaaS + Sprint 1, así que ANTES hay que: (a) resolver el SSE
     duplicado, (b) pasar la suite de `backend/tests/`, (c) probar login de workspace y
     marketplace en un entorno de staging o con feature flags.
- Riesgo para el otro agente: si el refactor de `server.py` se hace sobre `production`, cada
  archivo movido se volverá a conflictuar en el paso 3. **Recomendación: refactorizar sobre
  `trunk`** y desplegar por merge, no por cherry-pick.
- Estado: CERRADA (preparación) — la unificación real queda pendiente de duarte.

### 2026-09-07 — Maxx (E1) — Player v3.4.0: video en TextureView + clips completos
- Rama: `main` (fuente del APK) y `player-v3.4.0`; nada de refactor de backend.
- Commit base: `8f26441` (main remoto) / `7214d40` (rama de trabajo `fix/panel-perf`).
- Archivos tocados:
  - `android-player/app/src/main/java/com/mediaview/player/PlaybackController.kt`
  - `android-player/app/src/main/res/layout/video_surface.xml` (nuevo)
  - `android-player/app/build.gradle.kts` (versionCode 22 / v3.4.0)
  - `codemagic.yaml` (dispara también en ramas `player-v*`)
- Qué cambió: el video se pintaba en un SurfaceView, así que la rotación y el cross-fade no
  llegaban a los frames decodificados (rayas verdes/moradas en la caja de TV); ahora se pinta en
  TextureView. Además cada video se reproduce hasta su final real en vez de cortarse con la
  duración de la campaña.
- Validación: build GitHub Actions run `34137380145` en verde; APK publicado en el Release
  `player-latest` y verificado por descarga (`/apk` → 302 → 200, 8.5 MB, versionName 3.4.0).
  Pendiente: prueba física en la TV box (duarte).
- Riesgo para el otro agente: ninguno en `backend/`.
- Estado: CERRADA — commit `c1fbe12` (main).

### 2026-09-07 — Maxx (E1) — Marketplace: reintento de chunks en subidas de video
- Rama: `production` (cherry-pick sobre `b9fbecd`).
- Archivos tocados: `backend/web/customer.html` (solo el uploader del marketplace).
- Qué cambió: cada parte de 2 MB se reintenta hasta 4 veces y se avisa claro cuando el iPhone no
  puede leer el archivo porque el video está en iCloud sin descargar. El backend ya era
  idempotente por `X-Chunk-Offset`, no se tocó Python.
- Validación: `backend/tests/test_chunked_upload_iter35.py` (7 passed) + subida real desde iPhone.
- Riesgo para el otro agente: `backend/web/customer.html` es la SPA del marketplace; si el refactor
  mueve rutas públicas, revisar que `API` y `/marketplace` sigan resolviendo.
- Estado: CERRADA — commit `73d7d50` (production).

<!-- Nuevas entradas ARRIBA de esta línea, más recientes primero. -->
