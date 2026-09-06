# MEDIAVIEW — PREMIUM DESIGN REPORT
Fecha: junio 2026 · Alcance: UI/UX + experiencia visual (sin cambios de backend/negocio)

---

## 1. Lo que ya existía y se REUTILIZÓ (sin tocar)

| Pieza | Ruta | Nota |
|---|---|---|
| Backend FastAPI completo | `/app/backend/server.py` + `*_routes.py` | APIs, auth, RBAC, tenant isolation, pairing del Player, CRM, advertising |
| Planes y precios | `plans_routes.py` → `GET /api/plans` | La calculadora del landing consume esta API — **cero precios hardcodeados** |
| Signup / suscripciones | `signup_routes.py`, `workspace_routes.py` | Lógica intacta |
| Menús (CRUD + editor) | `/workspace/menus`, `/workspace/menu-edit`, `menu-editor.html` | Reutilizado, no duplicado |
| Selector de cantidad de pantallas | `app/(auth)/pricing.tsx` | Reutilizado tal cual |
| Onboarding | `app/workspace/onboarding.tsx` | Estructura reutilizada, sólo copy + detalle visual |
| Sistema i18n ES/EN | `web/i18n.js` | Reutilizado y ampliado (+180 claves) |
| Video real de producto | `web/promo-video.mp4` | Sigue en la sección "Mira la diferencia" |
| Logos | `logo-new.png` (fondo oscuro), `logo-dark.png` (fondo claro) | Ahora se intercambian según el scroll |

## 2. Lo que se REDISEÑÓ visualmente

### `web/landing.html` (homepage de producción, puerto 8001)
- **Hero nuevo**: titular de conversión + marco de TV premium con artwork real que rota
  entre 6 industrias, píldora "LIVE", chips clicables y 3 pruebas de confianza.
- Se **eliminó** el "TV de CSS" de juguete y los badges flotantes con emojis.
- Se **eliminaron** todas las fotos de stock externas (Unsplash/Pexels) del slideshow de menús;
  ahora usa artwork propio de MediaView.
- Nav reordenado y comprimido: Cómo Funciona · Industrias · Plantillas · Menús Digitales ·
  Precios · Nosotros + "Publica tu anuncio" + Iniciar sesión + Empieza Gratis.
- Logo cambia a la versión oscura cuando el nav se vuelve blanco al hacer scroll.

### `app/workspace/*` (12 pantallas, puerto 3000)
- Migrado de **oscuro `#0B0F1A` + índigo `#6366F1`** → **claro `#F8FAFC` + cian `#0891B2` + navy**.
- Cards con sombra suave en lugar de sólo borde.
- Todo el copy pasado a español (antes mezclaba inglés y español).
- Targets táctiles del bottom-nav subidos a 48 px.

### `app/landing.tsx` (landing del SPA Expo)
- De **negro/índigo `#050816` + `#6366F1`** → **navy `#0F172A` + cian**.
- Se le añadió marco de TV con artwork real rotando + galería de instalaciones reales.

### `app/(auth)/pricing.tsx`
- Color del plan Starter de índigo `#6366F1` → teal `#0E7490` (fuera del morado).
- Bullets de los planes localizados a español (en base de datos, vía script).

## 3. Componentes nuevos creados

**HTML / CSS (design system `landing.html`)**
`.reveal` (scroll reveal) · `.mv-tv` + `.mv-tv-stand` + `.mv-tv-glare` (marco de dispositivo) ·
`.mv-screen` (crossfade de contenido) · `.mv-live` (píldora en vivo) · `.mv-chip` (selector de industria) ·
`.mv-proof` (prueba social) · `.mv-envband` (banda de foto real full-bleed) ·
`.mv-story-card` (paso del producto) · `.mv-tabs` + `.mv-ind-card` (showcase filtrable) ·
`.mv-env-card` (galería de entornos) · `.mv-split` + `.mv-flow` (feature partida) ·
`.mv-tpl` (tarjeta de plantilla con hover) · `.mv-price` + `.mv-calc` + `.mv-stepper` (calculadora).

**React Native**
Dashboard del workspace reconstruido: tarjeta de uso de pantallas con barra de progreso,
tarjeta de estado de dispositivos (en línea / desconectados / equipo), lista de pantallas
con badges de estado, grid de acciones rápidas, pull-to-refresh.
Showcase de dispositivo + galería de entornos en `landing.tsx`.

## 4. Páginas mejoradas

