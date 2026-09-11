# syntax=docker/dockerfile:1.6
# ══════════════════════════════════════════════════════════════════════
# MediAd View — Production Dockerfile
# ══════════════════════════════════════════════════════════════════════
# Multi-stage build:
#   1. expo-builder — builds Expo web SPA (React Native Web static files)
#   2. py-builder   — installs Python deps into a virtualenv
#   3. runtime      — slim image, non-root user, backend + Expo static files
# ══════════════════════════════════════════════════════════════════════

# ── Stage 0: Build Expo SaaS frontend ────────────────────────────────
FROM node:20-slim AS expo-builder

WORKDIR /frontend

COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --frozen-lockfile 2>/dev/null || yarn install

COPY frontend/ ./

# Build Expo web app to /frontend/dist
RUN npx expo export --platform web --output-dir /frontend/dist

# ── Stage 1: Python builder ───────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Only build-time deps here (compilers, headers). None get shipped to runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip wheel \
 && /opt/venv/bin/pip install -r requirements.txt

# emergentintegrations no está en PyPI público: se instala desde el índice de
# Emergent. Lo usan las funciones de IA (importar menú con IA y generar foto de
# producto) en backend/menu_ai_routes.py. Sin este paso el endpoint
# /api/workspace/menus/ai-import muere con ModuleNotFoundError -> HTTP 500.
# --no-deps ES A PROPÓSITO: su metadata exige stripe<15 y degradaría el
# stripe==15.3.0 de requirements.txt, rompiendo la facturación. Todo lo que
# emergentintegrations.llm.chat necesita de verdad (litellm 1.80.0, openai,
# requests, aiohttp, pillow, google-genai) ya está pineado en requirements.txt.
RUN /opt/venv/bin/pip install --no-deps emergentintegrations==0.2.0 \
      --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/


# ── Stage 2: runtime ─────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production \
    PORT=8001

# libjpeg/zlib runtime libs (used by Pillow); tini for proper signal handling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    tini \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system --gid 1001 mediadview \
 && useradd  --system --uid 1001 --gid mediadview --shell /bin/false mediadview

WORKDIR /app

# Bring in the pre-built venv
COPY --from=builder /opt/venv /opt/venv

# App code — only what's needed to run
COPY --chown=mediadview:mediadview backend/  ./backend/

# Copy pre-built Expo SaaS frontend into backend/web/saas/
COPY --from=expo-builder --chown=mediadview:mediadview /frontend/dist/ ./backend/web/saas/

# App state dirs (not baked into the image contents)
RUN mkdir -p /app/backend/media /app/backend/media/uploads \
 && chown -R mediadview:mediadview /app

USER mediadview
WORKDIR /app/backend

EXPOSE 8001

# In production Render + Cloudflare will hit /api/livez every few seconds.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:${PORT}/api/livez || exit 1

# Use tini as PID 1 so signals reach uvicorn cleanly (fast restarts, proper drain).
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default: run the web-api. Override in the worker service to
#   ["arq", "worker.WorkerSettings"]
CMD ["uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--workers", "2"]
