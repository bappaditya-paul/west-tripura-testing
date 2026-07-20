"""
schemas/health.py
================
Health check response models.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    message: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    database: str
    redis: str
    vector_db: str


class LiveResponse(BaseModel):
    status: str
    uptime: float
