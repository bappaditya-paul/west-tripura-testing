"""
services/interfaces/base.py
===========================
Abstract base interfaces for all pluggable components.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStoreInterface(ABC):
    @abstractmethod
    async def upsert(self, vectors: list[dict]) -> int: ...

    @abstractmethod
    async def query(self, vector: list[float], top_k: int, filters: dict = None) -> list[dict]: ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> int: ...

    @abstractmethod
    async def count(self) -> int: ...

    @abstractmethod
    async def health(self) -> dict: ...


class EmbeddingInterface(ABC):
    @abstractmethod
    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]: ...

    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def health(self) -> dict: ...


class LLMInterface(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str: ...

    @abstractmethod
    async def generate_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024):
        """Yield string chunks for streaming."""
        ...

    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def health(self) -> dict: ...
