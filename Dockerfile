FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── System dependencies ──────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# ── Python dependencies (cached layer) ──────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Create non-root user ───────────────────────────────────────────────
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# ── Application code ─────────────────────────────────────────────────────
COPY backend/ backend/
COPY telegram_bot.py .

# ── Chunk data for BM25 search ──────────────────────────────────────────
COPY output/chunks/chunks.jsonl output/chunks/chunks.jsonl

# ── Create required directories ──────────────────────────────────────────
RUN mkdir -p uploads output processed_documents processed_chunks && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# ── Healthcheck ──────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
