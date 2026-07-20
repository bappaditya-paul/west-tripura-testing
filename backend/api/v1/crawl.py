"""
api/v1/crawl.py
===============
Web crawler management endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_db
from backend.middleware.auth import get_current_user
from backend.models.orm import CrawlJob
from backend.schemas.crawl import CrawlJobOut, CrawlStartRequest, CrawlStatus

router = APIRouter(prefix="/crawl")


@router.post("/start", response_model=CrawlJobOut, status_code=201)
async def start_crawl(
    payload: CrawlStartRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = CrawlJob(
        project_id=payload.project_id,
        start_url=payload.start_url,
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
        status="pending",
        config={
            "concurrency": payload.concurrency,
            "delay": payload.delay,
        },
    )
    db.add(job)
    await db.flush()
    return job


@router.post("/stop/{job_id}")
async def stop_crawl(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    if job.status != "running":
        raise HTTPException(status_code=400, detail=f"Job is {job.status}, cannot stop")
    job.status = "stopped"
    return {"message": "Crawl job stopped", "job_id": str(job_id)}


@router.get("/status/{job_id}", response_model=CrawlStatus)
async def crawl_status(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    return CrawlStatus(
        job_id=job.id,
        status=job.status,
        pages_crawled=job.pages_crawled,
        max_pages=job.max_pages,
        elapsed_seconds=0,
        pages_per_second=0,
    )


@router.get("/jobs", response_model=list[CrawlJobOut])
async def list_crawl_jobs(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CrawlJob).where(CrawlJob.project_id == project_id).order_by(CrawlJob.created_at.desc())
    )
    return result.scalars().all()
