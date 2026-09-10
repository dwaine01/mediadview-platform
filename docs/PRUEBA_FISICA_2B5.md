# Prueba física en TV box — validación de la Fase 2B-5

**Para:** duarte
**Qué se está validando:** que las 16 rutas `/player/*` + `/devices/*` movidas a
`backend/player_routes.py` (rama `refactor/fase2-5-player`) se comporten **exactamente** igual
que antes con el APK real v3.4.0. Sin esta prueba **no se fusiona a `trunk`**.

---

## 0. Datos de la prueba

| Campo | Valor |
|---|---|
| **Server URL** (esto es lo único que hay que cambiar en la caja) | `https://sprint1-signage.preview.emergentagent.com` |
| Pantalla de prueba | **PRUEBA 2B-5 TV Box** |
| `screen_id` | `eb38ab1b-b4d0-4cce-b472-99fbaedb14fd` |
| **Device ID** (pairing code) | `MV-F9NZ-S9CS` |
| **Secret Key** | `grrOutxlstOdN-eThS5yycuQ` |
| Contenido asignado | Playlist «Menú del día» → 2 ítems: el widget **Menú Principal** (20 s) y la imagen **Margherita-ia.jpg** (10 s) |

### Panel del comercio (para armar el menú de verdad)

| Campo | Valor |
|---|---|
| Panel | `https://sprint1-signage.preview.emergentagent.com/account/login` → entra a `/workspace` |
| Usuario | `pizzeria@demo.com` / `Pizza1234!` |
| Organización | **Pizzería Don Luis** |
| Plan | **Enterprise · suscripción `active`** (50 pantallas incluidas, `screens_limit` = ilimitado, todas las funciones premium) |
| Pantallas de la org | Mostrador, Sala, Vitrina y **PRUEBA 2B-5 TV Box** (la de la caja) |
| Menú | «Menú Principal», 8 productos, publicado en las 4 pantallas |

La pantalla de la caja pertenece a esa organización, así que todo lo que duarte haga en
**Menús → Menú Principal** (precios, fotos, agotados, categorías) y en **Promo** cae sobre la
misma pantalla que está reproduciendo la TV box. El player hace un `syncNow` cada **15 s** y
además escucha SSE, y el widget del menú se sirve con `Cache-Control: no-store`, así que un
cambio de precio se ve en la caja en la vuelta siguiente del loop sin tocar nada más.

Ese entorno ya corre el código de la 2B-5. Verificado por mí antes de mandarte esto: las 7 rutas
`/devices/*` responden 200 sobre esa URL, la playlist entrega los 2 ítems, la imagen baja completa
(731 094 bytes), el render del menú devuelve 10 758 bytes y el SSE de la pantalla conecta.

⚠️ Dos avisos de entorno (no son bugs del refactor):
- En esa URL **solo `/api/*` llega al backend**; la raíz la sirve Metro. O sea `/apk` ahí da 404:
  si necesitás reinstalar el APK, bajalo del Release `player-latest` de GitHub como siempre.
- El `update_available` que devuelve el heartbeat en ese entorno anuncia la v2.2.0 (`versionCode`
  4). El `AutoUpdater` del APK corta si `versionCode <= 22`, así que **no** va a intentar
  degradar la app. Lo verifiqué en el código, no hay riesgo de que se auto-instale nada.

---

## 1. Repuntar la caja al entorno de prueba (flujo de pairing manual)

El APK viene con `mediadview.com` embebido, pero el server se puede sobreescribir desde la
pantalla de pairing manual, sin reinstalar nada:

1. Abrí la app. Si ya está emparejada y reproduciendo, apretá **MENU** (o **F1**) **5 veces
   seguidas** (dentro de 3 s) → sale «Admin access» → PIN = **el código de activación de 6
   caracteres** que muestra/mostró la pantalla de pairing → «Desvincular». Vuelve a la pantalla de
   pairing.
2. En la pantalla de pairing, otra vez **MENU × 5** (o mantener **OK** apretado 5 segundos) →
   «Admin access» → mismo PIN → **«Manual pairing»**.
3. En esa pantalla llená los 3 campos:
   - **Device ID:** `MV-F9NZ-S9CS`
   - **Secret Key:** `grrOutxlstOdN-eThS5yycuQ`
   - **Server URL:** `https://sprint1-signage.preview.emergentagent.com`
4. **Connect Device**. Tiene que decir «Connected to: PRUEBA 2B-5 TV Box» y arrancar la
   reproducción en ~1,2 s.

Ese botón pega en **`POST /api/devices/pair`** — la primera de las 16 rutas movidas.

---

