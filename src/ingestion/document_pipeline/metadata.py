"""
metadata.py — Document metadata dataclass + builder.

Every successfully processed document produces a metadata record that is:
  - Saved as  output/metadata/<name>.metadata.json
  - Appended to the pipeline manifest

Schema matches the RAG ingestion spec for Neo4j graph population.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import safe_json_dump


# ─────────────────────────────────────────────────────────────────────────────
# Metadata dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentMetadata:
    """
    Canonical metadata for one extracted government document.

    This is the schema that flows downstream into:
      - Neo4j node properties
      - Qdrant payload fields
      - Chunk-level frontmatter
    """

    # Identity
    id: str = ""                    # slug + hash, e.g. "Notice_Admission__a1b2c3d4"
    url: str = ""
    file_name: str = ""
    title: str = ""

    # Classification
    content_type: str = ""          # "pdf" | "docx" | "xlsx"
    source: str = "westtripura.nic.in"
    language: str = "unknown"       # "en" | "bn" | "mixed" | "unknown"

    # Temporal
    download_date: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Document statistics
    page_count: int = 0
    tables: int = 0
    images: int = 0
    word_count: int = 0

    # Integrity
    sha256: str = ""
    file_size_bytes: int = 0

    # Processing status
    processing_status: str = "success"  # "success" | "partial" | "failed"
    parser_used: str = ""               # "docling" | "docling+ocr" | "openpyxl"
    extraction_time_s: float = 0.0

    # File paths (relative to output root)
    local_path: str = ""
    markdown_path: str = ""
    json_path: str = ""
    metadata_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, metadata_dir: Path) -> Path:
        """Write metadata to <metadata_dir>/<id>.metadata.json and return path."""
        out_path = metadata_dir / f"{self.id}.metadata.json"
        safe_json_dump(self.to_dict(), out_path)
        self.metadata_path = str(out_path)
        return out_path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentMetadata":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ─────────────────────────────────────────────────────────────────────────────
# Builder helper
# ─────────────────────────────────────────────────────────────────────────────

def build_metadata(
    *,
    doc_id: str,
    url: str,
    file_name: str,
    content_type: str,
    sha256: str,
    file_size_bytes: int,
    source: str = "westtripura.nic.in",
    title: str = "",
    language: str = "unknown",
    page_count: int = 0,
    tables: int = 0,
    images: int = 0,
    word_count: int = 0,
    parser_used: str = "",
    extraction_time_s: float = 0.0,
    processing_status: str = "success",
    local_path: str = "",
    markdown_path: str = "",
    json_path: str = "",
) -> DocumentMetadata:
    """
    Convenience factory — keyword-only to prevent argument-order bugs.
    """
    return DocumentMetadata(
        id=doc_id,
        url=url,
        file_name=file_name,
        title=title or file_name,
        content_type=content_type,
        source=source,
        language=language,
        page_count=page_count,
        tables=tables,
        images=images,
        word_count=word_count,
        sha256=sha256,
        file_size_bytes=file_size_bytes,
        processing_status=processing_status,
        parser_used=parser_used,
        extraction_time_s=extraction_time_s,
        local_path=local_path,
        markdown_path=markdown_path,
        json_path=json_path,
    )