| URL (preview) | Estado |
|---|---|
| `/api/landing` (= `/` en producción) | Rediseño premium completo |
| `/landing` (SPA Expo) | Recoloreado a marca + visuales reales |
| `/pricing` | Pulido, colores de marca, bullets en español |
| `/login`, `/signup` | Ya estaban limpios; sin regresiones |
| `/workspace` | Dashboard reconstruido |
| `/workspace/screens · menus · content · playlists · schedules · users · billing · settings · onboarding · menu-edit` | Tema claro + español |

## 5. Animaciones implementadas

1. **Scroll reveal** con `IntersectionObserver` + `cubic-bezier(.16,1,.3,1)`, con retardos escalonados (`.reveal-d1..d4`).
2. **Crossfade del contenido del TV** cada 3.8 s entre 6 industrias (hero) — pausable al elegir una industria.
3. **Rotación del showcase** en el SPA cada 4 s.
4. **Hover** de cards de industria / entorno / plantilla: elevación + zoom de imagen (0.6 s).
5. **Overlay de plantillas** que aparece al hacer hover.
6. **Pulso** del punto "LIVE".
7. **Pausa automática** de la rotación cuando la pestaña está oculta (ahorra CPU).
8. **`prefers-reduced-motion: reduce`** desactiva todo y muestra el contenido inmediatamente.

## 6. Assets: MANIFEST (24 piezas — TODAS generadas, ninguna pendiente)

Generadas con Gemini Nano Banana vía `backend/scripts/gen_premium_assets.py` (re-ejecutable,
salta lo ya existente). Servidas en `/api/web/assets/<id>.webp` (full) y `<id>-sm.webp` (grid).

| ID | Propósito | Ratio | Tipo | Dónde aparece |
|---|---|---|---|---|
| MV-HERO-001 | TV en pizzería real | 16:9 | estática | banda de entorno + paso 4 |
| MV-HERO-002 | Muro de 3 pantallas | 16:9 | estática | galería + slideshow de menús |
| MV-REST-PIZZA | Menú de pizza | 16:9 | estática | hero, industrias, plantillas |
| MV-REST-BURGER | Menú de hamburguesas | 16:9 | estática | industrias, plantillas |
| MV-REST-COFFEE | Menú de cafetería | 16:9 | estática | industrias, plantillas, slideshow |
| MV-REST-BREAKFAST | Menú de desayuno | 16:9 | estática | industrias, plantillas |
| MV-ICE-001 | Menú de heladería | 16:9 | estática | hero, industrias, plantillas |
| MV-MARKET-001 | Especiales de supermercado | 16:9 | estática | industrias, plantillas |
| MV-AUTO-001 | Precios de servicio automotriz | 16:9 | estática | hero, industrias, plantillas |
| MV-RETAIL-001 | Liquidación de temporada | 16:9 | estática | hero, industrias, plantillas |
| MV-CHURCH-001 | Bienvenida de iglesia | 16:9 | estática | hero, industrias, plantillas |
| MV-GYM-001 | Horario de clases | 16:9 | estática | industrias, plantillas |
| MV-CORP-001 | Recepción corporativa | 16:9 | estática | hero, industrias, plantillas |
| MV-EDU-001 | Anuncios de campus | 16:9 | estática | industrias, plantillas |
| MV-HEALTH-001 | Sala de espera | 16:9 | estática | industrias |
| MV-ENV-ICECREAM | Pantalla vertical en heladería | 16:9 | estática | galería + slideshow |
| MV-ENV-AUTO | Sala de espera de taller | 16:9 | estática | galería |
| MV-ENV-RETAIL | Vidriera comercial | 16:9 | estática | galería |
| MV-ENV-LOBBY | Recepción de oficina | 16:9 | estática | galería |
| MV-ENV-CHURCH | Santuario de iglesia | 16:9 | estática | galería |
| MV-MOBILE-001 | Editar precio desde el celular | 4:3 | estática | sección móvil + paso 3 |
| MV-PLAYER-001 | TV con código de 6 dígitos | 16:9 | estática | paso 2 + galería |
| MV-LAPTOP-001 | Dashboard en laptop | 4:3 | estática | paso 1 + galería |
| MV-IMPORT-001 | Menú impreso → menú editable | 16:9 | estática | sección de importación |

## 7. Video / storyboard — PENDIENTE (no se falsificó producción de video)

Los contenedores están listos (la sección "Mira la diferencia" ya reproduce
`promo-video.mp4`). Guion propuesto para 4 loops de 8–12 s, 1080p, sin audio, `.mp4` + `.webm`:

