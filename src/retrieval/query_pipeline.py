"""
query_pipeline.py
=================
Core RAG Retrieval and Generation Engine.
Uses NVIDIA NV-Embed-v1 for query embedding, Pinecone for vector retrieval,
and NVIDIA Chat API (Llama 3.1 70B) for answer generation.

Adds active web search fallback logic:
1. Pinecone Vector Search
2. DuckDuckGo site:westtripura.nic.in
3. DuckDuckGo site:tripura.gov.in
4. Default "Couldn't find information" fallback message
"""

from __future__ import annotations

import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from dotenv import load_dotenv
load_dotenv(_HERE.parent.parent / ".env")

from openai import OpenAI
from pinecone import Pinecone
import requests
from bs4 import BeautifulSoup

from src.ingestion.core.config import (
    NV_API_KEY,
    NV_API_BASE_URL,
    NV_EMBED_MODEL,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_HOST,
)

# New Chat API variables
NV_CHAT_API_KEY = os.getenv("NV_CHAT_API_KEY", "")
NV_CHAT_MODEL = "meta/llama-3.1-70b-instruct"

# Pinecone relevance score floor
RELEVANCE_THRESHOLD = 0.40


def clean_ddg_url(url: str) -> str:
    """Helper to clean redirect links that DuckDuckGo sometimes wraps."""
    if "uddg=" in url:
        parsed = urllib.parse.urlparse(url)
        queries = urllib.parse.parse_qs(parsed.query)
        if "uddg" in queries:
            return queries["uddg"][0]
    if url.startswith("//"):
        return "https:" + url
    return url


