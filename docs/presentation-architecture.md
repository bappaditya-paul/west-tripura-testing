# West Tripura Citizen RAG — Presentation Architecture

## Executive view

```text
Official Government Sources
        ↓
Crawl + Document Discovery
        ↓
Clean + Metadata + Chunking
        ↓
Embeddings + Pinecone
        +
BM25
        ↓
Hybrid Retrieval + RRF
        ↓
Neural Reranking
        ↓
Confidence / Grounding Gate
        ↓
Grounded LLM Response
        ↓
Sources + Direct Documents
        ↓
API / Telegram / WhatsApp
```

## Why RAG?

The assistant is designed for government information where correctness and traceability matter. Retrieval provides the evidence before generation, so the LLM is not the primary source of official facts.

## Why hybrid retrieval?

- Dense retrieval understands semantic meaning.
- BM25 handles exact government terminology, form names, acronyms and contact details.
- RRF combines complementary retrieval signals.
- Reranking evaluates the strongest candidates against the actual question.

## Why documents are first-class data

A government form or notification has two values: its text can answer a question, and the original file can be delivered to the citizen. The ingestion pipeline therefore preserves the official document URL while also indexing extracted text.

## Why confidence gating?

A low-quality retrieval result should not become a confident government answer. The system can broaden retrieval, ask the fallback model for general information where appropriate, or explicitly say that official evidence was not found.

## Citizen flow

```text
"PRTC er jonno ki ki document lagbe?"
              ↓
      Language / intent analysis
              ↓
       Dense + BM25 retrieval
              ↓
            RRF
              ↓
          Reranking
              ↓
        Official evidence
              ↓
      Grounded LLM answer
              ↓
   📄 Form + 🔗 official source
```

## Deployment flow

```text
Docker Compose
 ├── FastAPI RAG API
 ├── PostgreSQL
 ├── Redis
 ├── Telegram adapter
 ├── WhatsApp adapter
 ├── OpenWA
 └── OpenWA bootstrap
```

## Operational rule

An ingestion failure must stop before replacing or corrupting a healthy knowledge base. Existing Pinecone data is retained unless an operator explicitly requests a full rebuild.
