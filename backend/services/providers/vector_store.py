"""
services/providers/vector_store.py
==================================
Pluggable vector store providers (Pinecone, Qdrant, FAISS).
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from backend.services.interfaces.base import VectorStoreInterface


class PineconeProvider(VectorStoreInterface):
    def __init__(self, config: dict):
        from pinecone import Pinecone
        self.pc = Pinecone(api_key=config["api_key"])
        self.index = self.pc.Index(config["index_name"])
        self._name = "pinecone"

    async def upsert(self, vectors: list[dict]) -> int:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self.index.upsert(vectors=vectors))
        return result.upserted_count

    async def query(self, vector: list[float], top_k: int, filters: dict = None) -> list[dict]:
        loop = asyncio.get_event_loop()
        kwargs = {"vector": vector, "top_k": top_k, "include_metadata": True}
        if filters:
            kwargs["filter"] = filters
        res = await loop.run_in_executor(None, lambda: self.index.query(**kwargs))
        return [
            {
                "id": m.id,
                "score": m.score,
                "content": m.metadata.get("content", ""),
                "title": m.metadata.get("title", ""),
                "url": m.metadata.get("url", ""),
                "section": m.metadata.get("section", ""),
                "metadata": dict(m.metadata),
            }
            for m in res.matches
        ]

    async def delete(self, ids: list[str]) -> int:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.index.delete(ids=ids))
        return len(ids)

    async def count(self) -> int:
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(None, lambda: self.index.describe_index_stats())
        return stats.total_vector_count

    async def health(self) -> dict:
        try:
            await self.count()
            return {"status": "healthy", "provider": self._name}
        except Exception as e:
            return {"status": "unhealthy", "provider": self._name, "error": str(e)}


class QdrantProvider(VectorStoreInterface):
    def __init__(self, config: dict):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(host=config["host"], port=config["port"])
        self.collection = config.get("collection", "rag-platform")
        self._name = "qdrant"

    async def upsert(self, vectors: list[dict]) -> int:
        from qdrant_client.models import PointStruct
        points = [
            PointStruct(id=v["id"], vector=v["values"], payload=v.get("metadata", {}))
            for v in vectors
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.client.upsert(collection_name=self.collection, points=points))
        return len(points)

    async def query(self, vector: list[float], top_k: int, filters: dict = None) -> list[dict]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=top_k,
            ),
        )
        return [
            {
                "id": str(r.id),
                "score": r.score,
                "content": r.payload.get("content", "") if r.payload else "",
                "title": r.payload.get("title", "") if r.payload else "",
                "url": r.payload.get("url", "") if r.payload else "",
                "section": r.payload.get("section", "") if r.payload else "",
                "metadata": dict(r.payload) if r.payload else {},
            }
            for r in results
        ]

    async def delete(self, ids: list[str]) -> int:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.client.delete(
                collection_name=self.collection,
                points_selector=ids,
            ),
        )
        return len(ids)

    async def count(self) -> int:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: self.client.get_collection(self.collection))
        return info.points_count or 0

    async def health(self) -> dict:
        try:
            await self.count()
            return {"status": "healthy", "provider": self._name}
        except Exception as e:
            return {"status": "unhealthy", "provider": self._name, "error": str(e)}


def get_vector_store(config: dict) -> VectorStoreInterface:
    provider = config.get("provider", "pinecone")
    if provider == "pinecone":
        return PineconeProvider(config["pinecone"])
    elif provider == "qdrant":
        return QdrantProvider(config["qdrant"])
    else:
        raise ValueError(f"Unsupported vector DB provider: {provider}")
