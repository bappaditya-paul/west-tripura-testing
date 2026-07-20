"""
core/config.py
==============
Centralized configuration loaded from environment / .env file.
Single source of truth for every pluggable component.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorDBProvider(str, Enum):
    PINECONE = "pinecone"
    QDRANT = "qdrant"
    FAISS = "faiss"
    WEAVIATE = "weaviate"
    MILVUS = "milvus"


class EmbeddingProvider(str, Enum):
    NVIDIA = "nvidia"
    OPENAI = "openai"
    BGE = "bge"
    SENTENCE_TRANSFORMERS = "sentence-transformers"


class LLMProvider(str, Enum):
    NVIDIA = "nvidia"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    APP_NAME: str = "RAG Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    STATIC_API_KEY: str = "telegram-bot-internal"
    API_V1_PREFIX: str = "/api/v1"

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    CORS_ORIGINS: list[str] = ["*"]

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/ragplatform"

    # ── Redis ────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"
    CACHE_TTL: int = 300

    # ── Authentication ───────────────────────────────────────────────────
    JWT_SECRET: str = "change-me-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60 * 24 * 7  # 7 days

    # ── Pluggable Providers ──────────────────────────────────────────────
    VECTOR_DB_PROVIDER: VectorDBProvider = VectorDBProvider.PINECONE
    EMBEDDING_PROVIDER: EmbeddingProvider = EmbeddingProvider.NVIDIA
    LLM_PROVIDER: LLMProvider = LLMProvider.NVIDIA

    # ── NVIDIA ───────────────────────────────────────────────────────────
    NV_API_KEY: str = ""
    NV_API_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NV_EMBED_MODEL: str = "nvidia/nv-embed-v1"
    NV_CHAT_MODEL: str = "meta/llama-3.1-70b-instruct"
    NV_CHAT_API_KEY: str = ""

    # ── OpenAI ───────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_EMBED_MODEL: str = "text-embedding-3-large"
    OPENAI_CHAT_MODEL: str = "gpt-4o"

    # ── Pinecone ─────────────────────────────────────────────────────────
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "rag-platform"
    PINECONE_HOST: str = ""

    # ── Qdrant ───────────────────────────────────────────────────────────
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "rag-platform"

    # ── Chunking ─────────────────────────────────────────────────────────
    CHUNK_TOKEN_SIZE: int = 300
    CHUNK_TOKEN_OVERLAP: int = 30
    MAX_CHUNK_TOKEN_SIZE: int = 450
    MIN_CHUNK_WORDS: int = 15
    EMBED_BATCH_SIZE: int = 16

    # ── Retrieval ────────────────────────────────────────────────────────
    RELEVANCE_THRESHOLD: float = 0.40
    TOP_K: int = 5
    RERANK_TOP_K: int = 3

    # ── Crawler ──────────────────────────────────────────────────────────
    CRAWL_MAX_DEPTH: int = 5
    CRAWL_MAX_PAGES: int = 2000
    CRAWL_CONCURRENCY: int = 3
    CRAWL_DELAY: float = 1.5

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Monitoring ───────────────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True
    OPENTELEMETRY_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4317"

    # ── Storage ──────────────────────────────────────────────────────────
    UPLOAD_DIR: Path = Path("uploads")
    OUTPUT_DIR: Path = Path("output")
    PROCESSED_DOCS_DIR: Path = Path("processed_documents")
    PROCESSED_CHUNKS_DIR: Path = Path("processed_chunks")

    @property
    def vector_db_config(self) -> dict:
        return {
            "provider": self.VECTOR_DB_PROVIDER,
            "pinecone": {
                "api_key": self.PINECONE_API_KEY,
                "index_name": self.PINECONE_INDEX_NAME,
                "host": self.PINECONE_HOST,
            },
            "qdrant": {
                "host": self.QDRANT_HOST,
                "port": self.QDRANT_PORT,
                "collection": self.QDRANT_COLLECTION,
            },
        }

    @property
    def embedding_config(self) -> dict:
        return {
            "provider": self.EMBEDDING_PROVIDER,
            "nvidia": {
                "api_key": self.NV_API_KEY,
                "base_url": self.NV_API_BASE_URL,
                "model": self.NV_EMBED_MODEL,
            },
            "openai": {
                "api_key": self.OPENAI_API_KEY,
                "model": self.OPENAI_EMBED_MODEL,
            },
        }

    @property
    def llm_config(self) -> dict:
        return {
            "provider": self.LLM_PROVIDER,
            "nvidia": {
                "api_key": self.NV_CHAT_API_KEY or self.NV_API_KEY,
                "base_url": self.NV_API_BASE_URL,
                "model": self.NV_CHAT_MODEL,
            },
            "openai": {
                "api_key": self.OPENAI_API_KEY,
                "model": self.OPENAI_CHAT_MODEL,
            },
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
