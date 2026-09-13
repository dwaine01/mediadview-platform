# Cuaderno de notas — mejoras MediaView (sin implementar todavía)

El dueño va dictando ideas desordenadas. Acá se acumulan tal cual, numeradas, para
convertirlas al final en un único prompt maestro de implementación. **Nada de esto está
construido**: mientras una nota no diga «IMPLEMENTADA», sigue siendo pendiente.

---

## Nota #1 — Ficha detallada de la pantalla para el anunciante público

Contexto: una persona pasa por un comercio, ve en la pantalla el aviso «Promociónate aquí»
y escanea el QR.

Flujo pedido:
1. Entra o crea su cuenta de anunciante.
2. Ve **todas las pantallas disponibles** para anunciarse.
3. La plataforma **reconoce la pantalla desde la que escaneó el QR** y la marca aparte:
   «Esta es la pantalla donde estás ahora».
4. Al tocar cualquier pantalla **NO va directo al pago**. Primero se abre una **ficha
   detallada de la ubicación** con:
   - nombre del establecimiento
   - ubicación / dirección
   - ciudad
   - referencia del lugar (cómo ubicarlo)
   - audiencia o tráfico estimado (ej.: 500–700 personas)
   - **fotografía real de la pantalla instalada** dentro del local
5. Desde la ficha puede: «Quiero anunciarme en esta pantalla», seguir eligiendo otras
   pantallas, o volver al listado/mapa.

Finalidad: que el anunciante evalúe exactamente dónde va a aparecer su publicidad **antes**
de pagar.

Estado: **IMPLEMENTADA** (2026-06).

Cómo quedó:
- Panel admin (`web/app.js`, tarjeta «Public marketplace» de cada pantalla): campos nuevos
  Establishment name, How to find it (reference), People/day from–to y Busiest hours, además
  de la foto que ya existía. Endpoint `PUT /api/admin/screens/{id}/advertising`.
- La foto se guarda en `advertising.photo_base64` pero se SIRVE como imagen en
  `GET /api/screens/{id}/venue-photo` (el base64 dentro del JSON son cientos de KB por
  pantalla y el catálogo muestra varias a la vez).
- `GET /api/marketplace/screens?here=MV-ADV-XXXX`: marca `is_here` en la pantalla cuyo QR
  escaneó el anunciante y la pone primera. Filtra las pantallas ocultas del catálogo
  (`advertising.is_public = false`).
- `GET /api/marketplace/screens/{id}` (nuevo): ficha detallada de la ubicación.
- Portal del anunciante (`web/advertising.js`): tarjetas con la foto real, el negocio, la
  ciudad, la referencia y el tráfico; banner «Esta es la pantalla donde estás ahora»; al tocar
  una tarjeta se abre la FICHA (no el pago) y desde ahí: «Quiero anunciarme en esta pantalla»,
  «Seguir eligiendo pantallas» o «Volver al listado».
- Landing del QR (`web/advertise.html`): también muestra la foto instalada, el establecimiento,
  cómo llegar y la gente que pasa.
- Demo: 4 locales con ficha completa (`scripts/seed_public_ad_screens.py`) y 528 pantallas de
  prueba sacadas del catálogo público sin borrarlas.
- Test: `tests/test_nota1_venue_detail.py` (6 casos).

---

## Nota #2 — Mapa por zona y alcance estimado

Pedido del dueño (dos ítems de la lista de próximos pasos):
- «Mostrá las pantallas en un mapa para que el anunciante elija por zona».
- «Calculá cuánta gente vería el anuncio según los días y el horario que elija».

Estado: **IMPLEMENTADA** (2026-06).

Cómo quedó:
- Marketplace del anunciante con dos vistas: **☰ Listado** y **🗺 Mapa** (Leaflet + OpenStreetMap,
  sin llave de API ni costo por vista). Un pin por pantalla: verde la que escaneó, rojo la que
  está llena, índigo las demás. El globo trae foto, establecimiento, ciudad, referencia,
  personas/día, espacios libres y el botón que abre la ficha. Si escaneó un QR el mapa abre
  centrado ahí; si no, encuadra todo el catálogo. Las pantallas sin coordenadas no se esconden:
  se avisa cuántas quedaron sólo en el listado.
- **Alcance estimado** dentro de la ficha: elige días (todos / lunes a viernes / fin de semana),
  franja horaria y duración (1 semana a 1 año) y ve a cuánta gente le llega por día y en toda la
  campaña, más cuántas veces sale su anuncio por hora. `POST /api/marketplace/screens/{id}/reach`.
  La cuenta se muestra escrita («1.000 personas/día × 3 h de las 14 h que abre el local × 20
  días») para que el anunciante pueda rehacerla, y va rotulada como estimación, no como garantía.
  La franja se recorta al horario del local: pedir 00:00–23:00 no inventa gente.
- Campos nuevos en el panel (tarjeta «Public marketplace» de cada pantalla): **Open from / Open
  to** (mueven la calculadora) y **Map coordinates (lat, lng)** (ponen el pin en el mapa).
- Sin tráfico cargado la calculadora NO estima: devuelve 400. Preferimos no dar un número antes
  que dar uno inventado.
- Tests: `tests/test_reach_and_map.py` (7) + `tests/test_iter53_reach_map_edges.py` (12).

---

## Corrección importante (2026-06)

Las Notas #1 y #2 se construyeron primero en el **portal del anunciante del panel**
(`web/advertising.js`, `/api/dashboard#advertiser`) y el dueño no vio nada en producción,
porque la tienda que él revisa —y la que ve el cliente que escanea el QR— es
**`web/customer.html`** en **`/marketplace`**.

Las dos notas ya están portadas a la tienda pública real:
- Tarjetas con la foto del local, establecimiento, ciudad, referencia y personas/día, con el
  banner «Esta es la pantalla donde esta ahora» y la pantalla escaneada primera.
- Vista **☰ Listado / 🗺 Mapa** (Leaflet + OpenStreetMap) con pin verde en la pantalla escaneada.
- **Ficha de la ubicación** (vista `v-venue`) con todos los datos, la calculadora de **alcance
  estimado** y los botones «Quiero anunciarme en esta pantalla» / «Seguir eligiendo pantallas».
  Recién ahí se pasa a los planes y al pago.
- El QR (`advertise.html`) ahora lleva a `/marketplace?code=MV-ADV-XXXX`, no al panel.

Regla para el futuro: antes de implementar algo del recorrido del anunciante, confirmar si va en
`customer.html` (cliente de la calle) o en `advertising.js` (panel del dueño).