- **VIDEO 1 — "De la idea a la pantalla"**: laptop crea una promo → selecciona pantalla → Publicar → aparece en el TV del restaurante.
- **VIDEO 2 — "Cambia tu menú en segundos"**: celular abre el menú → cambia el precio de la pizza → Guardar → el TV se actualiza.
- **VIDEO 3 — "Conecta una pantalla"**: Android TV abre el Player → aparece `482 731` → se escribe en el panel → estado pasa a "En línea".
- **VIDEO 4 — "Contenido para cada negocio"**: secuencia rápida Pizza → Helados → Supermercado → Taller → Tienda → Iglesia → Gym → Corporativo.

Requisito técnico: `poster` obligatorio, `preload="none"`, `loop muted playsinline`, ≤ 1.5 MB cada uno.

## 8–10. Verificación en navegador

- **Desktop 1440×900**: hero, 4 pasos, industrias (13 cards + 11 filtros), galería de 8 entornos,
  importación de menú, edición móvil, 12 plantillas con filtros, calculadora de precios, CTA, footer. ✅
- **Móvil 390×844**: una columna, grids a 2 columnas, píldora LIVE reubicada, nav hamburguesa,
  calculadora usable con targets de 44 px. ✅
- **Workspace**: dashboard, pantallas, menús, contenido, facturación, ajustes — desktop y móvil. ✅
- **Bilingüe**: toggle ES/EN verificado en todas las secciones nuevas y las legacy. ✅

## 11. Impacto en performance

- 24 assets convertidos de PNG (**15 MB**) a WebP: **1.9 MB** full-size + **0.7 MB** thumbnails.
- Los grids usan las miniaturas `-sm.webp` (21–40 KB cada una), no las full-size.
- `loading="lazy"` en todo excepto la primera imagen del hero; `width`/`height` declarados para evitar CLS.
- El video promocional conserva `poster`; no se agregó ningún video nuevo a la carga inicial.
- Cero librerías JS nuevas: animaciones con CSS + `IntersectionObserver` nativo.
- La rotación del hero se pausa con `visibilitychange`.

## 12. Antes / después

- **Antes**: TV dibujado en CSS con items de menú falsos, fotos de stock ajenas, workspace
  negro-índigo, copy mezclado ES/EN, precios de ejemplo escritos a mano.
- **Después**: artwork propio de MediaView en 13 rubros dentro de marcos de dispositivo reales,
  fotografía de instalaciones propia, workspace claro cian/navy, bilingüe completo,
  calculadora alimentada por `GET /api/plans`.

## 13. URLs para revisión

| Qué | URL de preview |
|---|---|
| Homepage premium (la de producción) | `/api/landing` |
| Landing del SPA | `/landing` |
| Precios | `/pricing` |
| Registro | `/signup` |
| Login | `/login` |
| Workspace | `/workspace` (testws@test.com / Test1234!) |

## 14. Lo que NO se cambió a propósito

- Backend, APIs, autenticación, RBAC, aislamiento por tenant, lógica del Player, CRM, advertising público.
- Arquitectura de suscripciones y de precios (la UI sólo lee `GET /api/plans`).
- `web/customer.html`, `web/admin*`, `menu-editor.html` y el resto del panel legacy.
- `metro.config.js`, `package.json`, y las variables de entorno protegidas.
- El export estático `web/saas/` (ver decisiones pendientes).

## Resueltos después del reporte inicial

1. **`web/saas/` regenerado.** `npx expo export --platform web` → copiado a `backend/web/saas/`.
   Diff de rutas verificado (idéntico salvo el cambio de `login`/`signup` a `account/*`).
2. **Conflicto de rutas de auth resuelto sin romper nada.** Las páginas SaaS viven ahora en
   `/account/login` y `/account/signup`; `/login`, `/signup`, `/portal` y `/marketplace`
   siguen sirviendo el SPA de anunciantes (`customer.html`) exactamente como antes.
3. **Precio anual** con dos meses gratis, configurable por plan (`annual_free_months`),
   sin descuentos escritos en el código.
4. **Prueba social sin inventar clientes**: sección de logos administrable
   (`/api/admin/clients-view`), oculta mientras no haya logos reales.

## Decisiones pendientes (requieren al dueño)

1. **Videos de producto** (sección 7) — 4 loops por producir.
2. **Cobro real**: el ciclo anual se guarda pero `billing_status` queda en `pending`.
   Falta integrar Stripe (requiere la API key del dueño).
3. **Logos reales de clientes**: subirlos desde `/api/admin/clients-view` para que la
   sección de prueba social aparezca en el sitio.
