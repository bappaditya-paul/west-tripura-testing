"""
schemas/project.py
=================
Project request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    vector_db_provider: str = "pinecone"
    embedding_provider: str = "nvidia"
    llm_provider: str = "nvidia"
    config: dict[str, Any] = {}


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class ProjectOut(BaseModel):
    id: UUID
    name: str
    description: str
    vector_db_provider: str
    embedding_provider: str
    llm_provider: str
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectList(BaseModel):
    items: list[ProjectOut]
    total: int
