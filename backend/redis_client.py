# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Redis client + cache layer

- Single async client used across the app (rate-limit, cache, ARQ workers).
- Transparent fallback to an in-process dict when REDIS_URL is unset (dev only).
- Namespaced keys so cache never collides with rate-limit or ARQ queues.

Usage:

    from redis_client import cache, redis_client, ping_redis

    await cache.set("screen:%s" % sid, screen_dict, ttl=60)
    val = await cache.get("screen:%s" % sid)
    await cache.delete("screen:%s" % sid)

    ok = await ping_redis()                 # health check
    raw = await redis_client.get_raw("...") # low-level access
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

log = logging.getLogger("redis_client")

try:
    import redis.asyncio as _aioredis  # redis-py 5.x
    _HAS_REDIS = True
except Exception:
    _aioredis = None
    _HAS_REDIS = False

REDIS_URL       = os.environ.get("REDIS_URL", "").strip()
REDIS_PREFIX    = os.environ.get("REDIS_PREFIX", "mediadview")
REDIS_TIMEOUT   = float(os.environ.get("REDIS_TIMEOUT", "2.0"))


class _MemoryFallback:
    """Tiny in-process replacement for Redis, ONLY suitable for dev/single-worker."""
    def __init__(self):
        self._store: dict = {}
        self._expires: dict = {}
        self._lock = asyncio.Lock()

    def _expired(self, k: str) -> bool:
        exp = self._expires.get(k)
        return exp is not None and exp < time.time()

    async def get(self, k: str) -> Optional[bytes]:
        async with self._lock:
            if self._expired(k):
                self._store.pop(k, None); self._expires.pop(k, None)
                return None
            v = self._store.get(k)
            return v.encode() if isinstance(v, str) else v

    async def set(self, k: str, v, ex: Optional[int] = None, nx: bool = False):
        async with self._lock:
            if nx and k in self._store and not self._expired(k):
                return None
            self._store[k] = v
            if ex:
                self._expires[k] = time.time() + int(ex)
            else:
                self._expires.pop(k, None)
            return True

    async def delete(self, *keys):
        async with self._lock:
            for k in keys:
                self._store.pop(k, None); self._expires.pop(k, None)

    async def ping(self) -> bool:
        return True

    async def close(self): pass
    async def aclose(self): pass


class RedisClient:
    """Thin async wrapper. Auto-detects fallback vs real Redis."""

    def __init__(self):
        self._client = None
        self._is_fallback = False

    async def _connect(self):
        if self._client is not None:
            return
        if REDIS_URL and _HAS_REDIS:
            try:
                self._client = _aioredis.from_url(
                    REDIS_URL,
                    encoding="utf-8", decode_responses=False,
                    socket_connect_timeout=REDIS_TIMEOUT,
                    socket_timeout=REDIS_TIMEOUT,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
                await self._client.ping()
                log.info("✓ Redis connected (%s)", REDIS_URL.split("@")[-1])
                return
            except Exception as e:
                log.warning("Redis connection failed → fallback to in-memory (%s)", e)
        # Fallback
        self._client = _MemoryFallback()
        self._is_fallback = True
        if os.environ.get("ENVIRONMENT") == "production":
            log.error("PRODUCTION Redis fallback active — check REDIS_URL!")

    async def close(self):
        if self._client and hasattr(self._client, "aclose"):
            try: await self._client.aclose()
            except Exception: pass
        self._client = None

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    async def get_raw(self, k: str) -> Optional[bytes]:
        await self._connect()
        try:
            return await self._client.get(k)
        except Exception as e:
            log.warning("redis GET %s failed: %s", k, e)
            return None

    async def set_raw(self, k: str, v, ex: Optional[int] = None):
        await self._connect()
        try:
            await self._client.set(k, v, ex=ex)
        except Exception as e:
            log.warning("redis SET %s failed: %s", k, e)

    async def setnx(self, k: str, v, ex: Optional[int] = None) -> bool:
        """Atomic SET-if-Not-eXists with optional TTL. Returns True iff the
        key was newly created. Used for slot reservations and webhook dedup.

        On network failure returns False (i.e. "the lock is already held")
        so the caller must handle the rejection path defensively — a false
        negative here is safer than a false positive (double-reserve)."""
        await self._connect()
        try:
            result = await self._client.set(k, v, ex=ex, nx=True)
            return bool(result)
        except Exception as e:
            log.warning("redis SETNX %s failed: %s", k, e)
            return False

    async def delete_raw(self, *keys):
        await self._connect()
        try:
            await self._client.delete(*keys)
        except Exception as e:
            log.warning("redis DEL failed: %s", e)

    async def ping(self) -> bool:
        await self._connect()
        try:
            return bool(await self._client.ping())
        except Exception:
            return False


redis_client = RedisClient()


class Cache:
    """JSON-serialising cache built on RedisClient."""

    def __init__(self, prefix: str = REDIS_PREFIX):
        self.prefix = prefix

    def _k(self, k: str) -> str:
        return f"{self.prefix}:cache:{k}"

    async def get(self, k: str) -> Any:
        raw = await redis_client.get_raw(self._k(k))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def set(self, k: str, value: Any, ttl: int = 60):
        try:
            payload = json.dumps(value, default=str)
        except Exception as e:
            log.warning("cache set json fail %s: %s", k, e)
            return
        await redis_client.set_raw(self._k(k), payload, ex=ttl)

    async def delete(self, k: str):
        await redis_client.delete_raw(self._k(k))

    async def delete_prefix(self, prefix: str):
        """Delete every key matching prefix. Only works with real Redis."""
        await redis_client._connect()
        if redis_client.is_fallback:
            # Best-effort in-memory purge
            store = redis_client._client._store
            for k in list(store.keys()):
                if k.startswith(self._k(prefix)):
                    store.pop(k, None)
            return
        # Real redis: SCAN + DEL
        pattern = f"{self._k(prefix)}*"
        cursor = 0
        while True:
            cursor, keys = await redis_client._client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await redis_client._client.delete(*keys)
            if cursor == 0:
                break


cache = Cache()


async def ping_redis() -> dict:
    """Used by /api/ready. Returns {ok, latency_ms, fallback}."""
    t0 = time.monotonic()
    ok = await redis_client.ping()
    return {
        "ok":         ok,
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "fallback":   redis_client.is_fallback,
    }
