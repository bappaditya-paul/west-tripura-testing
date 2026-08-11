"""
backend/services/canonical_chunk_loader.py
==========================================
Canonical Chunk Corpus Loader.
Loads, normalizes, and validates text chunks strictly from `processed_chunks/`
directory to ensure Pinecone and BM25 use the exact same corpus.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ragplatform.canonical_chunk_loader")


class ChunkMetadata(Dict[str, Any]):
    """Normalized dictionary representation of a chunk."""
    pass


class CanonicalChunkLoader:
    def __init__(self, processed_chunks_dir: str | Path = "processed_chunks"):
        self.processed_chunks_dir = Path(processed_chunks_dir)

    def load_all_chunks(self) -> List[Dict[str, Any]]:
        """
        Scan processed_chunks/ directory for JSON files and return a list of
        normalized chunk dictionaries.
        """
        chunks: List[Dict[str, Any]] = []

        if not self.processed_chunks_dir.exists():
            logger.warning("Processed chunks directory %s does not exist.", self.processed_chunks_dir)
            return chunks

        # Method A: Read all JSON files in processed_chunks/
        json_files = list(self.processed_chunks_dir.glob("*.json"))
        for json_path in json_files:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            norm = self._normalize_chunk(item, json_path.stem)
                            if norm:
                                chunks.append(norm)
                    elif isinstance(data, dict):
                        norm = self._normalize_chunk(data, json_path.stem)
                        if norm:
                            chunks.append(norm)
            except Exception as exc:
                logger.error("Failed to load chunk file %s: %s", json_path, exc)

        # Method B: Fallback check if any JSONL files exist
        if not chunks:
            jsonl_files = list(self.processed_chunks_dir.glob("*.jsonl"))
            for jsonl_path in jsonl_files:
                try:
                    with open(jsonl_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                item = json.loads(line)
                                norm = self._normalize_chunk(item, jsonl_path.stem)
                                if norm:
                                    chunks.append(norm)
                except Exception as exc:
                    logger.error("Failed to load JSONL chunk file %s: %s", jsonl_path, exc)

        logger.info("Loaded %d canonical chunks from %s", len(chunks), self.processed_chunks_dir)
        return chunks

    def _normalize_chunk(self, raw: Dict[str, Any], fallback_id: str) -> Optional[Dict[str, Any]]:
        """Normalize chunk schema into standard dictionary structure."""
        content = raw.get("content") or raw.get("text") or raw.get("chunk_text") or ""
        if not content.strip():
            return None

        chunk_id = str(raw.get("chunk_id") or raw.get("id") or fallback_id)
        doc_id = str(raw.get("document_id") or raw.get("doc_id") or "")
        title = raw.get("title") or raw.get("doc_title") or raw.get("document_title") or "West Tripura Information"
        url = raw.get("url") or raw.get("source_url") or raw.get("page_url") or ""
        section = raw.get("section") or raw.get("heading") or raw.get("sub_section") or ""
        prev_chunk_id = raw.get("prev_chunk_id")
        next_chunk_id = raw.get("next_chunk_id")

        return {
            "chunk_id": chunk_id,
            "id": chunk_id,
            "document_id": doc_id,
            "content": content,
            "text": content,
            "title": title,
            "url": url,
            "section": section,
            "prev_chunk_id": prev_chunk_id,
            "next_chunk_id": next_chunk_id,
            "metadata": {
                "title": title,
                "url": url,
                "section": section,
                "document_id": doc_id,
                "prev_chunk_id": prev_chunk_id,
                "next_chunk_id": next_chunk_id,
            }
        }


# Singleton accessor
_canonical_loader = None

def get_canonical_chunk_loader() -> CanonicalChunkLoader:
    global _canonical_loader
    if _canonical_loader is None:
        _canonical_loader = CanonicalChunkLoader()
    return _canonical_loader
