# West Tripura Citizen RAG

A production-oriented citizen information assistant built around one principle:

> **Retrieve verified official evidence first, then generate a simple answer citizens can understand.**

```text
Official Sources
      ↓
Crawl4AI + Document Discovery
      ↓
Clean + Metadata + Semantic Chunking
      ↓
Embeddings → Pinecone
      +
BM25 lexical index
      ↓
Hybrid Retrieval → RRF → Reranking
      ↓
Confidence / Grounding Gate
      ↓
Grounded LLM
      ↓
Answer + Source + Direct Document
      ↓
API / Telegram / WhatsApp
```

## Citizen experience

```text
Citizen:
"PRTC er jonno ki ki document lagbe?"

System:
1. Understand language and intent
2. Search semantic + exact matches
3. Rerank the strongest evidence
4. Generate a grounded answer
5. Return the official source and form when available
```

## Main components

- **FastAPI** — online RAG API
- **Pinecone** — dense vector search
- **BM25** — exact/lexical search
- **RRF + reranking** — relevance selection
- **Redis** — cache/session infrastructure
- **Crawl4AI + Playwright** — official-site ingestion
- **Telegram** — citizen channel
- **OpenWA + WhatsApp** — citizen channel
- **LLM provider** — grounded answer generation and safe fallback

## Knowledge pipeline

The crawler discovers official pages and document links. Documents such as PDF/DOC/DOCX/XLS/XLSX are treated as first-class knowledge: their text is extracted for retrieval while the original official URL is preserved for delivery.

```text
Website
 ↓
Pages + documents
 ↓
Preprocess + metadata
 ↓
Semantic chunks
 ↓
Embeddings + BM25
 ↓
Searchable knowledge base
```

## Grounding

The LLM is downstream of retrieval. If official evidence is insufficient, the system should not invent government facts. It can broaden retrieval or clearly state that verified information was not found.

## Presentation layers

```text
1. INGESTION  — collect official knowledge
2. KNOWLEDGE  — clean, chunk, embed, index
3. RETRIEVAL  — dense + BM25 + RRF + rerank
4. GENERATION  — grounded LLM + safe fallback
5. DELIVERY  — API + Telegram + WhatsApp + documents
```

See `README.md` and `docs/presentation-architecture.md` for the full architecture and operator workflow.
