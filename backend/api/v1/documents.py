"""
api/v1/documents.py
===================
Document upload, URL ingestion, listing, deletion, and reindexing.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.db.engine import get_db
from backend.middleware.auth import get_current_user
from backend.models.orm import Document
from backend.schemas.document import DocumentList, DocumentOut, DocumentReindexRequest, DocumentURLEntry, DocumentUploadResponse

router = APIRouter(prefix="/documents")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".md", ".txt", ".html", ".csv"}


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    settings = get_settings()
    upload_dir = settings.UPLOAD_DIR / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    save_path = upload_dir / f"{file_id}{ext}"
    content = await file.read()
    save_path.write_bytes(content)

    doc = Document(
        id=file_id,
        project_id=project_id,
        filename=file.filename,
        doc_type=ext.lstrip("."),
        status="pending",
        char_count=len(content.decode("utf-8", errors="ignore")),
    )
    db.add(doc)
    await db.flush()

    return DocumentUploadResponse(id=doc.id, filename=doc.filename, status=doc.status, message="Document uploaded. Processing will begin shortly.")


@router.post("/url", response_model=DocumentUploadResponse, status_code=201)
async def add_document_url(
    project_id: UUID,
    payload: DocumentURLEntry,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = Document(
        project_id=project_id,
        filename=payload.filename or payload.url.split("/")[-1],
        source_url=payload.url,
        doc_type="url",
        status="pending",
    )
    db.add(doc)
    await db.flush()
    return DocumentUploadResponse(id=doc.id, filename=doc.filename, status=doc.status, message="URL queued for processing.")


@router.get("", response_model=DocumentList)
async def list_documents(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return DocumentList(items=[DocumentOut.model_validate(d) for d in docs], total=len(docs))


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)


@router.post("/reindex")
async def reindex_documents(
    payload: DocumentReindexRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id.in_(payload.document_ids)))
    docs = result.scalars().all()
    count = 0
    for doc in docs:
        doc.status = "pending"
        count += 1
    return {"message": f"{count} documents queued for reindexing.", "document_ids": [str(d.id) for d in docs]}
