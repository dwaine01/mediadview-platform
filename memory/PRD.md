# MediaView / MediAd View — PRD técnico

## Problema y objetivo

MediaView debe operar como una plataforma SaaS de señalización digital 24/7:

1. El Android TV no puede depender de una pantalla WebView para emparejarse o
   reproducir video, porque ciertos equipos quedaban negros sin diagnóstico.
2. Los clientes necesitan administrar contenido cotidiano mediante **Playlists**
   de menús, fotos y videos, con duración, horario y asignación directa a pantallas.
3. Las Playlists deben permanecer separadas de las **Campaigns** publicitarias pagadas.

## Arquitectura

- **Backend:** FastAPI + MongoDB; rutas bajo `/api`.
- **Panel:** HTML/CSS/JavaScript servido por FastAPI.
- **Player Android:** Kotlin; pairing nativo, Media3/ExoPlayer para video, Coil para
  imágenes, WebView aislado únicamente para menús HTML/widgets y Room para caché.
- **Actualización:** SSE por pantalla con reconexión y polling cada 15 segundos como respaldo.
- **Entrega Android:** Codemagic; el contenedor local no compila Android.

## Implementado

### Player Android nativo

- Pairing nativo idempotente e identidad persistente; no se regresó al pairing WebView.
- Playlist canónica, checksums SHA-256, versiones y URLs compatibles.
- ExoPlayer/Coil por tipo de medio; estado visible hasta primer frame o decode correcto.
- Room, descargas temporales, validación de integridad y última playlist válida offline.
- NetworkCallback, reintentos con backoff, watchdog, timeout de preparación, recuperación
  de crash, heartbeat, WorkManager y BootReceiver.
- HUD con URL, screen_id, pairing, HTTP, error de renderer, red, estado realtime y última sync.
- SSE `playlist.updated` provoca sincronización inmediata; polling de 15 s recupera eventos perdidos.

### Playlists profesionales

- CRUD de Playlists de contenido propio, separado de Campaigns.
- Mezcla ordenada de menús, imágenes y videos con duración individual.
- Publicación directa a una o varias pantallas.
- Programación por zona horaria, días, horas, fecha inicial/final y prioridad.
- Gestión admin/client, preparación desde un menú, enlaces/QR seguros y aportes públicos aprobables.
- Estado de entrega online/offline calculado desde el heartbeat real del dispositivo.
- Editar un menú actualiza la versión del playlist y avisa inmediatamente a cada TV asignado.
- Se bloquea borrar un menú usado por playlists, mostrando las dependencias.
- Drawer móvil, editor, modal de publicación y estados de guardado corregidos.

### Sesión web

- Rutas protegidas responden `401` + `WWW-Authenticate: Bearer` cuando falta o falla el token.
- Un refresh vencido cancela la llamada, limpia la sesión y muestra login sin dejar el panel activo.
- Access token permanece en memoria y refresh token en cookie HttpOnly.

## Verificación actual

- QA independiente Iteración 9: **9/9 contratos backend** y **100% del flujo móvil crítico**.
- Verificado: CRUD, programación, múltiples pantallas, versionado, SSE, heartbeats,
  dependencias de menú y autenticación 401.
- Verificado a 390x844: login, drawer, Playlists, crear, añadir menú, guardar y configurar publicación.
- Revisión estática Kotlin: sin bloqueadores evidentes; pairing nativo intacto.
- Compilación Android local no ejecutada por diseño; corresponde a Codemagic.

## Estado de publicación

- **Entorno de trabajo/preview:** contiene y sirve todos los cambios anteriores.
- **Producción `panel.mediadview.com`: no contiene todavía Playlists.** La comprobación devolvió
  `404` para `/api/playlists` y `/api/web/playlists.js`.
- Para publicar se requiere guardar/sincronizar esta versión con GitHub y esperar el despliegue
  de Render; después debe verificarse nuevamente producción.
- El APK que incluye SSE debe compilarse en Codemagic y probarse en el Android TV físico.

## Prioridades

### P0 — publicación y aceptación

- Sincronizar la versión actual con GitHub mediante **Save to Github** sin force push.
- Confirmar despliegue verde en Render y que producción sirve Playlists/SSE.
- Confirmar build verde de Codemagic e instalar el APK diagnóstico generado.
- En TV físico: publicar/cambiar una playlist y confirmar actualización inmediata más modo offline.

### P1 — robustez operativa

- Prueba soak de 24–72 horas con cortes WAN, reinicios y cambios repetidos de playlist.
- Convertir la build aceptada a release con diagnósticos visuales desactivados.
- Modularizar `backend/server.py` para reducir el riesgo de regresión del monolito.

### P2 — flota y almacenamiento

- Cloudflare R2/almacenamiento persistente para archivos; hoy existe fallback local/base64.
- Métricas y comandos remotos ampliados por dispositivo.
- Aprovisionamiento Device Owner/OEM para autoarranque e instalación silenciosa garantizados.

### Backlog

- Stripe LIVE (actualmente **MOCKED/DESACTIVADO**), D-04 multi-moneda y D-05 presign worker.