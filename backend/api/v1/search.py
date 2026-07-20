"""
api/v1/search.py
================
Search, query, and rerank endpoints.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from backend.core.config import get_settings
from backend.middleware.auth import get_current_user
from backend.schemas.search import QueryRequest, QueryResponse, ReferenceItem, SearchHit, SearchRequest, SearchResponse
from backend.services.rag_service import RAGService

router = APIRouter(prefix="")


def _get_rag() -> RAGService:
    return RAGService.from_settings()


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    current_user: dict = Depends(get_current_user),
):
    rag = _get_rag()
    start = time.perf_counter()
    matches = await rag.retrieve(payload.query, top_k=payload.top_k)
    latency_ms = (time.perf_counter() - start) * 1000

    hits = [
        SearchHit(
            id=m.get("id", ""),
            content=m.get("content", ""),
            score=m.get("score", 0),
            title=m.get("title", ""),
            url=m.get("url", ""),
            section=m.get("section", ""),
            metadata=m.get("metadata", {}),
        )
        for m in matches
    ]
    return SearchResponse(query=payload.query, hits=hits, total=len(hits), latency_ms=round(latency_ms, 1), source="vector_db")


@router.post("/query", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    rag = _get_rag()
    result = await rag.answer(payload.query, top_k=payload.top_k, session_id=payload.session_id, reset=payload.reset)
    return QueryResponse(
        answer=result["answer"],
        references=[ReferenceItem(**r) for r in result["references"]],
        source_type=result["source_type"],
        latency_ms=result["latency_ms"],
        session_id=result["session_id"],
    )
