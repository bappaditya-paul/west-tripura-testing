"""
api/v1/health.py
================
Health, readiness, liveness, and version endpoints.
"""

from __future__ import annotations

import time
import sys
from pathlib import Path

from fastapi import APIRouter

from backend.core.config import get_settings

router = APIRouter()


@router.get("/health", tags=["Monitoring"])
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "message": f"{settings.APP_NAME} is healthy.",
        "version": settings.APP_VERSION,
    }


@router.get("/ready", tags=["Monitoring"])
async def readiness():
    checks = {"database": "ok", "redis": "ok", "vector_db": "ok"}
    try:
        from backend.db.engine import get_engine
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "not_ready"

    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception as e:
        checks["redis"] = f"error: {e}"
        checks["status"] = "not_ready"

    if "status" not in checks:
        checks["status"] = "ready"

    return checks


@router.get("/live", tags=["Monitoring"])
async def liveness():
    return {
        "status": "alive",
        "uptime": time.time(),
    }


@router.get("/version", tags=["Monitoring"])
async def version():
    settings = get_settings()
    return {
        "version": settings.APP_VERSION,
        "python": sys.version.split()[0],
        "vector_db": settings.VECTOR_DB_PROVIDER.value,
        "embedding": settings.EMBEDDING_PROVIDER.value,
        "llm": settings.LLM_PROVIDER.value,
    }