def search_duckduckgo(query: str, site_domain: str) -> List[Dict[str, str]]:
    """
    Search html.duckduckgo.com directly (no javascript, bypasses bot detection).
    Returns list of {'title': str, 'url': str, 'body': str}
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    url = "https://html.duckduckgo.com/html/"
    search_query = f"{query} site:{site_domain}"
    data = {"q": search_query}
    
    try:
        r = requests.post(url, data=data, headers=headers, timeout=8)
        if r.status_code != 200:
            return []
            
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for result in soup.find_all("div", class_="result"):
            title_tag = result.find("a", class_="result__url")
            snippet_tag = result.find("a", class_="result__snippet")
            if title_tag and snippet_tag:
                title = title_tag.get_text(strip=True)
                href = title_tag.get("href")
                snippet = snippet_tag.get_text(strip=True)
                
                clean_url = clean_ddg_url(href)
                results.append({
                    "title": title,
                    "url": clean_url,
                    "body": snippet
                })
        return results
    except Exception:
        return []


class RAGPipeline:
    def __init__(self):
        # Validate keys
        if not NV_API_KEY:
            raise ValueError("NV_API_KEY (embedding key) is missing in .env")
        if not NV_CHAT_API_KEY:
            raise ValueError("NV_CHAT_API_KEY is missing in .env")
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY is missing in .env")

        # Clients initialization
        self.embed_client = OpenAI(api_key=NV_API_KEY, base_url=NV_API_BASE_URL)
        self.chat_client = OpenAI(api_key=NV_CHAT_API_KEY, base_url=NV_API_BASE_URL)
        
        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        self.index = self.pc.Index(host=PINECONE_HOST)

    def embed_query(self, query: str) -> List[float]:
        """Embed the user query using NV-Embed-v1 with input_type='query'."""
        response = self.embed_client.embeddings.create(
            model=NV_EMBED_MODEL,
            input=[query],
            extra_body={"input_type": "query", "truncate": "END"},
            encoding_format="float",
        )
        return response.data[0].embedding

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve top_k matching chunks from Pinecone index."""
        query_vector = self.embed_query(query)
        res = self.index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
        
        results = []
        for match in res.matches:
            if match.score >= RELEVANCE_THRESHOLD:
                results.append({
                    "id": match.id,
                    "score": match.score,
                    "content": match.metadata.get("content", ""),
                    "title": match.metadata.get("title", ""),
                    "url": match.metadata.get("url", ""),
                    "section": match.metadata.get("section", ""),
                    "sub_section": match.metadata.get("sub_section", ""),
                })
        return results

    def answer(self, query: str) -> Dict[str, Any]:
        """Runs full RAG pipeline (Retrieve -> Answer) with DuckDuckGo fallback."""
        source_type = "Pinecone Vector DB"
        
        # 1. Pinecone Vector Search
        matches = self.retrieve(query, top_k=5)
        
        # 2. Fallback: Search westtripura.nic.in
        if not matches:
            print("  [Pipeline] Query below threshold in Pinecone. Trying site:westtripura.nic.in...")
            ddg_results = search_duckduckgo(query, "westtripura.nic.in")
            if ddg_results:
                source_type = "Live search (westtripura.nic.in)"
                matches = [{
                    "title": r["title"],
                    "url": r["url"],
                    "content": r["body"],
                    "section": "Web Search Results",
                    "sub_section": "westtripura.nic.in"
                } for r in ddg_results[:4]]
                
        # 3. Fallback: Search tripura.gov.in
        if not matches:
            print("  [Pipeline] Still no result. Trying site:tripura.gov.in...")
            ddg_results = search_duckduckgo(query, "tripura.gov.in")
            if ddg_results:
                source_type = "Live search (tripura.gov.in)"
                matches = [{
                    "title": r["title"],
                    "url": r["url"],
                    "content": r["body"],
                    "section": "Web Search Results",
                    "sub_section": "tripura.gov.in"
                } for r in ddg_results[:4]]

        # 4. Final Fallback: Not Found in any source
        if not matches:
            no_info_msg = (
                "I couldn't find this information in the available official government sources "
                "(West Tripura District database and state portals). Please check back later or "
                "visit the official port: https://westtripura.nic.in"
            )
            # Simple Bengali check
            if any(ord(char) >= 0x0980 and ord(char) <= 0x09FF for char in query):
                no_info_msg = (
                    "আমি উপলব্ধ অফিসিয়াল সরকারি উৎসগুলোতে (পশ্চিম ত্রিপুরা জেলা ডেটাবেস এবং রাজ্য পোর্টাল) "
                    "এই তথ্যটি খুঁজে পাইনি। অনুগ্রহ করে পরে আবার চেক করুন বা অফিসিয়াল পোর্টালে যান: https://westtripura.nic.in"
                )
            return {
                "answer": no_info_msg,
                "references": []
            }

        # Build context prompt
        context_blocks = []
        references = []
        seen_urls = set()
        
        for idx, match in enumerate(matches):
            context_blocks.append(
                f"[Source {idx+1}]\n"
                f"Title: {match['title']}\n"
                f"Section: {match.get('section', '')} > {match.get('sub_section', '')}\n"
                f"Content: {match['content']}\n"
            )
            # Collect unique URLs/sources
            url = match.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                references.append({
                    "title": match["title"],
                    "url": url,
                    "section": match.get("section", "Web Result")
                })

        context_str = "\n\n".join(context_blocks)

        # Build System Prompt suitable for general citizens of West Tripura
        system_prompt = (
            "You are 'West Tripura Chatbot', a helpful public service assistant. "
            "Your goal is to answer queries from general citizens truthfully, clearly, and concisely "
            "based strictly on the context block provided below.\n\n"
            f"Note on Sources: These documents are retrieved dynamically via: {source_type}.\n\n"
            "Guidelines:\n"
            "1. Answer the query in the language it was asked (e.g. if the user asks in Bengali, reply in polite Bengali. "
            "If in English, reply in plain English).\n"
            "2. Keep the answer direct and simple to understand for general citizens.\n"
            "3. If the context does not contain the answer, politely state that you do not have the information and direct them to the official district website (https://westtripura.nic.in).\n"
            "4. Do not invent details or assume anything not written in the context.\n\n"
            f"Context:\n{context_str}"
        )

        try:
            response = self.chat_client.chat.completions.create(
                model=NV_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.2,
                max_tokens=800,
            )
            answer_text = response.choices[0].message.content.strip()
        except Exception as e:
            answer_text = f"Error generating answer: {str(e)}"

        return {
            "answer": answer_text,
            "references": references
        }


# Quick standalone test
if __name__ == "__main__":
    pipeline = RAGPipeline()
    
    # Test local DB search
    test_q1 = "Who is the DM of West Tripura?"
    print(f"Testing Query 1 (Local RAG): '{test_q1}'")
    r1 = pipeline.answer(test_q1)
    print(f"Answer: {r1['answer']}")
    print(f"Sources: {r1['references']}")
    print("-" * 60)
    
    # Test live fallback search
    test_q2 = "What tourism packages are available for 8 days in Tripura?"
    print(f"Testing Query 2 (Fallback DDG): '{test_q2}'")
    r2 = pipeline.answer(test_q2)
    print(f"Answer: {r2['answer']}")
    print(f"Sources: {r2['references']}")
