from __future__ import annotations

import asyncio
import re
import time
import uuid
import urllib.parse
from typing import Any, AsyncIterator, Optional

import httpx
from bs4 import BeautifulSoup

from backend.core.config import get_settings
from backend.services.conversation import store as conversation_store
from backend.services.interfaces.base import EmbeddingInterface, LLMInterface, VectorStoreInterface
from backend.services.providers.vector_store import get_vector_store
from backend.services.providers.llm import get_llm_provider
from backend.services.providers.bm25_retriever import get_bm25_retriever

ABBREV_PATTERN = re.compile(r'\b(SDO|BDO|DM|DC|DRDA|SDM|ADM|BDO|CEO|CM|MP|MLA)\b', re.IGNORECASE)

SYSTEM_PROMPT = """You are the official West Tripura District Information Assistant — a knowledgeable, trustworthy, and professional assistant for citizens of West Tripura, India.
Your sole purpose is to answer questions about:
- District offices, departments, and officials
- Government schemes and public services
- Notifications, circulars, and guidelines
- Recruitment and eligibility information
- Contact details and procedures

CRITICAL RULES — Follow these without exception:
1. Answer ONLY from the provided context. Never add information from memory or general knowledge.
2. If the context does not contain the answer, say exactly: "I don't have verified information about this. Please visit westtripura.nic.in or call the district helpline."
3. NEVER invent or guess: names, phone numbers, email addresses, dates, statistics, designations, or officials. If it is not in the context, it does not exist.
4. Always cite your sources by referencing the source title at the end of your answer.
5. If the question is in Bengali (বাংলা), answer in Bengali. If in English, answer in English.
6. Keep answers concise (under 200 words unless detail is explicitly requested).
7. Use simple, clear language that any citizen can understand.
8. For contact details, always remind the user to verify directly with the office.

Context:
{context}"""

REWRITE_PROMPT = """You are a search query optimizer for a West Tripura government information system.
Given a conversation history and a new user question, rewrite the question into a clear,
specific, retrieval-optimized search query.
Rules:
- Expand abbreviations (SDO, BDO, DM, DC, DRDA, etc.)
- Resolve pronouns using conversation history ("it", "they", "the office", etc.)
- Add geographic context if missing ("West Tripura" if not mentioned)
- Make it self-contained (no reference to previous turns needed)
- Return ONLY the rewritten query, nothing else. No explanation.

Conversation history:
{history}
New question: {question}
Rewritten query:"""


