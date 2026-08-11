"""Citizen-focused RAG orchestrator with fast routing and safe fallback."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional

from backend.core.config import get_settings
from backend.services.cache_service import CacheService
from backend.services.confidence_service import ConfidenceScorer
from backend.services.query_analysis import QueryAnalyzer
from backend.services.response_formatter import ResponseFormatter
from backend.services.reranker_service import RerankerService
from backend.services.providers.llm import get_llm_provider
from backend.services.retrieval_service import RetrievalService

logger = logging.getLogger("ragplatform.rag_service")

GROUNDED_PROMPT = """You are the West Tripura District citizen information assistant.
Answer the citizen's question using ONLY the verified official context supplied below.
Never invent government names, phone numbers, addresses, dates, eligibility rules, fees or procedures.
Use simple language suitable for ordinary citizens. Match the user's language: English, Bengali, or Benglish.
For a contact question, put the key contact details first. For procedures, use numbered steps.
If the context does not support the answer, say that the information could not be verified.
Always include a short source line when a source URL is available.

OFFICIAL CONTEXT:
{context}"""

GENERAL_PROMPT = """You are a helpful general-purpose assistant used by a West Tripura citizen portal.
The official West Tripura knowledge base did not contain enough verified evidence for this question.
Answer general-knowledge questions naturally and concisely.
IMPORTANT: Do not fabricate West Tripura government-specific facts. If the user asks for an official West Tripura fact that was not verified, say it could not be verified from the official knowledge base.
Match the user's language: English, Bengali, or Benglish.
"""


class RAGService:
    def __init__(self, retrieval_service=None, llm=None):
        self.settings = get_settings()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or get_llm_provider(self.settings.llm_config)
        self.analyzer = QueryAnalyzer()
        self.reranker = RerankerService(self.settings.RERANKER_MODEL if self.settings.ENABLE_RERANKER else None)
        self.confidence = ConfidenceScorer()
        self.formatter = ResponseFormatter()
        self.cache = CacheService(self.settings.REDIS_URL, self.settings.CACHE_TTL)

    async def answer(self, query: str, top_k: int | None = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        analysis = self.analyzer.analyze(query)

        if analysis.intent.value == "conversational":
            thanks = bool(re.search(r"\b(thank|thanks)\b|ধন্যবাদ", query, re.I))
            return self._result(self.formatter.conversational(analysis.language, thanks), "conversational", [], t0, session_id)

        if analysis.intent.value == "general_knowledge":
            text = await self._general_fallback(query, analysis.language)
            return self._result(text, "general_llm", [], t0, session_id)

        cache_key = analysis.retrieval_query
        if self.settings.ENABLE_CACHE:
            cached = await self.cache.get(cache_key)
            if cached:
                cached["cache_hit"] = True
                cached["session_id"] = session_id
                return cached

        search_res = await self.retrieval_service.search(
            query=analysis.retrieval_query,
            top_k=max(top_k or self.settings.TOP_K, self.settings.RETRIEVAL_CANDIDATE_K),
            filters=analysis.filters,
        )
        candidates = search_res["results"]
        reranked = self.reranker.rank(analysis.retrieval_query, candidates, top_k=self.settings.RERANK_TOP_K)
        confidence = self.confidence.score(analysis.retrieval_query, reranked)

        if confidence.level == "low":
            # One cheap broadening pass before falling back.
            broad = await self.retrieval_service.search(query=query, top_k=self.settings.RETRIEVAL_CANDIDATE_K)
            reranked = self.reranker.rank(query, broad["results"], top_k=self.settings.RERANK_TOP_K)
            confidence = self.confidence.score(query, reranked)

        if confidence.level == "low":
            text = await self._general_fallback(query, analysis.language, official_query=True)
            result = self._result(text, "general_llm", [], t0, session_id, confidence.score, search_res)
        else:
            context_chunks = self.retrieval_service.expand_context(reranked[:self.settings.RERANK_TOP_K])
            text, sources = await self._grounded_answer(query, analysis.language, context_chunks)
            result = self._result(text, "official_rag", sources, t0, session_id, confidence.score, search_res)

        if self.settings.ENABLE_CACHE and result["mode"] == "official_rag":
            await self.cache.set(cache_key, result)
        return result

    async def _grounded_answer(self, query: str, language: str, chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        blocks, sources = [], []
        seen = set()
        for chunk in chunks:
            title = chunk.get("title") or chunk.get("metadata", {}).get("title") or "West Tripura document"
            content = chunk.get("content") or chunk.get("text") or ""
            url = chunk.get("url") or chunk.get("metadata", {}).get("url") or ""
            section = chunk.get("section") or chunk.get("metadata", {}).get("section") or ""
            if content:
                blocks.append(f"--- {title} | {section} ---\n{content}")
            if url and url not in seen:
                seen.add(url)
                sources.append({"title": title, "url": url, "section": section, "chunk_id": str(chunk.get("id") or chunk.get("chunk_id"))})
        if not blocks:
            return self.formatter.not_verified(language), sources
        prompt = GROUNDED_PROMPT.format(context="\n\n".join(blocks))
        answer = await self.llm.generate([{"role": "system", "content": prompt}, {"role": "user", "content": query}], temperature=0.15, max_tokens=700)
        return answer.strip(), sources

    async def _general_fallback(self, query: str, language: str, official_query: bool = False) -> str:
        prompt = GENERAL_PROMPT
        answer = await self.llm.generate([{"role": "system", "content": prompt}, {"role": "user", "content": query}], temperature=0.3, max_tokens=600)
        if official_query and "could not verify" not in answer.lower() and "couldn't verify" not in answer.lower():
            return self.formatter.not_verified(language)
        return answer.strip()

    @staticmethod
    def _result(answer: str, mode: str, sources: list[dict], started: float, session_id: str | None, confidence: float | None = None, search: dict | None = None) -> dict:
        return {
            "answer": answer,
            "sources": sources,
            "mode": mode,
            "grounded": mode == "official_rag",
            "confidence": confidence,
            "retrieval_query": (search or {}).get("retrieval_query"),
            "retrieval_trace": (search or {}).get("timing", {}),
            "timing_ms": round((time.perf_counter() - started) * 1000, 2),
            "session_id": session_id,
        }


_rag_service = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
