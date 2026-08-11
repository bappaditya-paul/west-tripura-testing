"""
Phase 0 Baseline Benchmark Script
==================================
Measures current baseline latency, retrieval top scores, source types,
and answer quality across:
1. Short Factual Query
2. Long Multi-Intent Query
3. Benglish Informal Query
4. Native Bengali Query
"""

import sys
import time
import asyncio
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.retrieval.query_pipeline import RAGPipeline

TEST_QUERIES = [
    {
        "category": "1. Short Factual",
        "query": "Who is the District Magistrate of West Tripura?"
    },
    {
        "category": "2. Long Multi-Intent",
        "query": "How can I apply for a marriage certificate in West Tripura, what documents are required, and where is the office located?"
    },
    {
        "category": "3. Benglish Informal",
        "query": "Dada West Tripura sub divisional office te EWS certificate application process kothay pabo ar ki ki lagbe?"
    },
    {
        "category": "4. Native Bengali Script",
        "query": "পশ্চিম ত্রিপুরা জেলায় বিবাহ নিবন্ধনের জন্য কি কি নথি প্রয়োজন?"
    }
]


def run_baseline_benchmark():
    print("=" * 80)
    print("STARTING PHASE 0 BASELINE BENCHMARK")
    print("=" * 80)
    
    start_init = time.perf_counter()
    pipeline = RAGPipeline()
    init_time = (time.perf_counter() - start_init) * 1000
    print(f"Pipeline Initialization Time: {init_time:.2f} ms\n")

    results_summary = []

    for item in TEST_QUERIES:
        cat = item["category"]
        q = item["query"]
        print(f"\n--- Testing [{cat}] ---")
        print(f"Query: \"{q}\"")

        start_q = time.perf_counter()
        res = pipeline.answer(q)
        total_latency = (time.perf_counter() - start_q) * 1000

        ans = res.get("answer", "")
        refs = res.get("references", [])
        
        print(f"Latency: {total_latency:.2f} ms")
        print(f"Citations count: {len(refs)}")
        print(f"Answer Preview (first 150 chars): {ans[:150]}...")
        
        results_summary.append({
            "category": cat,
            "query": q,
            "latency_ms": round(total_latency, 2),
            "citations_count": len(refs),
            "answer_length": len(ans),
            "sample_answer": ans[:100].replace("\n", " ")
        })

    print("\n" + "=" * 80)
    print("PHASE 0 BASELINE BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"{'Category':<25} | {'Latency (ms)':<12} | {'Citations':<10} | {'Answer Length':<15}")
    print("-" * 80)
    for r in results_summary:
        print(f"{r['category']:<25} | {r['latency_ms']:<12} | {r['citations_count']:<10} | {r['answer_length']:<15}")
    print("=" * 80)


if __name__ == "__main__":
    run_baseline_benchmark()
