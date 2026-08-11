from __future__ import annotations

import re
from typing import Any


class RerankerService:
    """Optional neural reranker with a dependency-free lexical fallback."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is not None or not self.model_name:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        except Exception:
            self._model = False

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))

    def rank(self, query: str, documents: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        if not documents:
            return []
        self._load_model()
        if self._model:
            pairs = [(query, d.get("content") or d.get("text") or "") for d in documents]
            scores = self._model.predict(pairs)
            for doc, score in zip(documents, scores):
                doc["rerank_score"] = float(score)
        else:
            q = self._tokens(query)
            for doc in documents:
                text = doc.get("content") or doc.get("text") or ""
                t = self._tokens(text)
                overlap = len(q & t) / max(1, len(q))
                title = self._tokens(doc.get("title", ""))
                title_overlap = len(q & title) / max(1, len(q))
                doc["lexical_overlap"] = overlap
                doc["rerank_score"] = min(1.0, 0.8 * overlap + 0.2 * title_overlap)

        for doc in documents:
            doc.setdefault("entity_match", 0.0)
        return sorted(documents, key=lambda d: d.get("rerank_score", 0.0), reverse=True)[:top_k]
