# --- Stage 1: build wheels in an isolated venv ---
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# --- Stage 2: slim runtime with only what uvicorn + audio libs need ---
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    CACHE_DIR=/data/cache

# Runtime-only deps: libsndfile for soundfile, ffmpeg for librosa/audioread,
# curl for the HEALTHCHECK. Build tools are intentionally NOT included.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && mkdir -p /data/cache \
    && chown -R app:app /data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# Railway probes /api/health; keep the Docker healthcheck in sync so
# `docker run` reports readiness the same way.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# ALLOWED_ORIGINS is intentionally NOT defaulted here — production must set it
# via Railway env vars so a misconfigured deploy fails CORS loudly instead of
# silently allowing localhost. Local dev falls back to main.py's default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
