"""
test_post_chat_suite.py
========================
Executes test queries against POST http://localhost:8001/chat
and prints formatted results (Answer, Sources, Timing, Retrieval Query).
"""

import json
import time
import requests

API_URL = "http://localhost:8001/chat"

TEST_QUESTIONS = [
    {
        "category": "Simple English Query",
        "query": "who is the dm of west tripura?"
    },
    {
        "category": "Bengali Script Query",
        "query": "পশ্চিম ত্রিপুরার ডিএম কে?"
    },
    {
        "category": "Benglish Query (Abbreviation Expansion)",
        "query": "sadar sdm office e prtc section e kara ache?"
    },
    {
        "category": "Multi-Constraint Query",
        "query": "What are the names and contact numbers of ADMs in West Tripura?"
    },
    {
        "category": "Election / Department Query",
        "query": "Who is the District Election Officer of West Tripura?"
    }
]


def run_tests():
    print("==========================================================================")
    print("🚀 STARTING POST /chat ENDPOINT VERIFICATION TEST SUITE")
    print("==========================================================================\n")

    for i, item in enumerate(TEST_QUESTIONS, 1):
        cat = item["category"]
        q = item["query"]
        print(f"[{i}/{len(TEST_QUESTIONS)}] [{cat}]")
        print(f"❓ Question: {q}")

        start = time.time()
        try:
            resp = requests.post(API_URL, json={"query": q}, timeout=300)
            elapsed = time.time() - start

            if resp.status_code == 200:
                data = resp.json()
                print(f"⏱️ Response Time: {elapsed:.2f}s")
                print(f"🔍 Normalized Query: {data.get('retrieval_query')}")
                print(f"💬 Answer:\n{data.get('answer')}\n")
                
                sources = data.get("sources", [])
                print(f"📖 Sources ({len(sources)}):")
                for s in sources:
                    title = s.get("title", "Doc")
                    sec = s.get("section", "")
                    url = s.get("url", "")
                    print(f"   • [{sec} - {title}]({url})")
            else:
                print(f"❌ Failed HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            print(f"💥 Exception: {exc}")

        print("-" * 75 + "\n")


if __name__ == "__main__":
    run_tests()
