# West Tripura Citizen RAG Platform

> **Retrieve verified official evidence first, then generate a simple answer citizens can use.**

A production-oriented RAG platform for West Tripura government information. It combines official-site ingestion, document extraction, hybrid retrieval, reranking, grounded generation, and citizen-facing delivery through REST, Telegram and WhatsApp.

**Official source:** https://westtripura.nic.in/

---

## 1. Architecture

```text
                    OFFICIAL SOURCES
                           │
              ┌────────────┴────────────┐
              │                         │
       West Tripura portal       Official documents
       HTML / services           PDF / DOCX / XLSX
              │                         │
              └────────────┬────────────┘
                           ▼
                CRAWL + DOCUMENT DISCOVERY
                           ▼
                 CLEAN + METADATA + HASH
                           ▼
                 SEMANTIC / STRUCTURED
                       CHUNKING
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
           Embeddings                BM25
                │                     │
                ▼                     │
             Pinecone                 │
                │                     │
                └──────────┬──────────┘
                           ▼
                  HYBRID RETRIEVAL
                  Dense + BM25 + RRF
                           ▼
                       RERANKING
                           ▼
                   CONFIDENCE GATE
                    /      |       \
                   /       |        \
             grounded   broader    no evidence
               answer   retrieval     ↓
                   \       |       safe fallback
                    \      |          /
                     └─────┴─────────┘
                           ▼
                  RESPONSE FORMATTER
                           ▼
              Answer + Source + Document
                           ▼
              API / Telegram / WhatsApp
```

## 2. Citizen experience

Citizens can ask naturally in **English, Bengali or Benglish**:

```text
How can I apply for PRTC?
PRTC er jonno ki ki document lagbe?
আমি কীভাবে সার্টিফিকেটের জন্য আবেদন করব?
Show me the official application form.
```

A good response should provide, where available:

```text
Answer
+ verified source
+ direct official document/form
```

For official facts, the system must not invent names, phone numbers, addresses, dates, fees, eligibility rules or procedures.

---

## 3. Online RAG flow

```text
Citizen question
      ↓
Intent + language analysis
      ↓
Fast path for greetings / simple conversation
      ↓
Query normalization + entities
      ↓
Dense search + BM25
      ↓
RRF fusion
      ↓
Candidate reranking
      ↓
Confidence / grounding decision
      ↓
Grounded LLM generation
      ↓
Response formatting
      ↓
Sources + direct document links
```

### Retrieval design

- **Dense retrieval:** semantic similarity.
- **BM25:** exact names, acronyms, form titles, phone numbers and lexical matches.
- **RRF:** combines complementary retrieval lists.
- **Reranker:** evaluates query-document relevance on the candidate pool.
- **Context expansion:** preserves useful related document/section context.

The LLM is downstream of retrieval; it is not the source of truth for official facts.

---

## 4. Offline knowledge pipeline

```text
Approved official source
        ↓
Crawl4AI + Playwright
        ↓
Citizen-relevant pages + document links
        ↓
Download / extract documents
        ↓
Normalize + metadata + content hash
        ↓
Hierarchical semantic chunking
        ↓
Embeddings → Pinecone
        +
BM25 retrieval data
        ↓
RAG knowledge base
```

### Documents are first-class knowledge

A PDF/form/notification has two purposes:

1. extracted text can answer a question;
2. its original official URL can be delivered to the citizen.

Runtime documents remain in ignored output storage and do not need to be committed to Git.

### Existing knowledge is preserved

A failed crawl must never silently replace a healthy Pinecone knowledge base with an empty one. A destructive/full index rebuild is an explicit operator action.

---

## 5. Repository structure

```text
west-tripura-testing/
│
├── backend/
│   ├── api/v1/              # REST endpoints
│   ├── core/                # configuration
│   ├── middleware/          # request controls
│   ├── schemas/             # API contracts
│   └── services/            # RAG orchestration
│       ├── rag_service.py
│       ├── retrieval_service.py
│       ├── intent_router.py
│       ├── query_analysis.py
│       ├── reranker_service.py
│       ├── confidence_service.py
│       ├── document_resolver.py
│       ├── response_formatter.py
│       └── providers/
│
├── src/ingestion/
│   ├── crawler.py
│   ├── auto_ingest.py
│   ├── materialize_documents.py
│   ├── build_chunks.py
│   ├── embed_and_load.py
│   └── core/
│
├── telegram_bot.py
├── whatsapp_bot.py
├── scripts/
├── docs/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-ingestion.txt
├── .env.example
└── README.md
```

