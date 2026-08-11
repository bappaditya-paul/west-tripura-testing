from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.services.intent_router import Intent, IntentRouter
from backend.services.query_processor import QueryProcessor


@dataclass
class QueryAnalysisV2:
    original_query: str
    language: str
    intent: Intent
    topic: str | None
    entities: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    retrieval_query: str = ""


class QueryAnalyzerV2:
    """Broader citizen query understanding without over-filtering vector search."""

    def __init__(self):
        self.router = IntentRouter()
        self.processor = QueryProcessor()

    def analyze(self, query: str) -> QueryAnalysisV2:
        processed = self.processor.process(query)
        intent = self.router.route(query)
        text = query.lower()
        entities: list[str] = []
        filters: dict[str, Any] = {}
        topic = None

        if re.search(r"\b(dm|district magistrate|collector)\b|জেলা শাসক|জেলাশাসক", text):
            entities.append("District Magistrate")
            filters["office"] = "District Magistrate"
        elif re.search(r"\b(sdm|sub[ -]?divisional magistrate)\b", text):
            entities.append("Sub-Divisional Magistrate")
            filters["office"] = "Sub-Divisional Magistrate"
        elif re.search(r"\b(bdo|block development officer)\b", text):
            entities.append("Block Development Officer")
            filters["office"] = "Block Development Officer"

        if re.search(r"\b(phone|number|contact|email|helpline)\b|নম্বর|ফোন|যোগাযোগ", text):
            topic = "contact"
        elif re.search(r"\b(apply|application|eligib|document|documents|required|certificate|register|registration|how do i|where do i|birth|marriage|death)\b|কিভাবে|করব|আবেদন|যোগ্য|নথি|ডকুমেন্ট|শংসাপত্র|সার্টিফিকেট|নিবন্ধন|জন্ম|বিবাহ|মৃত্যু", text):
            topic = "procedure"
        elif re.search(r"\b(scheme|yojana|pmay|pm kisan|pension|benefit)\b|স্কিম|প্রকল্প|যোজনা|পেনশন", text):
            topic = "scheme"

        retrieval_query = processed["retrieval_query"]
        if entities:
            retrieval_query = f"{retrieval_query} {' '.join(entities)}"
        if topic:
            retrieval_query = f"{retrieval_query} {topic}"
        if topic == "procedure":
            retrieval_query = f"{retrieval_query} application process required documents official form notification PDF"

        return QueryAnalysisV2(
            original_query=query,
            language=processed["language"],
            intent=intent,
            topic=topic,
            entities=entities,
            filters=filters,
            retrieval_query=retrieval_query.strip(),
        )
