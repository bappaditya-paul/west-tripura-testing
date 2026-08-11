"""
backend/schemas/health.py
==========================
Pydantic models for /health and /stats endpoints.
"""

from __future__ import annotations

from typing import Dict, Any
from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    status: str = Field(..., description="ok, warning, or error")
    details: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall system health status")
    app_name: str
    version: str
    environment: str
    services: Dict[str, ServiceStatus]


class CorpusStats(BaseModel):
    documents_count: int = 0
    parsed_documents_count: int = 0
    processed_chunks_count: int = 0
    bm25_indexed_count: int = 0
    pinecone_vector_count: int = 0
    embedding_dimension: int = 4096
    pinecone_index_name: str = "west-tripura"
    is_synced: bool = True


class StatsResponse(BaseModel):
    status: str = "ok"
    corpus: CorpusStats
