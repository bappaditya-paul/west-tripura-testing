"""
schemas/document.py
==================
Document request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    id: UUID
    filename: str
    status: str
    message: str


class DocumentURLEntry(BaseModel):
    url: str
    filename: Optional[str] = None


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    source_url: Optional[str]
    doc_type: str
    status: str
    chunk_count: int
    char_count: int
    metadata_: dict[str, Any] = {}
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


class DocumentReindexRequest(BaseModel):
    document_ids: list[UUID]
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
