from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Retriever:
    def __init__(self, chunks_path: str | Path):
        self.chunks_path = Path(chunks_path)
        self._corpus: list[str] = []
        self._documents: list[dict] = []
        self._bm25: Optional[BM25Okapi] = None

    def load(self):
        if not self.chunks_path.exists():
            logger.warning("Chunks file not found at %s", self.chunks_path)
            return
        with open(self.chunks_path) as f:
            for line in f:
                doc = json.loads(line)
                text = doc.get("text", "")
                if text and len(text.strip()) > 20:
                    self._corpus.append(text)
                    self._documents.append(doc)
        self._bm25 = BM25Okapi([self._tokenize(t) for t in self._corpus])
        logger.info("BM25 index built with %d documents", len(self._corpus))

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def query(self, query: str, top_k: int = 20) -> list[dict]:
        if not self._bm25 or not self._corpus:
            return []
        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []
        for idx in top_indices:
            score = scores[idx]
            if score <= 0:
                continue
            doc = self._documents[idx]
            results.append({
                "id": doc.get("chunk_id", f"bm25-{idx}"),
                "score": float(score),
                "content": doc.get("text", ""),
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "section": doc.get("section", ""),
                "metadata": {
                    "domain": doc.get("domain", ""),
                    "category": doc.get("category", ""),
                    "language": doc.get("language", ""),
                },
            })
        return results


_retriever: Optional[BM25Retriever] = None


def get_bm25_retriever(chunks_path: str | Path = "output/chunks/chunks.jsonl") -> BM25Retriever:
    global _retriever
    if _retriever is None:
        _retriever = BM25Retriever(chunks_path)
        _retriever.load()
    return _retriever
