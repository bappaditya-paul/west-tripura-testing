from __future__ import annotations

import hashlib
import json
from typing import Any


class CacheService:
    def __init__(self, redis_url: str, ttl: int = 300):
        self.redis_url = redis_url
        self.ttl = ttl
        self._redis = None

    async def _client(self):
        if self._redis is None:
            try:
                from redis.asyncio import Redis
                self._redis = Redis.from_url(self.redis_url, decode_responses=True)
            except Exception:
                return None
        return self._redis

    @staticmethod
    def key(query: str) -> str:
        normalized = " ".join(query.lower().strip().split())
        return "rag:answer:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def get(self, query: str) -> dict[str, Any] | None:
        client = await self._client()
        if client is None:
            return None
        try:
            value = await client.get(self.key(query))
            return json.loads(value) if value else None
        except Exception:
            return None

    async def set(self, query: str, value: dict[str, Any]) -> None:
        client = await self._client()
        if client is None:
            return
        try:
            await client.set(self.key(query), json.dumps(value, ensure_ascii=False), ex=self.ttl)
        except Exception:
            return
