"""
backend/services/query_processor.py
====================================
Modular Query Understanding, Normalization, & Rewriting Interface.
Expands informal Benglish & Bengali queries and expands government abbreviations.
"""

from __future__ import annotations

import re
from typing import Dict, Any, Optional

ABBREVIATIONS = {
    r"\bdm\b": "District Magistrate and Collector",
    r"\bdc\b": "District Collector",
    r"\bsdm\b": "Sub-Divisional Magistrate",
    r"\bsdo\b": "Sub-Divisional Officer",
    r"\bbdo\b": "Block Development Officer",
    r"\bdrda\b": "District Rural Development Agency",
    r"\bceo\b": "Chief Executive Officer",
    r"\badm\b": "Additional District Magistrate",
    r"\bdm office\b": "District Magistrate Office Agartala",
}


class QueryProcessor:
    """Preprocesses and normalizes citizen search queries."""

    def __init__(self):
        pass

    def process(self, raw_query: str) -> Dict[str, Any]:
        cleaned = raw_query.strip()
        language = self._detect_language(cleaned)
        normalized = self._normalize_query(cleaned)

        return {
            "raw_query": raw_query,
            "retrieval_query": normalized,
            "language": language,
            "is_benglish": language == "bn_en",
        }

    def _detect_language(self, text: str) -> str:
        # Check Bengali Unicode block range (U+0980 to U+09FF)
        bengali_chars = len(re.findall(r"[\u0980-\u09FF]", text))
        if bengali_chars > 0:
            return "bn"

        # Check Benglish heuristic keywords
        benglish_keywords = ["kivabe", "kora", "pabo", "jonno", "dorkar", "khobor", "somoy"]
        lower = text.lower()
        if any(kw in lower for kw in benglish_keywords):
            return "bn_en"

        return "en"

    def _normalize_query(self, text: str) -> str:
        normalized = text
        for pattern, replacement in ABBREVIATIONS.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        # Append geographic context if not present
        if "tripura" not in normalized.lower():
            normalized += " West Tripura"

        return normalized.strip()


class QueryRewriter:
    """Interface for LLM-based multi-turn query rewriting."""

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    async def rewrite(self, query: str, history: Optional[list] = None) -> str:
        if not history or not self.llm_provider:
            processor = QueryProcessor()
            return processor.process(query)["retrieval_query"]
        # Can be extended to call LLM rewriter
        return query
