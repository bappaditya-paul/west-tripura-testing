"""
schemas/feedback.py
==================
Feedback and evaluation models.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    conversation_id: UUID
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class EvaluateRequest(BaseModel):
    query: str
    expected_answer: str
    project_id: Optional[str] = None


class EvaluateResponse(BaseModel):
    relevance_score: float
    faithfulness_score: float
    answer_quality: float
    details: dict = {}
