"""
backend/services/rag_service.py
================================
RAG Service Orchestrator combining RetrievalService and LLMProvider.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Any, Optional

from backend.core.config import get_settings
from backend.services.providers.llm import get_llm_provider
from backend.services.retrieval_service import RetrievalService

logger = logging.getLogger("ragplatform.rag_service")

SYSTEM_PROMPT = """You are the official West Tripura District Information Assistant — a knowledgeable, trustworthy, and professional assistant for citizens of West Tripura, India.

Your sole purpose is to answer questions about:
- District offices, departments, and officials (DM, ADM, SDO, BDO)
- Government schemes and public services
- Notifications, circulars, and guidelines
- Contact details and procedures

CRITICAL RULES:
1. Answer ONLY using the provided Context below.
2. If the answer is not present in Context, state clearly: "I don't have verified information about this. Please visit westtripura.nic.in or contact the district helpline."
3. Cite the document/source title at the end of your answer.
4. Keep answers clear, accurate, and concise.

Context:
{context}"""


class RAGService:
    def __init__(self, retrieval_service=None, llm=None):
        self.settings = get_settings()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or get_llm_provider(self.settings.llm_config)

    async def answer(self, query: str, top_k: int = 5, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Full RAG Pipeline:
        Citizen Query ➔ Preprocessing ➔ RRF Hybrid Search ➔ Context Expansion ➔ LLM Answer + Sources.
        """
        t0 = time.perf_counter()

        # Step 1: Retrieval with RRF
        search_res = await self.retrieval_service.search(query=query, top_k=top_k)
        primary_results = search_res["results"]

        # Step 2: Context Expansion
        expanded_chunks = self.retrieval_service.expand_context(primary_results)

        # Build Context String for LLM
        context_blocks = []
        sources = []
        seen_urls = set()

        for chunk in expanded_chunks:
            title = chunk.get("title") or chunk.get("metadata", {}).get("title") or "West Tripura Document"
            content = chunk.get("text") or chunk.get("content") or ""
            url = chunk.get("url") or chunk.get("metadata", {}).get("url") or ""
            section = chunk.get("section") or chunk.get("metadata", {}).get("section") or ""

            context_blocks.append(f"--- Document: {title} (Section: {section}) ---\n{content}")

            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({"title": title, "url": url, "section": section, "chunk_id": str(chunk.get("id") or chunk.get("chunk_id"))})

        context_str = "\n\n".join(context_blocks) if context_blocks else "No relevant context found."

        # Step 3: LLM Generation
        prompt = SYSTEM_PROMPT.format(context=context_str)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]

        try:
            answer_text = await self.llm.generate(messages=messages, temperature=0.2, max_tokens=1024)
        except Exception as exc:
            logger.error("LLM Generation failed: %s", exc)
            answer_text = "I encountered an error generating the answer. Please try again later."

        t1 = time.perf_counter()
        total_ms = round((t1 - t0) * 1000, 2)

        return {
            "answer": answer_text,
            "sources": sources,
            "retrieval_query": search_res["retrieval_query"],
            "timing_ms": total_ms,
            "session_id": session_id,
        }


# Singleton accessor
_rag_service = None

def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