---

## 6. Runtime services

| Component | Role |
|---|---|
| FastAPI | Online RAG API |
| Pinecone | Dense vector search |
| BM25 | Lexical search |
| Redis | Cache/session infrastructure |
| PostgreSQL | Application persistence |
| Crawl4AI | Website ingestion |
| Playwright | Browser automation |
| Telegram Bot | Telegram adapter |
| OpenWA | WhatsApp gateway |
| WhatsApp Bot | WhatsApp adapter |
| LLM provider | Grounded generation / fallback |

---

## 7. Docker

Start:

```bash
docker compose up -d
```

Check:

```bash
docker compose ps
```

Logs:

```bash
docker compose logs -f api
docker compose logs -f telegram
docker compose logs -f whatsapp
```

API Swagger:

```text
http://localhost:8001/docs
```

**Test Swagger before Telegram/WhatsApp.** This isolates the RAG engine from channel integration problems.

---

## 8. Ingestion

Install ingestion dependencies and the browser:

```bash
pip install -r requirements-ingestion.txt
python -m playwright install chromium
```

Run:

```bash
python src/ingestion/auto_ingest.py
```

Resume:

```bash
python src/ingestion/auto_ingest.py --resume
```

Runtime artifacts:

```text
output/pages/
output/documents/
processed_documents/
processed_chunks/
```

The normal refresh does **not** mean deleting existing Pinecone data. A full replacement is an explicit maintenance operation.

---

## 9. Telegram

Telegram is a thin channel adapter. It receives the citizen message and calls the internal FastAPI `/chat` endpoint.

Required variable:

```ini
TELEGRAM_BOT_TOKEN=...
```

Useful commands:

```text
/start
/help
/health
/reset
```

Logs:

```bash
docker compose logs -f telegram
```

The Telegram bot should be tested only after the API `/health` endpoint is healthy.

---

## 10. Testing strategy

Test in layers:

### Layer 1 — API

Use Swagger for greetings, English/Bengali/Benglish queries, procedures, contacts, document requests, follow-ups and unsupported questions.

Example:

```json
{
  "query": "How can I apply for PRTC and what documents are required?",
  "top_k": 5,
  "session_id": "demo-001"
}
```

### Layer 2 — Telegram

Use `/start`, `/health`, then a real citizen question.

### Layer 3 — WhatsApp

Verify OpenWA session → webhook → RAG API → reply.

### Layer 4 — Retrieval evaluation

Inspect `/search` for retrieval query, source URL, section, scores and timing.

### Quality checklist

```text
✓ relevant evidence
✓ factual grounding
✓ source URL
✓ direct document when available
✓ correct language
✓ no hallucinated official facts
✓ acceptable latency
```

---

## 11. Environment

```bash
cp .env.example .env
```

Typical settings:

```ini
TELEGRAM_BOT_TOKEN=...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=...
NV_API_KEY=...
REDIS_URL=redis://redis:6379/0
OPENWA_API_KEY=...
OPENWA_SESSION_ID=bot
```

Never commit `.env` or secrets.

---

## 12. NIC operator workflow

```text
Pull approved code
      ↓
Configure .env
      ↓
Refresh ingestion
      ↓
Verify page/document counts
      ↓
Verify processed chunks
      ↓
Verify Pinecone vectors
      ↓
Start Docker
      ↓
Check /health + Swagger
      ↓
Check Telegram
      ↓
Check WhatsApp
      ↓
Review logs and retrieval quality
```

A failed crawler must stop the refresh rather than silently producing an empty knowledge base.

---

## 13. Scope

The primary source is the official West Tripura district portal. Some citizen services may live on other official Tripura departments, municipalities or e-District systems. Those sources should be added only when approved and must remain attributable to their official origin.

The chatbot must never manufacture a government form, official phone number, eligibility rule, fee, address or procedure that cannot be verified.

---

## 14. Presentation summary

```text
INGESTION
Collect official pages and documents
        ↓
KNOWLEDGE
Clean → metadata → chunk → embed → index
        ↓
RETRIEVAL
Dense + BM25 → RRF → rerank → confidence
        ↓
GENERATION
Grounded LLM + safe fallback
        ↓
DELIVERY
API + Telegram + WhatsApp + direct documents
```

**Core principle: accurate retrieval, explainable sources, usable documents, fast routing, and multiple citizen delivery channels.**
