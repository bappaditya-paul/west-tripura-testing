"""
api/v1/chat.py
==============
Chat and streaming endpoints with conversation memory.
"""

from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.core.config import get_settings
from backend.middleware.auth import get_current_user
from backend.schemas.chat import ChatMessage, ChatRequest, ChatResponse, StreamChunk
from backend.services.rag_service import RAGService

router = APIRouter(prefix="/chat")


def _get_rag() -> RAGService:
    return RAGService.from_settings()


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    rag = _get_rag()
    # Use last user message as query
    last_user_msg = next((m.content for m in reversed(payload.messages) if m.role == "user"), "")
    if not last_user_msg:
        last_user_msg = payload.messages[-1].content if payload.messages else ""

    result = await rag.answer(
        last_user_msg,
        top_k=payload.top_k,
        session_id=payload.session_id,
    )
    return ChatResponse(
        answer=result["answer"],
        references=result["references"],
        source_type=result["source_type"],
        latency_ms=result["latency_ms"],
        session_id=result["session_id"],
    )


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    rag = _get_rag()
    last_user_msg = next((m.content for m in reversed(payload.messages) if m.role == "user"), "")

    async def event_generator():
        async for chunk in rag.answer_stream(last_user_msg, top_k=payload.top_k, session_id=payload.session_id):
            data = json.dumps({"chunk": chunk})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
