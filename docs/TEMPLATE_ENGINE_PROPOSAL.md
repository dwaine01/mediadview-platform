# MediaView Template Engine — Propuesta de arquitectura

Estado: **PROPUESTA — pendiente de aprobación del cliente (duarte).**
Autor: E1 · 2026-06

Este documento responde al punto 15 del pedido: *inspeccionar primero la arquitectura
existente y presentar la propuesta antes de implementar*.

---

## 1. Lo que ya existe y de qué nos podemos colgar

| Pieza | Dónde | Cómo la reusamos |
|---|---|---|
| Reproductor Android (Kotlin) | `android-player/` | **Sin cambios.** Ya renderiza cualquier ítem con `content_type: "widget"` dentro de un WebView (`PlayerModels.kt:34`). Un template es HTML en una URL. |
| Playlists | `playlists` + `server.py:_build_owned_playlist_items` | Se agrega un tipo de ítem `design`, al lado de `menu`, `media` y `webpage`. |
| Pantallas y versionado | `screens.playlist_version` + `bump_playlist_version` | Igual que los menús: editar un diseño sube la versión y el TV recarga. |
| Horarios | `playlist_domain.normalize_schedule` | Sin cambios: el diseño se publica dentro de una playlist, que ya tiene horario y prioridad. |
| Biblioteca de medios | `media` (R2 + legacy) + `storage_service` | Las fotos y videos de producto salen de ahí, con URL pública de R2. |
| Menús con diseño propio | `menus.canvas`, `menu_templates` | Es el mismo motor de overlay, un nivel más abajo. Convive; no se reemplaza. |
| Tipografía premium | el render de menús ya carga Google Fonts | Los templates declaran su familia y el render la pide. |

### El hallazgo que define todo

El APK **no necesita ni una línea de cambio**. Todo lo que renderice HTML en una URL
llega al TV hoy mismo. Eso significa que la calidad visual del template está limitada
sólo por CSS: gradientes, texturas, sombras, capas, video de fondo, animación. Y también
significa que el motor de templates es **backend + web**, no Android — con el riesgo de
romper el player reducido a cero.

---

## 2. Arquitectura: tres capas separadas

El error a evitar es el que el pedido marca explícitamente: un componente nuevo por cada
template. La separación es:

```
TEMPLATE (catálogo de MediaView)      → declarativo, JSON. Lo escribimos nosotros.
   ↓  el cliente elige uno
DESIGN (instancia del cliente)        → qué template + qué datos + qué overrides
   ↓  se publica
RENDER (HTML)                         → un único motor lo genera para cualquier template
```

### 2.1 `signage_templates` — el catálogo

Propiedad de MediaView, no del cliente. Un documento por template, **sin código**:

```jsonc
{
  "id": "pizzeria-forno-grid",
  "kind": "menu_board",              // menu_board | flash_offer
  "industry": "pizzeria",
  "name": "Forno — Grilla de 12",
  "canvas": { "w": 1920, "h": 1080, "orientation": "landscape" },
  "safe_zone": 48,                    // margen intocable para TVs con overscan
  "capacity": { "products": 12, "categories": 3 },
  "screen_role": null,                // "main" | "combos" | "drinks" en sets multi-pantalla
  "theme": {
    "palette": { "bg": "#140A08", "accent": "#C1440E", "ink": "#FFF6E8", "price": "#F2C14E" },
    "fonts": { "display": "Playfair Display", "body": "Inter" },
    "texture": "wood-dark",           // capa de textura del catálogo
    "mood": "warm-italian"
  },
  "background": [                     // capas, de atrás hacia adelante
    { "type": "color", "value": "#140A08" },
    { "type": "texture", "asset": "wood-dark", "opacity": 0.35 },
    { "type": "gradient", "from": "#00000000", "to": "#000000CC", "angle": 180 }
  ],
  "blocks": [                          // la composición
    { "type": "brand",    "rect": [48,40,520,120], "fields": ["logo","business_name"] },
    { "type": "category", "rect": [48,190,900,70], "binds": "categories[0]" },
    { "type": "product_grid",
      "rect": [48,270,1180,760], "cols": 3, "rows": 4, "gap": 24,
      "binds": "categories[0].products",
      "card": "photo-top-price-strip" },   // preset de tarjeta del catálogo
    { "type": "product_list",
      "rect": [1280,270,592,500], "binds": "categories[1].products",
      "row": "name-dots-price" },
    { "type": "promo",    "rect": [1280,800,592,230], "fields": ["promo_title","promo_price"] },
    { "type": "qr",       "rect": [1760,40,120,120], "fields": ["qr_url"] }
  ],
  "motion": { "preset": "subtle-fade", "loop_s": 0 }
}
```

**Lo importante**: `blocks` es un vocabulario cerrado y chico (`brand`, `category`,
`product_grid`, `product_list`, `hero`, `promo`, `qr`, `text`, `media`, `ticker`). El
motor sabe dibujar esos diez bloques con calidad de agencia. Un template nuevo es un JSON
nuevo, no un componente nuevo. Eso es lo que hace que la biblioteca escale a miles.

