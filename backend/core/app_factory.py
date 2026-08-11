"""
core/app_factory.py
===================
Application factory — builds FastAPI app with middleware, routers, lifespan.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings
from backend.middleware.logging import RequestLoggingMiddleware
from backend.middleware.rate_limit import RateLimitMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ──
        from backend.db.engine import init_db, close_db

        app.state.settings = settings
        app.state.start_time = time.time()

        try:
            await init_db()
        except Exception as e:
            import logging
            logging.getLogger("ragplatform").warning(
                "Database init failed (will retry on first request): %s", e
            )

        yield

        # ── Shutdown ──
        try:
            await close_db()
        except Exception:
            pass

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Reusable RAG Platform API. "
            "Upload documents, crawl websites, embed content, and query with LLMs."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom Middleware ────────────────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=settings.RATE_LIMIT_PER_MINUTE)

    # ── Exception Handlers ───────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": str(exc),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    # ── Register API Routers ─────────────────────────────────────────────
    from backend.api.v1.health import router as health_router
    from backend.api.v1.ingestion import router as ingestion_router
    from backend.api.v1.rag import router as rag_router

    app.include_router(health_router)
    app.include_router(ingestion_router)
    app.include_router(rag_router)

    return app