class RAGService:
    def __init__(
        self,
        vector_store: VectorStoreInterface,
        embedding: EmbeddingInterface,
        llm: LLMInterface,
    ):
        self.vector_store = vector_store
        self.embedding = embedding
        self.llm = llm
        self.settings = get_settings()
        self._bm25 = None

    @classmethod
    def from_settings(cls, settings=None) -> "RAGService":
        settings = settings or get_settings()
        vs = get_vector_store(settings.vector_db_config)
        from backend.services.providers.embedding import get_embedding_provider
        emb = get_embedding_provider(settings.embedding_config)
        llm = get_llm_provider(settings.llm_config)
        inst = cls(vector_store=vs, embedding=emb, llm=llm)
        inst._bm25 = get_bm25_retriever()
        return inst

    def reset_session(self, session_id: str):
        conversation_store.reset_session(session_id)

    def _should_rewrite(self, query: str, history: list) -> bool:
        if history:
            return True
        if len(query.split()) < 6:
            return True
        if ABBREV_PATTERN.search(query):
            return True
        return False

    async def _rewrite_query(self, query: str, session_id: str) -> str:
        history = conversation_store.get_history(session_id)
        if not self._should_rewrite(query, history):
            return query
        history_str = conversation_store.format_history(session_id)
        prompt = REWRITE_PROMPT.format(history=history_str or "No previous conversation.", question=query)
        messages = [{"role": "system", "content": prompt}]
        try:
            rewritten = await self.llm.generate(messages, temperature=0, max_tokens=100)
            return rewritten.strip() or query
        except Exception:
            return query

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self.embedding.embed([query], input_type="query")
        return vectors[0]

    def _normalize_scores(self, results: list[dict]) -> list[dict]:
        if not results:
            return results
        scores = [r.get("score", 0) for r in results]
        max_s = max(scores)
        if max_s < 1e-6:
            return results
        for r in results:
            r["score"] = r.get("score", 0) / max_s
        return results

    def _dedup_by_url(self, results: list[dict], max_chunks_per_url: int = 1) -> list[dict]:
        url_counts = {}
        deduped = []
        for r in results:
            url = r.get("url", "")
            count = url_counts.get(url, 0)
            if count < max_chunks_per_url:
                deduped.append(r)
                url_counts[url] = count + 1
        return deduped

    def _fuse_hybrid(self, vector_results: list[dict], bm25_results: list[dict], top_k: int) -> list[dict]:
        merged: dict[str, dict] = {}
        for r in vector_results:
            rid = r.get("id", "")
            r["_hybrid_score"] = 0.7 * r.get("score", 0)
            merged[rid] = r
        for r in bm25_results:
            rid = r.get("id", "")
            bm25_score = 0.3 * r.get("score", 0)
            if rid in merged:
                merged[rid]["_hybrid_score"] += bm25_score
            else:
                r["_hybrid_score"] = bm25_score
                r["score"] = 0
                merged[rid] = r
        sorted_results = sorted(merged.values(), key=lambda x: x["_hybrid_score"], reverse=True)
        for r in sorted_results:
            r["score"] = r.pop("_hybrid_score")
        return sorted_results[:top_k]

    async def retrieve(self, query: str, top_k: int = 5, filters: dict = None) -> list[dict]:
        candidate_k = max(top_k * 4, 20)
        vector_task = asyncio.create_task(self._vector_retrieve(query, candidate_k, filters))
        bm25_task = asyncio.create_task(self._bm25_retrieve(query, candidate_k))
        vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task, return_exceptions=True)
        if isinstance(vector_results, Exception):
            vector_results = []
        if isinstance(bm25_results, Exception):
            bm25_results = []

        # Deduplicate individually first by URL to ensure diversity
        vector_results = self._dedup_by_url(vector_results, max_chunks_per_url=1)
        bm25_results = self._dedup_by_url(bm25_results, max_chunks_per_url=1)

        # Normalize relative to max score of the deduplicated candidate set
        vector_results = self._normalize_scores(vector_results)
        bm25_results = self._normalize_scores(bm25_results)

        hybrid = self._fuse_hybrid(vector_results, bm25_results, top_k)
        threshold = self.settings.RELEVANCE_THRESHOLD
        return [r for r in hybrid if r.get("score", 0) >= threshold]

    async def _vector_retrieve(self, query: str, top_k: int, filters: dict = None) -> list[dict]:
        vector = await self.embed_query(query)
        results = await self.vector_store.query(vector, top_k=top_k, filters=filters)
        return results

    async def _bm25_retrieve(self, query: str, top_k: int) -> list[dict]:
        if self._bm25 is None:
            return []
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self._bm25.query, query, top_k)
        return results

    async def search_duckduckgo(self, query: str, site_domain: str) -> list[dict]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        data = {"q": f"{query} site:{site_domain}"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data=data,
                    headers=headers,
                    timeout=8,
                )
                if resp.status_code != 200:
                    return []
                soup = BeautifulSoup(resp.text, "html.parser")
                results = []
                for div in soup.find_all("div", class_="result"):
                    title_tag = div.find("a", class_="result__url")
                    snippet_tag = div.find("a", class_="result__snippet")
                    if title_tag and snippet_tag:
                        href = title_tag.get("href", "")
                        if "uddg=" in href:
                            parsed = urllib.parse.urlparse(href)
                            qs = urllib.parse.parse_qs(parsed.query)
                            if "uddg" in qs:
                                href = qs["uddg"][0]
                        results.append({
                            "title": title_tag.get_text(strip=True),
                            "url": href,
                            "content": snippet_tag.get_text(strip=True),
                            "section": "Web Search",
                        })
                return results
        except Exception:
            return []

    async def answer(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        filters: dict = None,
        reset: bool = False,
    ) -> dict:
        start = time.perf_counter()
        session_id = session_id or str(uuid.uuid4())[:8]

        if reset:
            conversation_store.reset_session(session_id)
            return {
                "answer": "Your conversation has been reset. How can I help you?",
                "references": [],
                "source_type": "reset",
                "latency_ms": 0,
                "session_id": session_id,
            }

        source_type = "vector_db"
        rewritten_query = await self._rewrite_query(query, session_id)

        oversample_k = top_k * 4
        matches = await self.retrieve(rewritten_query, top_k=oversample_k, filters=filters)

        threshold = self.settings.RELEVANCE_THRESHOLD
        filtered = [m for m in matches if m.get("score", 0) >= threshold]
        seen_urls = set()
        deduped = []
        for m in sorted(filtered, key=lambda x: x.get("score", 0), reverse=True):
            url = m.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            deduped.append(m)

        matches = deduped[:top_k]

        if not matches:
            ddg = await self.search_duckduckgo(rewritten_query, "westtripura.nic.in")
            if ddg:
                source_type = "duckduckgo_westtripura"
                matches = ddg[:4]

        if not matches:
            ddg = await self.search_duckduckgo(rewritten_query, "tripura.gov.in")
            if ddg:
                source_type = "duckduckgo_tripura"
                matches = ddg[:4]

        if not matches:
            conversation_store.add_turn(session_id, query, "I couldn't find this information in the available official sources.")
            return {
                "answer": (
                    "I couldn't find this information in the available official sources. "
                    "Please check back later or visit the official portal."
                ),
                "references": [],
                "source_type": "none",
                "latency_ms": (time.perf_counter() - start) * 1000,
                "session_id": session_id,
            }

        context_blocks = []
        references = []
        seen_urls_ref = set()
        for idx, m in enumerate(matches):
            context_blocks.append(
                f"[Source {idx+1}]\n"
                f"Title: {m.get('title', '')}\n"
                f"Section: {m.get('section', '')}\n"
                f"Content: {m.get('content', '')}\n"
            )
            url = m.get("url", "")
            if url and url not in seen_urls_ref:
                seen_urls_ref.add(url)
                references.append({"title": m.get("title", ""), "url": url, "section": m.get("section", "")})

        context_str = "\n\n".join(context_blocks)
        system_prompt = SYSTEM_PROMPT.format(context=context_str)

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}]
        try:
            answer_text = await self.llm.generate(messages, temperature=0.2, max_tokens=800)
        except Exception as e:
            answer_text = f"Error generating answer: {str(e)}"

        conversation_store.add_turn(session_id, query, answer_text)

        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "answer": answer_text,
            "references": references,
            "source_type": source_type,
            "latency_ms": round(latency_ms, 1),
            "session_id": session_id,
        }

    async def answer_stream(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
    ) -> AsyncIterator[str]:
        session_id = session_id or str(uuid.uuid4())[:8]

        rewritten_query = await self._rewrite_query(query, session_id)
        oversample_k = top_k * 4
        matches = await self.retrieve(rewritten_query, top_k=oversample_k)
        source_type = "vector_db"

        threshold = self.settings.RELEVANCE_THRESHOLD
        filtered = [m for m in matches if m.get("score", 0) >= threshold]
        seen_urls = set()
        deduped = []
        for m in sorted(filtered, key=lambda x: x.get("score", 0), reverse=True):
            url = m.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            deduped.append(m)
        matches = deduped[:top_k]

        if not matches:
            ddg = await self.search_duckduckgo(rewritten_query, "westtripura.nic.in")
            if ddg:
                source_type = "duckduckgo_westtripura"
                matches = ddg[:4]

        if not matches:
            ddg = await self.search_duckduckgo(rewritten_query, "tripura.gov.in")
            if ddg:
                source_type = "duckduckgo_tripura"
                matches = ddg[:4]

        if not matches:
            yield '{"answer": "I could not find relevant information.", "references": [], "source_type": "none"}'
            return

        context_blocks = []
        references = []
        seen_urls_ref = set()
        for idx, m in enumerate(matches):
            context_blocks.append(f"[Source {idx+1}] {m.get('content', '')}")
            url = m.get("url", "")
            if url and url not in seen_urls_ref:
                seen_urls_ref.add(url)
                references.append({"title": m.get("title", ""), "url": url, "section": m.get("section", "")})

        context_str = "\n\n".join(context_blocks)
        system_prompt = SYSTEM_PROMPT.format(context=context_str)
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}]

        import json
        full_answer = ""
        async for chunk in self.llm.generate_stream(messages, temperature=0.2, max_tokens=800):
            full_answer += chunk
            yield chunk

        conversation_store.add_turn(session_id, query, full_answer)

        final = json.dumps({"references": references, "source_type": source_type, "session_id": session_id})
        yield f"\n\n{final}"
