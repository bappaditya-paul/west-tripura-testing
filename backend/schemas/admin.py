"""
schemas/admin.py
===============
Admin request/response models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AdminStats(BaseModel):
    total_users: int
    total_projects: int
    total_documents: int
    total_chunks: int
    total_conversations: int
    vector_db_status: str
    embedding_provider: str
    llm_provider: str
    uptime_seconds: float


class AdminLogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    extra: dict[str, Any] = {}


class VersionInfo(BaseModel):
    version: str
    python: str
    vector_db: str
    embedding: str
    llm: str
