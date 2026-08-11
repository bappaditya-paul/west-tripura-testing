from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    CONVERSATIONAL = "conversational"
    SIMPLE_FACT = "simple_fact"
    RAG_QUERY = "rag_query"
    GENERAL_KNOWLEDGE = "general_knowledge"


_GREETING_RE = re.compile(r"^(hi|hello|hey|namaste|নমস্কার|হ্যালো|good morning|good evening|good afternoon)\b", re.I)
_THANKS_RE = re.compile(r"\b(thank you|thanks|ধন্যবাদ|thnx)\b", re.I)
_SIMPLE_FACT_RE = re.compile(r"\b(phone|number|contact|email|address|location|where|who is|helpline|office)\b|\b(নম্বর|ফোন|যোগাযোগ|ঠিকানা|কোথায়|কে)\b", re.I)
_GENERAL_RE = re.compile(r"\b(joke|poem|story|movie|song|recipe|weather|capital of|who won|what is ai|what is blockchain)\b", re.I)


class IntentRouter:
    """Zero-LLM latency router for common citizen interactions."""

    def route(self, query: str) -> Intent:
        text = query.strip()
        if not text:
            return Intent.CONVERSATIONAL
        if _GREETING_RE.search(text) or _THANKS_RE.search(text) or text.lower() in {"ok", "okay", "bye", "ধন্যবাদ"}:
            return Intent.CONVERSATIONAL
        if _GENERAL_RE.search(text):
            return Intent.GENERAL_KNOWLEDGE
        if _SIMPLE_FACT_RE.search(text) and len(text.split()) <= 12:
            return Intent.SIMPLE_FACT
        return Intent.RAG_QUERY
