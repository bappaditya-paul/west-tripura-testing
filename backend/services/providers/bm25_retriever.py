from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Retriever:
    def __init__(self, chunks_path: str | Path = "processed_chunks"):
        self.chunks_path = Path(chunks_path)
        self._corpus: list[str] = []
        self._documents: list[dict] = []
        self._bm25: Optional[BM25Okapi] = None

    def load(self):
        self._corpus.clear()
        self._documents.clear()

        from backend.services.canonical_chunk_loader import get_canonical_chunk_loader
        loader = get_canonical_chunk_loader()
        chunks = loader.load_all_chunks()

        for doc in chunks:
            self._add_document(doc)

        if self._corpus:
            self._bm25 = BM25Okapi([self._tokenize(t) for t in self._corpus])
            logger.info("BM25 index built successfully with %d canonical documents", len(self._corpus))
        else:
            logger.warning("BM25 index initialization: No valid chunks loaded from CanonicalChunkLoader.")

    def _add_document(self, doc: dict):
        text = doc.get("content") or doc.get("text") or doc.get("chunk_text", "")
        if text and len(text.strip()) > 20:
            self._corpus.append(text)
            self._documents.append({
                "chunk_id": doc.get("chunk_id") or doc.get("id") or f"bm25-{len(self._documents)}",
                "text": text,
                "title": doc.get("title") or doc.get("doc_title", ""),
                "url": doc.get("url") or doc.get("source_url", ""),
                "section": doc.get("section") or doc.get("heading", ""),
                "sub_section": doc.get("sub_section", ""),
                "heading_chain": doc.get("heading_chain", []),
                "parent_chunk_id": doc.get("parent_chunk_id"),
                "prev_chunk_id": doc.get("prev_chunk_id"),
                "next_chunk_id": doc.get("next_chunk_id"),
                "domain": doc.get("domain", ""),
                "language": doc.get("language", "en"),
            })

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def query(self, query: str, top_k: int = 20) -> list[dict]:
        if not self._bm25 or not self._corpus:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []
        for idx in top_indices:
            score = scores[idx]
            if score <= 0:
                continue
            doc = self._documents[idx]
            results.append({
                "id": doc.get("chunk_id"),
                "score": float(score),
                "content": doc.get("text", ""),
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "section": doc.get("section", ""),
                "sub_section": doc.get("sub_section", ""),
                "heading_chain": doc.get("heading_chain", []),
                "parent_chunk_id": doc.get("parent_chunk_id"),
                "prev_chunk_id": doc.get("prev_chunk_id"),
                "next_chunk_id": doc.get("next_chunk_id"),
                "metadata": {
                    "domain": doc.get("domain", ""),
                    "language": doc.get("language", "en"),
                },
            })
        return results


_retriever: Optional[BM25Retriever] = None


def get_bm25_retriever(chunks_path: str | Path = "processed_chunks") -> BM25Retriever:
    global _retriever
    if _retriever is None:
        _retriever = BM25Retriever(chunks_path)
        _retriever.load()
    return _retriever
