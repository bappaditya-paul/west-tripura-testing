"""
backend/schemas/ingestion.py
============================
Pydantic schemas for /crawl and /ingest/file endpoints.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    url: str = Field(..., description="Target website URL to crawl (e.g., https://westtripura.nic.in)")
    max_pages: Optional[int] = Field(default=100, ge=1, le=2000, description="Maximum number of pages to crawl")


class CrawlResponse(BaseModel):
    status: str = Field(..., description="completed or failed")
    url: str
    pages_crawled: int = 0
    failed: int = 0
    output_dir: str = "output/pages"
    message: Optional[str] = None


class IngestResponse(BaseModel):
    status: str = "completed"
    filename: str
    document_id: str
    chunks_created: int = 0
    embedded_count: int = 0
    pinecone_upserted: int = 0
    bm25_indexed: int = 0
    message: str = "Document successfully ingested and indexed."