### 2.2 `products` — los datos reusables (punto 7 del pedido)

```jsonc
{ "id": "...", "org_id": "...", "name": "Pepperoni", "description": "...",
  "category_id": "...", "price": 15.99,
  "variants": [ {"label":"Small","price":9.99}, {"label":"Medium","price":12.99},
                {"label":"Large","price":15.99} ],
  "sale_price": null, "image_media_id": "...", "video_media_id": null,
  "available": true, "featured": false }
```

Los `variants` son los que permiten la fila `Small $9.99 | Medium $12.99 | Large $15.99`
del ejemplo del pedido. Cambiar el precio de «Pepperoni» **una vez** lo cambia en todos
los diseños que lo usan, porque el diseño guarda el `product_id`, no el precio.

Puente con lo que ya hay: los `menus.items` actuales se migran a `products` de forma
perezosa (al abrir un menú), y los menús viejos siguen funcionando sin tocar nada.

### 2.3 `designs` — «Mis diseños» del cliente

```jsonc
{ "id": "...", "org_id": "...", "template_id": "pizzeria-forno-grid",
  "name": "Menú principal",
  "brand": { "logo_media_id": "...", "business_name": "La Bendición" },
  "bindings": { "categories": [ {"name":"PIZZAS","product_ids":[...]},
                                {"name":"BEBIDAS","product_ids":[...]} ],
                "promo_title": "FAMILY COMBO", "promo_price": "$29.99" },
  "overrides": { "theme.palette.accent": "#E03131" },   // modo avanzado, opcional
  "set_id": null, "set_role": null,                      // para sets multi-pantalla
  "status": "draft" }
```

`overrides` es la respuesta al punto 6: por defecto la composición profesional queda
intacta; el cliente sólo reemplaza contenido. Si entra al modo avanzado, puede pisar
colores y fuentes puntuales — nunca las posiciones.

### 2.4 El motor de render

`backend/template_engine/` con un módulo por bloque:

```
template_engine/
  __init__.py        render_design(design, template, products) -> HTML
  theme.py           paleta, fuentes, texturas, tokens de espaciado
  layers.py          fondos: color, gradiente, textura, imagen, video
  blocks/            brand, category, product_grid, product_list, hero, promo, qr, ticker
  motion.py          presets de animación (subtle-fade, ken-burns, price-pop, countdown)
  fit.py             escalado del escenario + ajuste de texto (ya probado en los menús)
```

Sale un HTML autocontenido, escalado con un único `transform` — la misma técnica que ya
funciona en el render del diseño propio y que se ve idéntica en 1080p, 4K y en el celular.

### 2.5 Entrega al TV — sin tocar el APK

```
POST /api/workspace/designs/{id}/publish  { screen_ids: [...] }
  → sincroniza un playlist con un ítem { type: "design", ref_id }
  → _build_owned_playlist_items devuelve
      { media_id: "design:<id>", content_type: "widget",
        media_url: "/api/designs/<id>/render?v=<ms>",
        checksum: sha256(id + última edición) }
```

Idéntico al camino que ya usan los menús, incluido el `checksum` que hace que el player
recargue cuando cambia un precio. **Cero riesgo para el player.**

### 2.6 Sets multi-pantalla (punto 2)

`design_sets`: `{ id, org_id, name, template_set_id, members: [{design_id, role, screen_id}] }`.
El template declara `screen_role`, y las 3 o 4 piezas comparten `theme`, así que se ven
como un solo sistema de diseño. Publicar el set publica cada pieza en su pantalla.

### 2.7 Flash Offers (punto 3)

Mismo motor, `kind: "flash_offer"`, con bloques `hero` + `promo` y presets de `motion`
más fuertes (zoom, entrada de precio, cuenta regresiva, video de fondo). Se publican con
`priority` alta y `expires_at` — exactamente el mecanismo de promos que **ya existe**
(`promo_routes.py`, prioridad 90), así que interrumpen la rotación del menú y vuelven
solas cuando vencen.

---

## 3. UX propuesta

### 3.1 Biblioteca (punto 10)

`/workspace/templates`

1. **Primera vez**: «¿Qué tipo de negocio tenés?» — grilla de rubros con ícono. Se guarda
   en la organización y de ahí en más la biblioteca abre filtrada por su rubro.
2. **Grilla de previews**: cada tarjeta muestra el render real del template con contenido
   de muestra, en su proporción (16:9 o 9:16). Al tocar/hover, si es animado, arranca la
   animación.
3. **Filtros** (chips, una fila con scroll): Rubro · Menú completo / Promoción ·
   Horizontal / Vertical · Animado / Estático · Cantidad de productos.
4. Tocar un template → **Vista previa a pantalla completa** con el render real + botón
   «Usar esta plantilla».

### 3.2 Editor (punto 6)

