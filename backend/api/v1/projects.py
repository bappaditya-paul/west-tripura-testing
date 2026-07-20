"""
api/v1/projects.py
==================
Project CRUD endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_db
from backend.middleware.auth import get_current_user
from backend.models.orm import Document, Project
from backend.schemas.project import ProjectCreate, ProjectList, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects")


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = Project(
        owner_id=current_user["sub"],
        name=payload.name,
        description=payload.description,
        vector_db_provider=payload.vector_db_provider,
        embedding_provider=payload.embedding_provider,
        llm_provider=payload.llm_provider,
        config=payload.config,
    )
    db.add(project)
    await db.flush()
    return project


@router.get("", response_model=ProjectList)
async def list_projects(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.owner_id == current_user["sub"]).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    items = []
    for p in projects:
        doc_count_result = await db.execute(select(func.count(Document.id)).where(Document.project_id == p.id))
        doc_count = doc_count_result.scalar() or 0
        out = ProjectOut.model_validate(p)
        out.document_count = doc_count
        items.append(out)
    return ProjectList(items=items, total=len(items))


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == current_user["sub"])
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == current_user["sub"])
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.config is not None:
        project.config = payload.config
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == current_user["sub"])
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
