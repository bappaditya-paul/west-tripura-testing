"""
middleware/auth.py
=================
JWT + API Key authentication dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from backend.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_bearer = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_EXPIRY_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


GUEST_USER_DICT = {
    "sub": "00000000-0000-0000-0000-000000000001",
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "guest@westtripura.gov.in",
    "username": "guest_user",
    "role": "admin",
    "is_active": True,
    "created_at": "2026-01-01T00:00:00Z",
    "method": "no_jwt_open_access",
}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    """Authentication disabled: Always returns default guest/admin user context."""
    return GUEST_USER_DICT


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    api_key: Optional[str] = Security(api_key_header),
) -> Optional[dict]:
    """Authentication disabled: Always returns default guest/admin user context."""
    return GUEST_USER_DICT
