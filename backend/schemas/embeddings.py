"""
schemas/embeddings.py
====================
Embedding request/response models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=1000)
    model: str | None = None


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimensions: int
    total_tokens: int = 0


class EmbeddingStatus(BaseModel):
    provider: str
    model: str
    dimensions: int
    total_embedded: int
    index_size: int
    status: str


class RebuildRequest(BaseModel):
    project_id: str | None = None
    force: bool = False
