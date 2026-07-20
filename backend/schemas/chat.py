"""
schemas/chat.py
==============
Chat and streaming request/response models.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(description="user, assistant, or system")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    project_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    stream: bool = False
    session_id: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)


class ChatResponse(BaseModel):
    answer: str
    references: list[dict[str, Any]]
    source_type: str
    latency_ms: float
    session_id: str
    usage: dict[str, Any] = {}


class StreamChunk(BaseModel):
    chunk: str
    done: bool = False
    references: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
