"""
services/providers/embedding.py
===============================
Pluggable embedding providers (NVIDIA, OpenAI, BGE, Sentence Transformers).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from backend.services.interfaces.base import EmbeddingInterface


class NVIDIAEmbeddingProvider(EmbeddingInterface):
    def __init__(self, config: dict):
        from openai import OpenAI
        self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        self._model = config.get("model", "nvidia/nv-embed-v1")
        self._dimensions = 4096

    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.embeddings.create(
                model=self._model,
                input=texts,
                extra_body={"input_type": input_type, "truncate": "END"},
            ),
        )
        return [item.embedding for item in response.data]

    def dimensions(self) -> int:
        return self._dimensions

    def model_name(self) -> str:
        return self._model

    async def health(self) -> dict:
        try:
            await self.embed(["ping"], input_type="query")
            return {"status": "healthy", "provider": "nvidia", "model": self._model}
        except Exception as e:
            return {"status": "unhealthy", "provider": "nvidia", "error": str(e)}


class OpenAIEmbeddingProvider(EmbeddingInterface):
    def __init__(self, config: dict):
        from openai import OpenAI
        self.client = OpenAI(api_key=config["api_key"])
        self._model = config.get("model", "text-embedding-3-large")
        self._dimensions = config.get("dimensions", 3072)

    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.embeddings.create(
                model=self._model,
                input=texts,
            ),
        )
        return [item.embedding for item in response.data]

    def dimensions(self) -> int:
        return self._dimensions

    def model_name(self) -> str:
        return self._model

    async def health(self) -> dict:
        try:
            await self.embed(["ping"], input_type="query")
            return {"status": "healthy", "provider": "openai", "model": self._model}
        except Exception as e:
            return {"status": "unhealthy", "provider": "openai", "error": str(e)}


class SentenceTransformersEmbeddingProvider(EmbeddingInterface):
    def __init__(self, config: dict):
        from sentence_transformers import SentenceTransformer
        self._model_name = config.get("model", "BAAI/bge-large-en-v1.5")
        self._model = SentenceTransformer(self._model_name)
        self._dimensions = config.get("dimensions", 1024)

    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts).tolist(),
        )
        return embeddings

    def dimensions(self) -> int:
        return self._dimensions

    def model_name(self) -> str:
        return self._model_name

    async def health(self) -> dict:
        try:
            await self.embed(["ping"], input_type="query")
            return {"status": "healthy", "provider": "sentence-transformers", "model": self._model_name}
        except Exception as e:
            return {"status": "unhealthy", "provider": "sentence-transformers", "error": str(e)}


def get_embedding_provider(config: dict) -> EmbeddingInterface:
    provider = config.get("provider", "nvidia")
    if provider == "nvidia":
        return NVIDIAEmbeddingProvider(config["nvidia"])
    elif provider == "openai":
        return OpenAIEmbeddingProvider(config["openai"])
    elif provider in ("bge", "sentence-transformers"):
        return SentenceTransformersEmbeddingProvider(config.get("sentence_transformers", config.get("bge", {})))
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")
