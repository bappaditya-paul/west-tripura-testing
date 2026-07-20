"""
api/v1/auth.py
=============
Authentication endpoints: register, login, API key management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_db
from backend.middleware.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.models.orm import APIKey, User
from backend.schemas.auth import APIKeyCreate, APIKeyOut, TokenResponse, UserLogin, UserOut, UserRegister

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check duplicate
    existing = await db.execute(select(User).where((User.email == payload.email) | (User.username == payload.username)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already registered")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role="user",
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=token,
        expires_in=60 * 60 * 24 * 7,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/api-key", response_model=APIKeyOut, status_code=201)
async def create_api_key(
    payload: APIKeyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import secrets
    raw_key = f"rk_{secrets.token_urlsafe(32)}"
    api_key = APIKey(
        user_id=current_user["sub"],
        name=payload.name,
        key_hash=hash_password(raw_key),
    )
    db.add(api_key)
    await db.flush()
    return APIKeyOut(id=api_key.id, name=api_key.name, key=raw_key, is_active=api_key.is_active, created_at=api_key.created_at)


@router.get("/api-keys", response_model=list[APIKeyOut])
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIKey).where(APIKey.user_id == current_user["sub"]))
    return result.scalars().all()
