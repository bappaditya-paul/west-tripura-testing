"""
ingestion/config.py
===================
Central configuration — single source of truth for every pipeline stage.

All paths, API settings, and chunking parameters live here.
Secrets are loaded from the .env file (never hard-coded).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load .env automatically when this module is imported
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # dotenv optional; env vars can be set externally

# ─────────────────────────────────────────────────────────────────────────────
# Repo layout
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent

# ── Raw crawler / document-pipeline output ────────────────────────────────────
OUTPUT_ROOT: Path           = REPO_ROOT / "output"
PAGES_DIR: Path             = OUTPUT_ROOT / "pages"
MARKDOWN_DIR: Path          = OUTPUT_ROOT / "markdown"
JSON_DIR: Path              = OUTPUT_ROOT / "json"
METADATA_DIR: Path          = OUTPUT_ROOT / "metadata"
MANIFEST_PATH: Path         = OUTPUT_ROOT / "manifest.jsonl"

# ── Intermediate processed files ──────────────────────────────────────────────
PROCESSED_DOCS_DIR: Path    = REPO_ROOT / "processed_documents"
PROCESSED_CHUNKS_DIR: Path  = REPO_ROOT / "processed_chunks"
LOGS_DIR: Path              = REPO_ROOT / "logs"
FAILED_DOCS_PATH: Path      = REPO_ROOT / "failed_documents.json"

# Legacy aliases — kept so old modules don't break
PROCESSED_DIR   = PROCESSED_DOCS_DIR
CHUNKS_DIR      = PROCESSED_CHUNKS_DIR


# ─────────────────────────────────────────────────────────────────────────────
# NVIDIA NV-Embed-v1 (cloud API)
# ─────────────────────────────────────────────────────────────────────────────

NV_API_KEY: str       = os.getenv("NV_API_KEY", "")
NV_API_BASE_URL: str  = "https://integrate.api.nvidia.com/v1"
NV_EMBED_MODEL: str   = "nvidia/nv-embed-v1"
VECTOR_SIZE: int      = 4096   # NV-Embed-v1 output dimension
VECTOR_DIMENSION      = VECTOR_SIZE  # alias


# ─────────────────────────────────────────────────────────────────────────────
# Pinecone
# ─────────────────────────────────────────────────────────────────────────────

PINECONE_API_KEY: str    = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "west-tripura-chatbot")
PINECONE_HOST: str       = os.getenv(
    "PINECONE_HOST",
    "https://west-tripura-chatbot-ddxrjsk.svc.aped-4627-b74a.pinecone.io",
)


# ─────────────────────────────────────────────────────────────────────────────
# Chunking parameters
# ─────────────────────────────────────────────────────────────────────────────

CHUNK_TOKEN_SIZE: int    = int(os.getenv("CHUNK_TOKEN_SIZE",    "300"))
CHUNK_TOKEN_OVERLAP: int = int(os.getenv("CHUNK_TOKEN_OVERLAP", "30"))
CHUNK_OVERLAP            = CHUNK_TOKEN_OVERLAP  # alias
MAX_CHUNK_TOKEN_SIZE     = int(os.getenv("MAX_CHUNK_TOKEN_SIZE", "450"))
MIN_CHUNK_WORDS: int     = 15

BATCH_SIZE: int          = int(os.getenv("BATCH_SIZE",       "96"))
EMBED_BATCH_SIZE: int    = int(os.getenv("EMBED_BATCH_SIZE", "16"))


# ─────────────────────────────────────────────────────────────────────────────
# IngestionConfig dataclass
# (used by document_builder.py and chunk_builder.py)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IngestionConfig:
    """Typed configuration object — passed through all pipeline stages."""

    # Directories
    pages_dir: Path             = field(default_factory=lambda: PAGES_DIR)
    markdown_dir: Path          = field(default_factory=lambda: MARKDOWN_DIR)
    json_dir: Path              = field(default_factory=lambda: JSON_DIR)
    metadata_dir: Path          = field(default_factory=lambda: METADATA_DIR)
    manifest_path: Path         = field(default_factory=lambda: MANIFEST_PATH)
    processed_docs_dir: Path    = field(default_factory=lambda: PROCESSED_DOCS_DIR)
    processed_chunks_dir: Path  = field(default_factory=lambda: PROCESSED_CHUNKS_DIR)
    logs_dir: Path              = field(default_factory=lambda: LOGS_DIR)
    failed_documents_path: Path = field(default_factory=lambda: FAILED_DOCS_PATH)

    # Embedding (NVIDIA cloud)
    nv_api_key: str             = field(default_factory=lambda: NV_API_KEY)
    nv_embed_model: str         = NV_EMBED_MODEL
    vector_size: int            = VECTOR_SIZE

    # Pinecone
    pinecone_api_key: str       = field(default_factory=lambda: PINECONE_API_KEY)
    pinecone_index_name: str    = field(default_factory=lambda: PINECONE_INDEX_NAME)
    pinecone_host: str          = field(default_factory=lambda: PINECONE_HOST)

    # Chunking
    chunk_max_words: int        = MAX_CHUNK_TOKEN_SIZE
    chunk_target_words: int     = CHUNK_TOKEN_SIZE
    chunk_min_words: int        = MIN_CHUNK_WORDS
    chunk_overlap: int          = CHUNK_TOKEN_OVERLAP
    batch_size: int             = BATCH_SIZE
    embed_batch_size: int       = EMBED_BATCH_SIZE

    def create_all_dirs(self) -> None:
        """Create all required directories if they don't exist."""
        for d in [
            self.processed_docs_dir,
            self.processed_chunks_dir,
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton default — used as a convenient import
DEFAULT_CONFIG = IngestionConfig()
