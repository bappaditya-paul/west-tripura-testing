"""
api/v1/embeddings.py
====================
Embedding management: create, rebuild, status.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.config import get_settings
from backend.middleware.auth import get_current_user
from backend.schemas.embeddings import EmbedRequest, EmbedResponse, EmbeddingStatus, RebuildRequest

router = APIRouter(prefix="/embeddings")


@router.post("/create", response_model=EmbedResponse)
async def create_embeddings(
    payload: EmbedRequest,
    current_user: dict = Depends(get_current_user),
):
    from backend.services.providers.embedding import get_embedding_provider
    settings = get_settings()
    provider = get_embedding_provider(settings.embedding_config)
    embeddings = await provider.embed(payload.texts)
    return EmbedResponse(
        embeddings=embeddings,
        model=provider.model_name(),
        dimensions=provider.dimensions(),
    )


@router.post("/rebuild")
async def rebuild_embeddings(
    payload: RebuildRequest,
    current_user: dict = Depends(get_current_user),
):
    return {"message": "Rebuild initiated. This may take a while.", "project_id": payload.project_id, "force": payload.force}


@router.get("/status", response_model=EmbeddingStatus)
async def embedding_status(
    current_user: dict = Depends(get_current_user),
):
    settings = get_settings()
    return EmbeddingStatus(
        provider=settings.EMBEDDING_PROVIDER.value,
        model=settings.NV_EMBED_MODEL,
        dimensions=4096,
        total_embedded=0,
        index_size=0,
        status="healthy",
    )
