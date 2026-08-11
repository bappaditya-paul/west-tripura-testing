"""
backend/api/v1/ingestion.py
============================
Thin router for /crawl and /ingest/file endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile, HTTPException
from backend.schemas.ingestion import CrawlRequest, CrawlResponse, IngestResponse
from backend.services.ingestion_service import IngestionService

router = APIRouter(tags=["Ingestion"])
ingestion_service = IngestionService()


@router.post("/crawl", response_model=CrawlResponse)
async def crawl_website(payload: CrawlRequest):
    """
    POST /crawl MUST ONLY perform website crawling to output/pages/.
    Does NOT perform chunking, embedding, or indexing.
    """
    if not payload.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid target URL. Must start with http:// or https://")

    result = await ingestion_service.run_crawl_only(target_url=payload.url, max_pages=payload.max_pages or 100)
    return CrawlResponse(**result)


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(file: UploadFile = File(...)):
    """
    POST /ingest/file accepts document upload, parses text into processed_chunks/,
    embeds vector, and updates Pinecone and BM25.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a valid filename.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = await ingestion_service.ingest_uploaded_file(filename=file.filename, content=content)
    return IngestResponse(**result)