`/workspace/design-edit?id=...` — **no** es un editor de diseño gráfico. Tres pestañas:

- **Contenido** — lo que el cliente toca el 95% del tiempo. Lista de categorías y
  productos del diseño: tocar un producto abre la ficha (nombre, descripción, precio,
  variantes, foto, video, disponible). La foto se recorta sola al hueco del template.
- **Marca** — logo, nombre del negocio, teléfono, QR.
- **Estilo (avanzado)** — paleta y fuentes del template, con un aviso de que el diseño
  está pensado para verse mejor con los valores originales. Botón «Volver al original».

Arriba, siempre: **Vista previa** (abre el render real) y **Publicar** (selector de
pantallas, el que ya construimos). Flujo: *Elegir → Reemplazar contenido → Vista previa →
Publicar.*

### 3.3 Mis diseños

`/workspace/designs` — los diseños guardados del cliente, con su preview, en qué pantallas
están en vivo y acceso directo a editar o duplicar.

---

## 4. Cómo se integra sin romper nada

| Riesgo | Mitigación |
|---|---|
| Romper el APK | No se toca ningún endpoint `/api/devices/*` ni `/api/player/*`. El tipo `design` se agrega **al lado** de los existentes en el builder de playlists, con la misma forma de JSON. |
| Romper los menús actuales | El motor de templates es código nuevo. `menus`, `menus.canvas` y `menu_templates` siguen intactos y funcionando. |
| Pisar Contenido / Playlists / Horarios | Los diseños viajan dentro de playlists, como los menús. Cero cambios en Contenido, Playlists, Horarios y Publicación. |
| Peso y memoria del servidor | El render es HTML, no imágenes: no hay Pillow ni rasterizado en el camino caliente. Las previews del catálogo se generan una vez y se cachean. |
| Fuentes y texturas | Auto-hospedadas en R2 con `@font-face`, para que un TV sin acceso a Google Fonts no pierda la tipografía. |

---

## 5. Prototipo inicial (punto 14)

19 templates, con contenido de muestra realista para poder juzgar el diseño:

| Rubro | Cant. | Qué demuestra |
|---|---|---|
| Pizzería | 3 | Grilla de 12 con variantes S/M/L, híbrido con 2 destacados, menú de categorías |
| Fast food | 3 | Board de combos con foto grande, grilla de 9, tira de precios |
| Restaurante premium | 3 | **Set coordinado de 3 pantallas** (principales / combos / bebidas y postres) |
| Heladería | 3 | Colorido, 15 sabores en una pantalla, vertical 9:16 |
| Restaurante mexicano | 2 | Vibrante, patrón propio, 10 productos |
| Pescadería | 2 | Precios por libra, estilo mercado, 12 productos |
| Farmacia | 2 | Limpio y legible, promociones + información |
| Flash offers | 4 | Precio animado, video de fondo, cuenta regresiva, 2x1 |

Los de pizzería, heladería y pescadería son los que muestran **8 a 15 productos con
nombre, foto y precio en una sola pantalla**, que es el requisito explícito.

---

## 6. Plan de entrega por fases

| Fase | Qué se entrega | Se puede ver |
|---|---|---|
| **F1 — Motor** | Esquema + `template_engine` con los 10 bloques + render + 1 template de pizzería con contenido de muestra | Sí: la pizzería completa, en el TV |
| **F2 — Datos** | `products` con variantes, puente con los menús actuales, fichas de producto | Sí: cambiar un precio una vez y ver que cambia en todos lados |
| **F3 — Biblioteca + Editor** | `/workspace/templates`, selector de rubro, filtros, previews, editor de 3 pestañas, «Mis diseños» | Sí: el flujo completo elegir → reemplazar → publicar |
| **F4 — Catálogo** | Los 19 templates del prototipo, incluido el set de 3 pantallas | Sí |
| **F5 — Movimiento** | Presets de animación, video de fondo, cuenta regresiva, los 4 flash offers | Sí |

Cada fase se despliega a producción y se prueba antes de arrancar la siguiente.

---

## 7. Decisiones que necesito confirmar

1. **Fotos de muestra**: para que los templates se vean de agencia hacen falta fotos de
   producto buenas. Puedo generarlas con IA (Gemini Nano Banana) y guardarlas en R2 como
   contenido de muestra de MediaView, o usar fotos que vos provean. Generarlas consume
   saldo de la Universal Key.
2. **Quién carga el catálogo**: los templates son de MediaView. Propongo que se carguen
   con un script versionado en el repo (`backend/seed_templates/*.json`), no a mano en la
   base, así se despliegan solos y quedan auditados.
3. **Vertical (9:16)**: lo incluyo en el motor desde F1, pero en el prototipo sólo dos
   templates son verticales. ¿Alcanza?
4. **Menú viejo vs. templates**: «Usar mi propio diseño» (lo que ya funciona) y la
   biblioteca de templates son dos caminos distintos para el mismo fin. Se quedan los dos
   y el cliente elige, ¿correcto?
