from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Confidence:
    score: float
    level: str
    reason: str


class ConfidenceScorer:
    """Calibratable retrieval gate; never treats raw DB scores as directly comparable."""

    def score(self, query: str, results: list[dict[str, Any]]) -> Confidence:
        if not results:
            return Confidence(0.0, "low", "no_candidates")

        top = results[0]
        rerank = float(top.get("rerank_score", 0.0))
        lexical = float(top.get("lexical_overlap", 0.0))
        entity = float(top.get("entity_match", 0.0))
        support = min(len(results), 3) / 3.0
        gap = 0.0
        if len(results) > 1:
            gap = max(0.0, rerank - float(results[1].get("rerank_score", 0.0)))

        score = min(1.0, max(0.0, 0.55 * rerank + 0.20 * lexical + 0.15 * entity + 0.05 * support + 0.05 * min(gap * 5, 1.0)))
        if score >= 0.70:
            return Confidence(score, "high", "strong_retrieval_evidence")
        if score >= 0.45:
            return Confidence(score, "medium", "retrieval_needs_confirmation")
        return Confidence(score, "low", "insufficient_retrieval_evidence")
