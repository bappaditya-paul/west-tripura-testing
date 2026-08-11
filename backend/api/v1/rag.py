"""
backend/api/v1/rag.py
======================
Thin router for /search (retrieval debugging) and /chat (RAG response).
"""

from __future__ import annotations

from fastapi import APIRouter
from backend.schemas.rag import SearchRequest, SearchResponse, SearchResultItem, SearchTiming, ChatRequest, ChatResponse, SourceCitation
from backend.services.rag_service import get_rag_service
from backend.services.retrieval_service import RetrievalService

router = APIRouter(tags=["RAG Engine"])
retrieval_service = RetrievalService()


@router.post("/search", response_model=SearchResponse)
async def search_debug(payload: SearchRequest):
    """
    POST /search performs retrieval WITHOUT calling the LLM.
    Returns granular timing metrics and RRF hybrid results for debugging.
    """
    search_data = await retrieval_service.search(query=payload.query, top_k=payload.top_k)

    results_items = []
    for item in search_data["results"]:
        results_items.append(
            SearchResultItem(
                chunk_id=str(item.get("id") or item.get("chunk_id")),
                document_id=item.get("document_id") or item.get("metadata", {}).get("document_id"),
                score=float(item.get("score", 0.0)),
                title=item.get("title") or item.get("metadata", {}).get("title") or "West Tripura Document",
                section=item.get("section") or item.get("metadata", {}).get("section"),
                url=item.get("url") or item.get("metadata", {}).get("url"),
                content=item.get("text") or item.get("content") or "",
                source=item.get("source", "hybrid_rrf"),
            )
        )

    timing_model = SearchTiming(**search_data["timing"])

    return SearchResponse(
        query=search_data["query"],
        retrieval_query=search_data["retrieval_query"],
        language=search_data["language"],
        results=results_items,
        timing=timing_model,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_rag(payload: ChatRequest):
    """
    POST /chat executes full citizen RAG pipeline:
    Query Preprocessing ➔ RRF Hybrid Search ➔ Context Expansion ➔ LLM Answer + Sources.
    """
    rag_service = get_rag_service()
    result = await rag_service.answer(query=payload.query, top_k=payload.top_k, session_id=payload.session_id)

    source_models = [
        SourceCitation(
            title=src["title"],
            url=src.get("url"),
            section=src.get("section"),
            chunk_id=src.get("chunk_id"),
        )
        for src in result.get("sources", [])
    ]

    return ChatResponse(
        answer=result["answer"],
        sources=source_models,
        retrieval_query=result.get("retrieval_query"),
        timing_ms=result.get("timing_ms", 0.0),
        session_id=result.get("session_id"),
    )
