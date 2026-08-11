"""
backend/schemas/rag.py
======================
Pydantic schemas for /search (retrieval debugging) and /chat (RAG query).
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User search query (English, Bengali, Benglish)")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to retrieve")


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: Optional[str] = None
    score: float
    title: str = "West Tripura Document"
    section: Optional[str] = None
    url: Optional[str] = None
    content: str
    source: str = "hybrid_rrf"  # pinecone, bm25, or hybrid_rrf


class SearchTiming(BaseModel):
    query_processing_ms: float = 0.0
    embedding_ms: float = 0.0
    pinecone_ms: float = 0.0
    bm25_ms: float = 0.0
    fusion_ms: float = 0.0
    total_ms: float = 0.0


class SearchResponse(BaseModel):
    query: str
    retrieval_query: str
    language: str = "en"
    results: List[SearchResultItem]
    timing: SearchTiming


class SourceCitation(BaseModel):
    title: str
    url: Optional[str] = None
    section: Optional[str] = None
    chunk_id: Optional[str] = None


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Citizen question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve for context")
    session_id: Optional[str] = Field(default=None, description="Optional conversation session identifier")


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceCitation]
    retrieval_query: Optional[str] = None
    timing_ms: float = 0.0
    session_id: Optional[str] = None
