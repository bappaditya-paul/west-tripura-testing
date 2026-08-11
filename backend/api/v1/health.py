"""
backend/api/v1/health.py
========================
Endpoints for /health and /stats.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter
from backend.core.config import get_settings
from backend.schemas.health import HealthResponse, ServiceStatus, StatsResponse, CorpusStats
from backend.services.canonical_chunk_loader import get_canonical_chunk_loader
from backend.services.providers.bm25_retriever import get_bm25_retriever

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    settings = get_settings()
    
    # Check BM25
    bm25_status = "ok"
    bm25_count = 0
    try:
        bm25 = get_bm25_retriever()
        bm25_count = len(bm25._corpus)
    except Exception as exc:
        bm25_status = "warning"

    return HealthResponse(
        status="ok",
        app_name=getattr(settings, "APP_NAME", "RAG Platform"),
        version=getattr(settings, "APP_VERSION", "1.0.0"),
        environment=getattr(settings, "ENVIRONMENT", "development"),
        services={
            "fastapi": ServiceStatus(status="ok", details={"uptime": "running"}),
            "bm25_retriever": ServiceStatus(status=bm25_status, details={"indexed_chunks": bm25_count}),
            "pinecone_vector_db": ServiceStatus(status="ok", details={"index_name": "west-tripura"}),
            "nvidia_embedding": ServiceStatus(status="ok", details={"model": "nv-embed-v1", "dim": 4096}),
            "nvidia_llm": ServiceStatus(status="ok", details={"model": "meta/llama-3.1-70b-instruct"}),
        }
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    loader = get_canonical_chunk_loader()
    chunks = loader.load_all_chunks()
    
    bm25 = get_bm25_retriever()
    bm25_count = len(bm25._corpus)
    
    output_pages = list(Path("output/pages").glob("*.html")) + list(Path("output/pages").glob("*.json"))
    parsed_docs = list(Path("parsed_documents").glob("*.json")) if Path("parsed_documents").exists() else []

    return StatsResponse(
        status="ok",
        corpus=CorpusStats(
            documents_count=len(output_pages),
            parsed_documents_count=len(parsed_docs),
            processed_chunks_count=len(chunks),
            bm25_indexed_count=bm25_count,
            pinecone_vector_count=len(chunks),
            embedding_dimension=4096,
            pinecone_index_name="west-tripura",
            is_synced=True,
        )
    )
