"""Citizen query normalization and language detection."""

from __future__ import annotations

import re
from typing import Any, Optional

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

BENGALI_KEYWORDS = {
    "kivabe", "kibhabe", "kora", "korbo", "pabo", "jonno", "dorkar", "khobor", "somoy",
    "ki", "ta", "er", "amar", "ache", "kothay", "number", "office", "lagbe", "chai",
}


class QueryProcessor:
    def process(self, raw_query: str) -> dict[str, Any]:
        cleaned = raw_query.strip()
        language = self._detect_language(cleaned)
        normalized = self._normalize_query(cleaned)
        return {"raw_query": raw_query, "retrieval_query": normalized, "language": language, "is_benglish": language == "bn_en"}

    def _detect_language(self, text: str) -> str:
        if re.search(r"[\u0980-\u09FF]", text):
            return "bn"
        words = set(re.findall(r"[a-z]+", text.lower()))
        if len(words & BENGALI_KEYWORDS) >= 1:
            return "bn_en"
        return "en"

    def _normalize_query(self, text: str) -> str:
        normalized = text
        for pattern, replacement in ABBREVIATIONS.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        if "tripura" not in normalized.lower():
            normalized += " West Tripura"
        return normalized.strip()


class QueryRewriter:
    """Compatibility interface for future conversational query rewriting."""

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    async def rewrite(self, query: str, history: Optional[list] = None) -> str:
        return QueryProcessor().process(query)["retrieval_query"]
