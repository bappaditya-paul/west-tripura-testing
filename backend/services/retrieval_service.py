"""Hybrid retrieval with metadata filtering, RRF fusion and context expansion."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

from backend.core.config import get_settings
from backend.services.canonical_chunk_loader import get_canonical_chunk_loader
from backend.services.providers.bm25_retriever import get_bm25_retriever
from backend.services.providers.embedding import get_embedding_provider
from backend.services.providers.vector_store import get_vector_store
from backend.services.query_processor import QueryProcessor

logger = logging.getLogger("ragplatform.retrieval_service")


class RetrievalService:
    def __init__(self, vector_store=None, embedding=None, bm25=None):
        self.settings = get_settings()
        self.vector_store = vector_store or get_vector_store(self.settings.vector_db_config)
        self.embedding = embedding or get_embedding_provider(self.settings.embedding_config)
        self.bm25 = bm25 or get_bm25_retriever()
        self.query_processor = QueryProcessor()
        loader = get_canonical_chunk_loader()
        all_chunks = loader.load_all_chunks()
        self.chunk_lookup: Dict[str, Dict[str, Any]] = {c["chunk_id"]: c for c in all_chunks}

    async def search(self, query: str, top_k: int | None = None, filters: dict | None = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        top_k = top_k or getattr(self.settings, "TOP_K", 5)
        qp_res = self.query_processor.process(query)
        retrieval_query = qp_res["retrieval_query"]
        candidate_k = max(getattr(self.settings, "RETRIEVAL_CANDIDATE_K", 40), top_k * 6)

        emb_start = time.perf_counter()
        query_vector = (await self.embedding.embed([retrieval_query], input_type="query"))[0]
        embedding_ms = (time.perf_counter() - emb_start) * 1000

        search_start = time.perf_counter()
        dense_task = asyncio.create_task(self.vector_store.query(query_vector, top_k=candidate_k, filters=filters))
        sparse_task = asyncio.create_task(self._query_bm25(retrieval_query, candidate_k))
        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task, return_exceptions=True)
        search_ms = (time.perf_counter() - search_start) * 1000
        if isinstance(dense_results, Exception):
            logger.exception("Dense retrieval failed", exc_info=dense_results)
            dense_results = []
        if isinstance(sparse_results, Exception):
            logger.exception("BM25 retrieval failed", exc_info=sparse_results)
            sparse_results = []

        fused = self._reciprocal_rank_fusion(
            dense_results, sparse_results, candidate_k,
            rrf_k=getattr(self.settings, "RRF_K", 60),
            alpha=getattr(self.settings, "HYBRID_ALPHA", 0.6),
            max_chunks_per_url=getattr(self.settings, "MAX_CHUNKS_PER_URL", 3),
        )
        total_ms = (time.perf_counter() - t0) * 1000
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "language": qp_res["language"],
            "results": fused,
            "timing": {
                "query_processing_ms": round((emb_start - t0) * 1000, 2),
                "embedding_ms": round(embedding_ms, 2),
                "search_ms": round(search_ms, 2),
                "total_ms": round(total_ms, 2),
            },
        }

    async def _query_bm25(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.bm25.query, query, top_k)

    def _reciprocal_rank_fusion(self, dense_results, sparse_results, top_k, rrf_k=60, alpha=0.6, max_chunks_per_url=3):
        scores: Dict[str, float] = {}
        items: Dict[str, Dict[str, Any]] = {}
        for rank, item in enumerate(dense_results, start=1):
            cid = str(item.get("id") or item.get("chunk_id"))
            items[cid] = item
            item["source"] = "pinecone"
            scores[cid] = scores.get(cid, 0.0) + alpha / (rrf_k + rank)
        for rank, item in enumerate(sparse_results, start=1):
            cid = str(item.get("id") or item.get("chunk_id"))
            if cid not in items:
                items[cid] = item
                item["source"] = "bm25"
            else:
                items[cid]["source"] = "hybrid_rrf"
            scores[cid] = scores.get(cid, 0.0) + (1.0 - alpha) / (rrf_k + rank)

        sorted_ids = sorted(scores, key=scores.get, reverse=True)
        url_counts: Dict[str, int] = {}
        final: List[Dict[str, Any]] = []
        for cid in sorted_ids:
            chunk = items[cid]
            url = chunk.get("url") or chunk.get("metadata", {}).get("url") or ""
            count = url_counts.get(url, 0)
            if not url or count < max_chunks_per_url:
                chunk["score"] = round(scores[cid], 5)
                final.append(chunk)
                if url:
                    url_counts[url] = count + 1
            if len(final) >= top_k:
                break
        return final

    def expand_context(self, primary_chunks: List[Dict[str, Any]], max_extra_chunks: int = 2) -> List[Dict[str, Any]]:
        expanded: List[Dict[str, Any]] = []
        seen_ids = set()
        for chunk in primary_chunks:
            cid = str(chunk.get("id") or chunk.get("chunk_id"))
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            expanded.append(chunk)
            info = self.chunk_lookup.get(cid, {})
            doc_id = info.get("document_id")
            section = info.get("section")
            candidates = [info.get("parent_chunk_id"), info.get("prev_chunk_id"), info.get("next_chunk_id")]
            added = 0
            for related_id in candidates:
                if not related_id or related_id in seen_ids or related_id not in self.chunk_lookup:
                    continue
                related = self.chunk_lookup[related_id]
                if related.get("document_id") == doc_id and (not section or related.get("section") == section):
                    seen_ids.add(related_id)
                    expanded.append(related)
                    added += 1
                    if added >= max_extra_chunks:
                        break
        return expanded
