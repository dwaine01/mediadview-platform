# syntax=docker/dockerfile:1.6
# ══════════════════════════════════════════════════════════════════════
# MediAd View — Backend Dockerfile (production-grade)
# ══════════════════════════════════════════════════════════════════════
# Multi-stage build:
#   1. builder  — installs Python deps into a virtualenv
#   2. runtime  — slim image, non-root user, only the venv + app code
#
# Same image serves the web-api AND the worker (different CMD).
# See docker-compose.yml / render.yaml for the concrete entrypoints.
#
# Build:   docker build -t mediadview-backend:latest .
# Run api: docker run -p 8001:8001 --env-file .env mediadview-backend
# Run wrk: docker run --env-file .env mediadview-backend arq worker.WorkerSettings
# ══════════════════════════════════════════════════════════════════════

# ── Stage 1: builder ─────────────────────────────────────────────────
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
