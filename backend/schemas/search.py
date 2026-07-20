"""
schemas/search.py
================
Search, query, and retrieval request/response models.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    project_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] = {}
    use_hybrid: bool = True


class SearchHit(BaseModel):
    id: str
    content: str
    score: float
    title: str = ""
    url: str = ""
    section: str = ""
    metadata: dict[str, Any] = {}


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    total: int
    latency_ms: float
    source: str  # pinecone, duckduckgo, hybrid


class QueryRequest(BaseModel):
    query: str = Field(default="", max_length=2000)
    project_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    stream: bool = False
    session_id: Optional[str] = None
    reset: bool = False


class ReferenceItem(BaseModel):
    title: str
    url: str
    section: str = ""


class QueryResponse(BaseModel):
    answer: str
    references: list[ReferenceItem]
    source_type: str
    latency_ms: float
    session_id: str
