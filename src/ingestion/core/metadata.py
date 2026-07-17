"""
ingestion/metadata.py
=====================
Canonical metadata builder for unified documents.

Merges data from:
  - Crawler manifest.jsonl (HTML pages)
  - output/metadata/*.metadata.json (PDF/DOCX/XLSX)
  - Frontmatter parsed from .md files
  - Parsed document content (word_count, content_hash)

Output: a flat dict that lives inside every CanonicalDocument.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import content_hash, count_words


# ─────────────────────────────────────────────────────────────────────────────
# Metadata dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentMetadata:
    """
    Canonical metadata stored inside every processed document.
    Also propagated to every chunk derived from the document.
    """

    # Source provenance
    source_url: str = ""
    file_name: str = ""
    source_domain: str = "westtripura.nic.in"

    # Content classification
    language: str = "unknown"       # "en" | "bn" | "mixed" | "unknown"
    content_type: str = ""          # "html" | "pdf" | "docx" | "xlsx"

    # Statistics
    word_count: int = 0
    page_count: int = 0
    table_count: int = 0

    # Integrity
    content_hash: str = ""          # SHA-256 of content field

    # Temporal
    crawl_date: str = ""
    processed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Processing chain
    parser_used: str = ""           # "crawl4ai" | "docling" | "openpyxl" etc.

    # Crawl-specific
    depth: int = 0
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────────────

def build_html_metadata(
    *,
    frontmatter: dict[str, str],
    manifest_entry: dict[str, Any] | None,
    content: str,
) -> DocumentMetadata:
    """
    Build metadata for an HTML-sourced page.

    Frontmatter keys: url, depth, score, crawled_at
    Manifest keys:    url, depth, score, char_count, crawled_at
    """
    me = manifest_entry or {}
    url = frontmatter.get("url") or me.get("url", "")
    crawled_at = frontmatter.get("crawled_at") or me.get("crawled_at", "")

    return DocumentMetadata(
        source_url=url,
        file_name=Path(me.get("file", "")).name,
        source_domain="westtripura.nic.in",
        language=_detect_language(content),
        content_type="html",
        word_count=count_words(content),
        content_hash=content_hash(content),
        crawl_date=crawled_at,
        parser_used="crawl4ai+lxml",
        depth=int(frontmatter.get("depth", me.get("depth", 0))),
        score=float(frontmatter.get("score", me.get("score", 0.0))),
    )


def build_doc_metadata(
    *,
    raw_meta: dict[str, Any],
    content: str,
) -> DocumentMetadata:
    """
    Build metadata for PDF/DOCX/XLSX from the output/metadata/*.metadata.json file.
    """
    return DocumentMetadata(
        source_url=raw_meta.get("url", ""),
        file_name=raw_meta.get("file_name", ""),
        source_domain=raw_meta.get("source", "westtripura.nic.in"),
        language=raw_meta.get("language", _detect_language(content)),
        content_type=raw_meta.get("content_type", ""),
        word_count=raw_meta.get("word_count") or count_words(content),
        page_count=raw_meta.get("page_count", 0),
        table_count=raw_meta.get("tables", 0),
        content_hash=content_hash(content),
        crawl_date=raw_meta.get("download_date", ""),
        parser_used=raw_meta.get("parser_used", ""),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Language detection (same heuristic as document_pipeline)
# ─────────────────────────────────────────────────────────────────────────────

_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")


def _detect_language(text: str) -> str:
    if not text:
        return "unknown"
    sample = text[:2000]
    bn = len(_BENGALI_RE.findall(sample))
    en = sum(1 for c in sample if c.isascii() and c.isalpha())
    total = bn + en or 1
    ratio = bn / total
    if ratio > 0.6:
        return "bn"
    if ratio < 0.2:
        return "en"
    return "mixed"
