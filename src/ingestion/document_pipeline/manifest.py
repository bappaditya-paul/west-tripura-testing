"""
manifest.py — Thread-safe manifest updater for the Document Extraction Pipeline.

Appends one JSONL record per processed document to output/manifest.jsonl.
Each record is self-contained and can be streamed into downstream pipelines.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metadata import DocumentMetadata


# ─────────────────────────────────────────────────────────────────────────────
# Manifest record schema
# ─────────────────────────────────────────────────────────────────────────────

def _build_record(meta: DocumentMetadata, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compose a manifest JSONL record from a DocumentMetadata instance."""
    record: dict[str, Any] = {
        # Identity
        "id":               meta.id,
        "url":              meta.url,
        "file_name":        meta.file_name,
        "content_type":     meta.content_type,
        "source":           meta.source,

        # File paths
        "local_path":       meta.local_path,
        "markdown_path":    meta.markdown_path,
        "json_path":        meta.json_path,
        "metadata_path":    meta.metadata_path,

        # Extraction quality
        "extraction_status":  meta.processing_status,
        "extraction_time_s":  round(meta.extraction_time_s, 3),
        "parser_used":        meta.parser_used,

        # Stats
        "word_count":   meta.word_count,
        "page_count":   meta.page_count,
        "tables":       meta.tables,
        "sha256":       meta.sha256,
        "file_size_bytes": meta.file_size_bytes,

        # Temporal
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        record.update(extra)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Manifest writer
# ─────────────────────────────────────────────────────────────────────────────

class ManifestWriter:
    """
    Appends JSONL records to the pipeline manifest.

    Thread-safe: multiple worker coroutines can call append() concurrently.
    """

    def __init__(self, manifest_path: Path) -> None:
        self._path = manifest_path
        self._lock = threading.Lock()

    def append(self, meta: DocumentMetadata, extra: dict[str, Any] | None = None) -> None:
        """Append one record to the manifest file."""
        record = _build_record(meta, extra)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def load_existing_urls(self) -> set[str]:
        """
        Return the set of URLs already in the manifest.
        Used to skip already-processed documents on re-run.
        """
        if not self._path.exists():
            return set()
        urls: set[str] = set()
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if url := rec.get("url"):
                    urls.add(url)
            except Exception:
                pass
        return urls


# ─────────────────────────────────────────────────────────────────────────────
# Failed-documents log
# ─────────────────────────────────────────────────────────────────────────────

class FailedDocumentLog:
    """
    Maintains a JSON array of all documents that could not be processed.

    Written to output/failed_documents.json.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []
        # Load existing failures so we can accumulate across runs
        if path.exists():
            try:
                self._records = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self._records = []

    def record(
        self,
        *,
        url: str,
        error: str,
        stack_trace: str = "",
        retry_count: int = 0,
    ) -> None:
        entry: dict[str, Any] = {
            "url":         url,
            "error":       error,
            "stack_trace": stack_trace,
            "retry_count": retry_count,
            "failed_at":   datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._records.append(entry)
            self._flush()

    def _flush(self) -> None:
        self._path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._records)
