"""
api/v1/feedback.py
==================
Feedback and evaluation endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_db
from backend.middleware.auth import get_current_user
from backend.schemas.feedback import EvaluateRequest, EvaluateResponse, FeedbackCreate
from backend.models.orm import Feedback

router = APIRouter(prefix="")


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    payload: EvaluateRequest,
    current_user: dict = Depends(get_current_user),
):
    return EvaluateResponse(
        relevance_score=0.85,
        faithfulness_score=0.90,
        answer_quality=0.88,
        details={"message": "Evaluation not yet implemented"},
    )


@router.post("/feedback", status_code=201)
async def submit_feedback(
    payload: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = Feedback(
        conversation_id=payload.conversation_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(fb)
    return {"message": "Feedback recorded", "id": str(fb.id)}
