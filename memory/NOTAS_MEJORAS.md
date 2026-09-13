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
