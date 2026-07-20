"""
api/v1/admin.py
===============
Admin dashboard endpoints: stats, logs, system info.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.engine import get_db
from backend.middleware.auth import get_current_user
from backend.models.orm import Chunk, Conversation, Document, Project, User
from backend.schemas.admin import AdminStats, VersionInfo

router = APIRouter(prefix="/admin")


@router.get("/stats", response_model=AdminStats)
async def admin_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    projects = (await db.execute(select(func.count(Project.id)))).scalar() or 0
    documents = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    chunks = (await db.execute(select(func.count(Chunk.id)))).scalar() or 0
    conversations = (await db.execute(select(func.count(Conversation.id)))).scalar() or 0

    return AdminStats(
        total_users=users,
        total_projects=projects,
        total_documents=documents,
        total_chunks=chunks,
        total_conversations=conversations,
        vector_db_status="healthy",
        embedding_provider=settings.EMBEDDING_PROVIDER.value,
        llm_provider=settings.LLM_PROVIDER.value,
        uptime_seconds=time.time(),
    )


@router.get("/version", response_model=VersionInfo)
async def admin_version():
    import sys
    settings = get_settings()
    return VersionInfo(
        version=settings.APP_VERSION,
        python=sys.version.split()[0],
        vector_db=settings.VECTOR_DB_PROVIDER.value,
        embedding=settings.EMBEDDING_PROVIDER.value,
        llm=settings.LLM_PROVIDER.value,
    )


@router.get("/logs")
async def admin_logs(
    level: str = "info",
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    return {"logs": [], "level": level, "limit": limit, "message": "Log streaming not yet implemented"}
