# MediAd View — Escalado de WebSockets a múltiples réplicas

> Cómo pasar de 1 instancia del `web-api` a N réplicas sin perder los
> mensajes en tiempo real que se envían a las pantallas TV / APK / editor
> de menú.

---

## 1. Situación actual (1 instancia)

Todo el broadcast de eventos vive en memoria dentro de `realtime.py`:

```
Admin edita menú → server.py PUT /menus/{id}
                 → ws_manager.broadcast_menu(id, "updated")
                 → itera set() en memoria de sockets conectados a ese menú
                 → cada TV recibe "reload" y se recarga
```

Funciona perfecto **mientras haya una sola instancia**. Con dos réplicas
(load-balanced por Render/Cloudflare) las TVs conectadas a la réplica A
no se enteran cuando el admin edita desde la réplica B.

## 2. Solución: Redis Pub/Sub

Redis actúa como bus de mensajería:

```
      ┌──────────────┐          publish            ┌─────────────┐
      │  web-api A   │──────────────────────────►  │             │
      │  (admin edit)│                             │   Redis     │
      └──────────────┘                             │  channel:   │
                                                   │  mediadview:│
      ┌──────────────┐        subscribe            │  broadcast  │
      │  web-api B   │◄─────────────────────────── │             │
      │  (TV conected│                             └─────────────┘
      └──────────────┘                                   ▲
                                                         │ publish
      ┌──────────────┐                                   │
      │   worker     │───────────────────────────────────┘
      │  (job done)  │
      └──────────────┘
```

Los `web-api` publican **y** se suscriben. Cada réplica recibe la señal y
reenvía a sus sockets locales.

## 3. Implementación (cuando escalemos)

Reemplazar el `_broadcast()` interno de `ConnectionManager` en
`/app/backend/realtime.py` para que empuje al canal Redis en vez de
iterar sockets locales; añadir un consumer en el startup que reciba
del canal y haga la difusión local:

```python
# /app/backend/realtime.py — modificación futura
import asyncio, json, logging
from redis_client import redis_client

CHANNEL = "mediadview:broadcast"
log = logging.getLogger("realtime")


class ConnectionManager:
    # ... resto igual ...

    async def _local_broadcast(self, key: str, payload: dict):
        """Send to sockets connected to THIS instance only."""
        dead = []
        for ws in list(self._rooms.get(key, set())):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead: self._rooms.get(key, set()).discard(ws)

    async def _broadcast(self, key: str, payload: dict):
        """Publish so EVERY instance's subscriber (including us) sees it."""
        try:
            await redis_client._connect()
            await redis_client._client.publish(
                CHANNEL, json.dumps({"key": key, "payload": payload})
            )
        except Exception as e:
            log.warning("pubsub publish failed → local only: %s", e)
            await self._local_broadcast(key, payload)


async def start_pubsub_bridge():
    """Startup coroutine: subscribe to CHANNEL and fan-out to local sockets."""
    await redis_client._connect()
    if redis_client.is_fallback:
        log.warning("Redis in fallback mode — pubsub bridge disabled")
        return
    pubsub = redis_client._client.pubsub()
    await pubsub.subscribe(CHANNEL)
    log.info("✓ pubsub bridge subscribed to %s", CHANNEL)
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            await manager._local_broadcast(data["key"], data["payload"])
        except Exception as e:
            log.warning("pubsub bridge dispatch error: %s", e)


# In server.py startup:
#   asyncio.create_task(start_pubsub_bridge())
```

## 4. Pasos de activación

1. **Escalar el servicio en Render**
   - Dashboard → `mediadview-api` → Scaling → Number of Instances → `2` (o más).
   - Render reparte tráfico automáticamente.

2. **Aplicar el diff de `realtime.py`** de la sección 3.

3. **Añadir `asyncio.create_task(start_pubsub_bridge())`** en el bloque
   `startup()` de `server.py`, justo después de `ensure_auth_indexes(db)`.

4. **Redeploy**. En logs de cada instancia debe aparecer:
   ```
   ✓ pubsub bridge subscribed to mediadview:broadcast
   ```

5. **Verificación end-to-end**:
   - Instancia A: `curl -X PUT /api/menus/{id} -d '{"subtitle":"test"}'`
   - Cliente WS conectado a instancia B (usar `wscat` con `--origin`):
     debe recibir `{"type":"menu","event":"updated","menu_id":"..."}`
     en < 500 ms.

## 5. Consideraciones adicionales

### Sticky sessions no son necesarias
Cloudflare + Render pueden repartir cada request/WS a la instancia menos
cargada; la persistencia de la sesión se resuelve con:
- Access token (Bearer) — stateless.
- Refresh cookie — la valida cualquier instancia contra Mongo.
- Rate limiting — via Redis (ya en `slowapi`).

### Failure modes
- **Redis caído**: el `_broadcast` cae a `_local_broadcast` (log de
  warning). Los usuarios conectados a la misma instancia que hizo el
  cambio ven la actualización; los de otras instancias no la ven hasta
  que Redis vuelve.
- **Instancia matada mid-publish**: Redis Pub/Sub es *fire-and-forget*
  (no hay persistencia). Aceptable para `reload`/`updated` porque siempre
  hay fallback: la TV recarga por su timer de 5 min y detecta el cambio.
  Para eventos que NO deben perderse (pagos, contratos), usa Redis
  Streams o pon el evento en Mongo y notifica.

### Autenticación del WS
El endpoint `/api/ws/{channel}/{rid}` es actualmente público (por
diseño: el APK y las TVs se conectan sin token). Cuando implementemos
canales privados (dashboard admin), el cliente debe enviar el JWT en el
subprotocol `Sec-WebSocket-Protocol` o como query string firmada:
```
ws://.../api/ws/admin/{sid}?ticket=<one-shot-token>
```
El ticket se emite via `POST /api/auth/v2/ws-ticket`, expira en 60 s.
Documentar en Fase 6 si el panel admin va detrás del WS también.

### Métricas a monitorear
- `mediadview:broadcast` messages/second (Sentry o Prometheus)
- Sockets abiertos por instancia (`ConnectionManager.room_size`)
- Redis pubsub lag (Redis INFO stats)

---

## 6. Cuándo activar esto

- **Ahora (1 instancia)**: NO se necesita. Todo funciona.
- **>50 pantallas TV concurrentes**: aún es viable con 1 instancia Starter.
- **>500 pantallas / lat > 200 ms**: escalar a 2-3 instancias y aplicar
  este cambio.
- **Producción multi-región**: obligatorio + subscribir a canales
  federados (Redis Enterprise Active-Active o similar).

**Costo estimado del cambio**: 40-60 líneas de código (mostradas arriba)
+ 15 min de deploy. Cero migración de datos.
