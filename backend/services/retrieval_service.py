"""
backend/services/retrieval_service.py
======================================
Multi-stage Retrieval Service with Rank-Based RRF, Section-Aware Context Expansion,
and Granular Observability Timings.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional

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

        # Load canonical chunk lookup table for context expansion & section checking
        loader = get_canonical_chunk_loader()
        all_chunks = loader.load_all_chunks()
        self.chunk_lookup: Dict[str, Dict[str, Any]] = {c["chunk_id"]: c for c in all_chunks}

    async def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Executes parallel dense + sparse retrieval, rank-based RRF fusion,
        URL deduplication, and returns detailed diagnostic timing metrics.
        """
        t0 = time.perf_counter()

        # Step 1: Query Preprocessing
        qp_res = self.query_processor.process(query)
        retrieval_query = qp_res["retrieval_query"]
        t1 = time.perf_counter()
        query_processing_ms = (t1 - t0) * 1000

        # Step 2: Dense & Sparse Retrieval
        t_emb_start = time.perf_counter()
        query_vector = (await self.embedding.embed([retrieval_query], input_type="query"))[0]
        t_emb_end = time.perf_counter()
        embedding_ms = (t_emb_end - t_emb_start) * 1000

        candidate_k = max(top_k * 4, 20)

        # Execute Pinecone & BM25 in parallel
        t_search_start = time.perf_counter()
        dense_task = asyncio.create_task(self.vector_store.query(query_vector, top_k=candidate_k))
        sparse_task = asyncio.create_task(self._query_bm25(retrieval_query, candidate_k))

        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task, return_exceptions=True)
        t_search_end = time.perf_counter()

        pinecone_ms = (t_search_end - t_search_start) * 1000
        bm25_ms = pinecone_ms  # Ran in parallel

        if isinstance(dense_results, Exception):
            logger.error("Dense vector search error: %s", dense_results)
            dense_results = []
        if isinstance(sparse_results, Exception):
            logger.error("Sparse BM25 search error: %s", sparse_results)
            sparse_results = []

        # Step 3: Rank-Based Reciprocal Rank Fusion (RRF)
        t_fusion_start = time.perf_counter()
        rrf_results = self._reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=top_k,
            rrf_k=getattr(self.settings, "RRF_K", 60),
            alpha=getattr(self.settings, "HYBRID_ALPHA", 0.6),
            max_chunks_per_url=getattr(self.settings, "MAX_CHUNKS_PER_URL", 3),
        )
        t_fusion_end = time.perf_counter()
        fusion_ms = (t_fusion_end - t_fusion_start) * 1000

        total_ms = (t_fusion_end - t0) * 1000

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "language": qp_res["language"],
            "results": rrf_results,
            "timing": {
                "query_processing_ms": round(query_processing_ms, 2),
                "embedding_ms": round(embedding_ms, 2),
                "pinecone_ms": round(pinecone_ms, 2),
                "bm25_ms": round(bm25_ms, 2),
                "fusion_ms": round(fusion_ms, 2),
                "total_ms": round(total_ms, 2),
            },
        }

    async def _query_bm25(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.bm25.query, query, top_k)

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[Dict[str, Any]],
        sparse_results: List[Dict[str, Any]],
        top_k: int,
        rrf_k: int = 60,
        alpha: float = 0.6,
        max_chunks_per_url: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Rank-based Reciprocal Rank Fusion formula:
        RRF(d) = alpha / (k + dense_rank) + (1 - alpha) / (k + sparse_rank)
        """
        scores: Dict[str, float] = {}
        items: Dict[str, Dict[str, Any]] = {}

        # Process Dense Ranks
        for rank, item in enumerate(dense_results, start=1):
            cid = str(item.get("id") or item.get("chunk_id"))
            items[cid] = item
            item["source"] = "pinecone"
            scores[cid] = scores.get(cid, 0.0) + (alpha / (rrf_k + rank))

        # Process Sparse Ranks
        for rank, item in enumerate(sparse_results, start=1):
            cid = str(item.get("id") or item.get("chunk_id"))
            if cid not in items:
                items[cid] = item
                item["source"] = "bm25"
            else:
                items[cid]["source"] = "hybrid_rrf"
            scores[cid] = scores.get(cid, 0.0) + ((1.0 - alpha) / (rrf_k + rank))

        # Sort by RRF score descending
        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

        # Apply URL Deduplication (Max N chunks per URL)
        url_counts: Dict[str, int] = {}
        final_results: List[Dict[str, Any]] = []

        for cid in sorted_ids:
            chunk = items[cid]
            url = chunk.get("url") or chunk.get("metadata", {}).get("url") or ""
            count = url_counts.get(url, 0)
            if not url or count < max_chunks_per_url:
                chunk["score"] = round(scores[cid], 5)
                final_results.append(chunk)
                if url:
                    url_counts[url] = count + 1

            if len(final_results) >= top_k:
                break

        return final_results

    def expand_context(self, primary_chunks: List[Dict[str, Any]], max_extra_chunks: int = 2) -> List[Dict[str, Any]]:
        """
        Section-aware context expansion: Retrieves adjacent prev_chunk_id / next_chunk_id
        only when in the same document and heading context.
        """
        expanded: List[Dict[str, Any]] = []
        seen_ids = set()

        for chunk in primary_chunks:
            cid = str(chunk.get("id") or chunk.get("chunk_id"))
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            expanded.append(chunk)

            # Check if canonical metadata contains adjacent links
            canonical_info = self.chunk_lookup.get(cid, {})
            doc_id = canonical_info.get("document_id")
            section = canonical_info.get("section")
            prev_id = canonical_info.get("prev_chunk_id")
            next_id = canonical_info.get("next_chunk_id")

            # Try adjacent prev chunk
            if prev_id and prev_id not in seen_ids and prev_id in self.chunk_lookup:
                prev_chunk = self.chunk_lookup[prev_id]
                if prev_chunk.get("document_id") == doc_id and prev_chunk.get("section") == section:
                    seen_ids.add(prev_id)
                    expanded.append(prev_chunk)

            # Try adjacent next chunk
            if next_id and next_id not in seen_ids and next_id in self.chunk_lookup:
                next_chunk = self.chunk_lookup[next_id]
                if next_chunk.get("document_id") == doc_id and next_chunk.get("section") == section:
                    seen_ids.add(next_id)
                    expanded.append(next_chunk)

        return expanded
