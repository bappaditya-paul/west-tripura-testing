"""
backend/services/ingestion_service.py
======================================
Ingestion service for Crawling and Document Uploads.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any

from backend.services.canonical_chunk_loader import get_canonical_chunk_loader
from backend.services.providers.bm25_retriever import get_bm25_retriever
from backend.services.providers.embedding import get_embedding_provider
from backend.services.providers.vector_store import get_vector_store
logger = logging.getLogger("ragplatform.ingestion_service")


class IngestionService:
    def __init__(self):
        self.output_pages_dir = Path("output/pages")
        self.processed_chunks_dir = Path("processed_chunks")
        self.uploads_dir = Path("uploads")
        self.output_pages_dir.mkdir(parents=True, exist_ok=True)
        self.processed_chunks_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    async def run_crawl_only(self, target_url: str, max_pages: int = 100) -> Dict[str, Any]:
        """
        POST /crawl MUST ONLY perform website crawling to output/pages/.
        Does NOT run chunking, embedding, or indexing.
        """
        import httpx
        from bs4 import BeautifulSoup

        crawled_count = 0
        failed_count = 0

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(target_url, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text = soup.get_text(separator="\n", strip=True)

                    page_file = self.output_pages_dir / f"page_0.html"
                    page_file.write_text(resp.text, encoding="utf-8")
                    crawled_count = 1
                else:
                    failed_count = 1

            return {
                "status": "completed" if crawled_count > 0 else "failed",
                "url": target_url,
                "pages_crawled": crawled_count,
                "failed": failed_count,
                "output_dir": str(self.output_pages_dir),
                "message": f"Successfully crawled {crawled_count} page(s) to {self.output_pages_dir}"
            }
        except Exception as exc:
            logger.error("Crawl failed for %s: %s", target_url, exc)
            return {
                "status": "failed",
                "url": target_url,
                "pages_crawled": 0,
                "failed": 1,
                "output_dir": str(self.output_pages_dir),
                "message": f"Crawl failed: {str(exc)}"
            }

    async def ingest_uploaded_file(self, filename: str, content: bytes) -> Dict[str, Any]:
        """
        Accepts uploaded document, writes chunk to processed_chunks/,
        embeds vector, and updates Pinecone + BM25.
        """
        doc_id = str(uuid.uuid4())[:8]
        clean_filename = f"{doc_id}_{Path(filename).name}"
        saved_path = self.uploads_dir / clean_filename

        with open(saved_path, "wb") as f:
            f.write(content)

        text_content = content.decode("utf-8", errors="ignore")
        if not text_content.strip():
            text_content = f"Uploaded document: {filename}"

        # Write canonical chunk to processed_chunks/
        chunk_id = f"upload-{doc_id}-0"
        chunk_data = {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "content": text_content,
            "title": filename,
            "url": str(saved_path),
            "section": "User Upload",
        }

        chunk_file = self.processed_chunks_dir / f"{chunk_id}.json"
        import json
        with open(chunk_file, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, indent=2)

        from backend.core.config import get_settings
        settings = get_settings()
        emb_provider = get_embedding_provider(settings.embedding_config)
        vs_provider = get_vector_store(settings.vector_db_config)

        vectors = await emb_provider.embed([text_content], input_type="passage")
        vector_record = {
            "id": chunk_id,
            "values": vectors[0],
            "metadata": {
                "title": filename,
                "url": str(saved_path),
                "section": "User Upload",
                "text": text_content[:500],
            }
        }
        await vs_provider.upsert([vector_record])

        # Reload BM25 index with new canonical chunk
        bm25 = get_bm25_retriever()
        bm25.load()

        return {
            "status": "completed",
            "filename": filename,
            "document_id": doc_id,
            "chunks_created": 1,
            "embedded_count": 1,
            "pinecone_upserted": 1,
            "bm25_indexed": 1,
            "message": f"Successfully ingested and indexed file {filename}"
        }
