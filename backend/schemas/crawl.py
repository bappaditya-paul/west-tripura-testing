"""
schemas/crawl.py
===============
Crawler request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CrawlStartRequest(BaseModel):
    project_id: UUID
    start_url: str = Field(description="Seed URL to begin crawling")
    max_depth: int = Field(default=5, ge=1, le=10)
    max_pages: int = Field(default=2000, ge=1, le=50000)
    concurrency: int = Field(default=3, ge=1, le=10)
    delay: float = Field(default=1.5, ge=0.1, le=10.0)


class CrawlJobOut(BaseModel):
    id: UUID
    project_id: UUID
    start_url: str
    max_depth: int
    max_pages: int
    status: str
    pages_crawled: int
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CrawlStatus(BaseModel):
    job_id: UUID
    status: str
    pages_crawled: int
    max_pages: int
    elapsed_seconds: float
    pages_per_second: float