## 2. Qué mirar en pantalla (esto es la prueba de verdad)

- [ ] Aparece el **Menú Principal** (widget, 20 s) y después la **imagen Margherita** (10 s), en
      loop, con cross-fade.
- [ ] La imagen se ve **completa y sin rayas ni franjas verdes/moradas** (esto también revalida
      el TextureView de la v3.4.0).
- [ ] La orientación es **horizontal** y no queda rotada ni recortada.
- [ ] Se queda **20 minutos largos** en loop sin congelarse, sin pantalla negra y sin volver a la
      pantalla de pairing.

## 3. Qué mirar en el diagnóstico de la app

Apretá **I** (o MENU × 5 → PIN) para abrir el panel de diagnóstico y confirmá:

- [ ] **Server URL:** `https://sprint1-signage.preview.emergentagent.com` (si dice
      `mediadview.com`, el paso 1.3 no tomó y la prueba **no** vale).
- [ ] `screen_id` = `eb38ab1b-b4d0-4cce-b472-99fbaedb14fd`.
- [ ] Heartbeat en verde, contador subiendo (cada ~30 s).
- [ ] Sin errores rojos de red ni `HTTP 4xx/5xx`.

## 3 bis. Armar un menú de verdad desde el panel (lo que pidió duarte)

Con la caja ya reproduciendo, entrá al panel con `pizzeria@demo.com` / `Pizza1234!`:

- [ ] **Menús → Menú Principal**: cambiá un precio (ej. Margherita) y guardá. En ≤ 15 s la caja
      tiene que mostrar el precio nuevo.
- [ ] Marcá un producto como **agotado** y confirmá que desaparece/aparece tachado en la caja.
- [ ] **Crear Menú** desde cero, agregale 2-3 productos y **publicalo en PRUEBA 2B-5 TV Box**;
      la caja tiene que empezar a mostrarlo.
- [ ] **Promo**: lanzá una promo instantánea y verificá que entra en la caja.
- [ ] **Contenido**: subí una imagen o video propio y sumalo a la playlist de esa pantalla.
- [ ] **Pantallas**: cambiá la orientación de PRUEBA 2B-5 TV Box a vertical y confirmá que la
      caja rota (esto bumpea `playlist_version`, así que también valida
      `GET /api/player/{id}/version`).

## 4. Segunda vuelta: el flujo de código de activación

El paso 1 valida `pair`. Para validar también `register` + `check` (el flujo normal de un
cliente nuevo):

1. **MENU × 5** → PIN → **«Desvincular»**. Ojo: el Server URL **se conserva**, así que ya queda
   apuntando al entorno de prueba.
2. La app vuelve a la pantalla de pairing y muestra un **código de activación de 6 caracteres**.
   Eso es `POST /api/devices/register`, y el `check #N` que va contando abajo es
   `GET /api/devices/{id}/check`.
3. **Pasame ese código de 6 caracteres** y yo activo el dispositivo contra la pantalla de prueba
   (`POST /api/admin/devices/activate`).
4. La caja tiene que pasar sola a «Paired with PRUEBA 2B-5 TV Box» y arrancar a reproducir en
   ~1,6 s, sin tocar nada.

## 5. Si algo falla

Mandame, en este orden:
1. Qué paso exacto falló (número de esta lista).
2. La captura del panel de diagnóstico (paso 3).
3. Si podés, `adb logcat -s MediaViewPlayer` de los 2 minutos alrededor del fallo.

Yo tengo en paralelo los logs del backend, así que con el minuto aproximado ubico la request.

## 6. Cuando pase

Decime «pasó la prueba física» y ahí sí fusiono `refactor/fase2-5-player` a `trunk` + `main`
(nunca a `production` sin que lo autorices aparte) y sigo con la 2B-6 (`/admin/*`).

---

### Rutas que esta prueba ejercita (las 16 movidas)

`POST /api/devices/pair` · `POST /api/devices/register` · `GET /api/devices/{id}/check` ·
`POST /api/devices/{id}/heartbeat` · `GET /api/devices/{id}/update-check` ·
`POST /api/devices/{id}/log` · `GET /api/devices/{id}/playlist` ·
`GET /api/player/{screen}/playlist` · `/version` · `/schedule` · `/status` · `/export` ·
`/diagnose` · `/web` · `/test` · `GET /api/player/media/{id}`

Las que el APK no toca por sí solo (`/player/{screen}/web`, `/test`, `/export`, `/diagnose`,
`/schedule`) ya quedaron verificadas por A/B **byte a byte** contra el servidor pre-refactor
(ver `docs/AGENT_COORDINATION.md`, entrada de la Fase 2B-5).
