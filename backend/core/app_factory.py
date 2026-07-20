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
    from backend.api.v1.auth import router as auth_router
    from backend.api.v1.projects import router as projects_router
    from backend.api.v1.documents import router as documents_router
    from backend.api.v1.crawl import router as crawl_router
    from backend.api.v1.embeddings import router as embeddings_router
    from backend.api.v1.search import router as search_router
    from backend.api.v1.chat import router as chat_router
    from backend.api.v1.admin import router as admin_router
    from backend.api.v1.feedback import router as feedback_router

    prefix = settings.API_V1_PREFIX
    app.include_router(health_router)
    app.include_router(auth_router, prefix=prefix, tags=["Authentication"])
    app.include_router(projects_router, prefix=prefix, tags=["Projects"])
    app.include_router(documents_router, prefix=prefix, tags=["Documents"])
    app.include_router(crawl_router, prefix=prefix, tags=["Crawler"])
    app.include_router(embeddings_router, prefix=prefix, tags=["Embeddings"])
    app.include_router(search_router, prefix=prefix, tags=["Search & Query"])
    app.include_router(chat_router, prefix=prefix, tags=["Chat"])
    app.include_router(feedback_router, prefix=prefix, tags=["Feedback & Evaluation"])
    app.include_router(admin_router, prefix=prefix, tags=["Admin"])

    return app
