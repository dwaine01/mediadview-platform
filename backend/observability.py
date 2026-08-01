"""
MediAd View — Structured logging + Sentry integration

- JSON-line logs when ENVIRONMENT=production (Render / Cloudflare Logpush ingest fine)
- Pretty console logs in dev
- Every log entry carries request_id + user_id when inside an HTTP request
- Sentry init with strict PII scrubbing:
   • never sent: passwords, cookies, tokens, card numbers, emails, full request bodies
   • before_send hook drops anything matching a regex list
"""
import os
import re
import sys
import json
import time
import uuid
import logging
import contextvars
from typing import Any

# ─── Context vars for request-scoped fields ───────────────────────────
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_user_id:    contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id",    default=None)

def bind_request(request_id: str, user_id: str | None = None):
    _request_id.set(request_id); _user_id.set(user_id)

def clear_request():
    _request_id.set(None); _user_id.set(None)

# ─── Redaction ────────────────────────────────────────────────────────
_SECRET_KEYS = re.compile(
    r"^(?:password|passwd|secret|api[_-]?key|token|jwt|authorization|cookie|"
    r"stripe.*key|.*webhook.*secret|refresh_token|access_token|card.*number|cvv|cvc)$",
    re.IGNORECASE,
)
_CARD_RX  = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_EMAIL_RX = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_JWT_RX   = re.compile(r"\beyJ[a-zA-Z0-9_\-]{5,}\.[a-zA-Z0-9_\-]{5,}\.[a-zA-Z0-9_\-]+\b")


def _redact(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        s = _CARD_RX.sub("[CARD]", obj)
        s = _JWT_RX.sub("[JWT]", s)
        s = _EMAIL_RX.sub(lambda m: (m.group(0).split("@")[0][:2] + "***@" + m.group(0).split("@")[1]), s)
        return s
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEYS.match(k):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(v, depth + 1) for v in obj][:50]
    return _redact(str(obj), depth + 1)

# ─── JSON formatter ──────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    _reserved = {
        "name","msg","args","levelname","levelno","pathname","filename","module","exc_info",
        "exc_text","stack_info","lineno","funcName","created","msecs","relativeCreated","thread",
        "threadName","processName","process","message","asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts":     time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        rid = _request_id.get()
        if rid:
            base["request_id"] = rid
        uid = _user_id.get()
        if uid:
            base["user_id"] = uid
        # Include any custom fields added with `extra=`
        for k, v in record.__dict__.items():
            if k in self._reserved or k.startswith("_"):
                continue
            try:
                base[k] = _redact(v)
            except Exception:
                pass
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        try:
            return json.dumps(base, default=str, ensure_ascii=False)
        except Exception:
            return json.dumps({"ts": base["ts"], "level": base["level"],
                               "msg": str(record.getMessage())})

# ─── Pretty console formatter for dev ────────────────────────────────
class PrettyFormatter(logging.Formatter):
    _colors = {"DEBUG":"\033[36m","INFO":"\033[32m","WARNING":"\033[33m",
               "ERROR":"\033[31m","CRITICAL":"\033[1;31m"}
    def format(self, record):
        c   = self._colors.get(record.levelname, "")
        rid = _request_id.get()
        uid = _user_id.get()
        pref = f"[{rid[:8]}]" if rid else ""
        upref = f"({uid[:8]})" if uid else ""
        base = f"{c}{record.levelname:5}\033[0m {record.name:22} {pref}{upref} {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging():
    """Configure the root logger once at startup."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    env = os.environ.get("ENVIRONMENT", "development")

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if env == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(PrettyFormatter())

    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third parties in prod
    for noisy in ("uvicorn.access", "apscheduler.executors.default",
                  "apscheduler.scheduler", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING if env == "production" else logging.INFO)


# ─── Sentry integration ──────────────────────────────────────────────
def init_sentry():
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logging.getLogger("sentry").info("SENTRY_DSN not set — Sentry disabled")
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.pymongo import PyMongoIntegration
    except Exception as e:
        logging.getLogger("sentry").warning("sentry_sdk not installed: %s", e)
        return False

    env = os.environ.get("ENVIRONMENT", "development")
    release = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("APP_RELEASE") or None

    def _scrub(event, hint):
        """Drop every PII field from the event before it leaves the process."""
        try:
            # 1) remove user email/ip precise
            u = event.get("user") or {}
            if isinstance(u, dict):
                u.pop("email", None); u.pop("ip_address", None)
                event["user"] = u
            # 2) redact request body/cookies/headers
            req = event.get("request") or {}
            if isinstance(req, dict):
                req.pop("cookies", None)
                headers = req.get("headers") or {}
                if isinstance(headers, dict):
                    for h in list(headers):
                        if h.lower() in ("authorization","cookie","set-cookie","x-api-key"):
                            headers[h] = "[REDACTED]"
                    req["headers"] = headers
                if req.get("data"):
                    req["data"] = _redact(req["data"])
                event["request"] = req
            # 3) redact extra + breadcrumbs
            if event.get("extra"):
                event["extra"] = _redact(event["extra"])
            for b in (event.get("breadcrumbs") or {}).get("values", []) or []:
                if b.get("data"):
                    b["data"] = _redact(b["data"])
                if b.get("message"):
                    b["message"] = _redact(b["message"])
            # 4) redact exception values (may contain user data)
            for x in (event.get("exception") or {}).get("values", []) or []:
                if x.get("value"):
                    x["value"] = _redact(x["value"])
        except Exception:
            pass
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        release=release,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_RATE", "0.0")),
        send_default_pii=False,   # strict — never send IPs/emails
        max_breadcrumbs=50,
        attach_stacktrace=True,
        before_send=_scrub,
        before_send_transaction=_scrub,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            PyMongoIntegration(),
        ],
    )
    logging.getLogger("sentry").info("✓ Sentry initialized (env=%s, release=%s)", env, release or "n/a")
    return True


# ─── FastAPI middleware for request_id + response header ─────────────
def install_request_id_middleware(app):
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            rid = request.headers.get("x-request-id") or uuid.uuid4().hex
            bind_request(rid)
            try:
                response: Response = await call_next(request)
            finally:
                clear_request()
            response.headers["x-request-id"] = rid
            return response

    app.add_middleware(RequestIdMiddleware)
