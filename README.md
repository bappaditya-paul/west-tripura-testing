# 🏛️ West Tripura Citizen RAG & Document Assistant

A self-hostable, production-oriented citizen information assistant for the **West Tripura District**. It combines official website crawling, document discovery/download, semantic + keyword retrieval, reranking, grounded LLM answers, direct document links, and Telegram/WhatsApp delivery.

The project is designed so that an NIC/operator can run the ingestion pipeline locally, refresh the knowledge base from the official district portal, and then serve citizen questions without manually collecting every government PDF or form.

> **Official source:** https://westtripura.nic.in/

---

## 🎯 What This System Does

The system is designed around one simple citizen experience:

```text
Citizen asks a question
        ↓
Understand the question
        ↓
Search official West Tripura pages + documents
        ↓
Rank the most relevant evidence
        ↓
Generate a grounded answer
        ↓
Attach the official source/document when available
```

Examples:

- `DM office er phone number ta ki?`
- `How can I apply for a PRTC?`
- `What documents are required for this certificate?`
- `আমি কীভাবে সার্টিফিকেটের জন্য আবেদন করব?`
- `Show me the official application form`

For official facts, the chatbot is instructed **not to invent names, phone numbers, addresses, dates, fees, eligibility rules, or procedures** when the knowledge base does not support them.

---

# 🚀 Main Capabilities

## 1. Citizen-friendly query routing

Common conversations such as greetings and thanks use a fast path instead of running the entire RAG pipeline.

```text
Hello → instant conversational response

Government question → retrieval pipeline

General knowledge → general LLM fallback
```

The query analyzer also handles common citizen language, Bengali, and Benglish/mixed-language wording.

## 2. Hybrid retrieval

Official information is searched using multiple signals:

```text
Dense semantic search
        +
BM25 keyword search
        ↓
RRF fusion
        ↓
Candidate pool
        ↓
Reranking
        ↓
Best evidence
```

This helps with both natural questions and exact terms such as form names, department names, phone numbers, and certificate names.

## 3. Confidence-based grounding

The assistant does not blindly trust the first search result.

```text
High confidence → official RAG answer
Medium confidence → broader retrieval/retry
Low confidence → safe general-LLM fallback
```

For West Tripura-specific facts that cannot be verified, the system prefers a verification message over fabrication.

## 4. Automatic official document discovery

The ingestion pipeline discovers document links exposed by crawled official pages, including common formats such as:

- PDF
- DOC / DOCX
- XLS / XLSX
- CSV
- TXT

When an official document is found, the pipeline can download it, extract its text, make it searchable, embed it, and retain the original official URL.

## 5. Direct document delivery

When a relevant form/notification/document is available, the chatbot can return the official document link directly instead of telling a citizen to manually browse the website.

Example response shape:

```text
📄 Required document
PRTC application form (PDF)
🔗 https://official-document-url...
```

## 6. One-command knowledge-base refresh

The repository includes an ingestion orchestrator:

```bash
python src/ingestion/auto_ingest.py
```

It runs the main pipeline:

```text
Crawl4AI
  ↓
official document discovery/download
  ↓
document extraction
  ↓
preprocessing
  ↓
semantic chunking
  ↓
embeddings
  ↓
Pinecone
```

For a resumable crawl:

```bash
python src/ingestion/auto_ingest.py --resume
```

For a deliberate full vector-index rebuild:

```bash
python src/ingestion/auto_ingest.py --clear-index
```

> `--clear-index` removes the existing Pinecone vectors before rebuilding them. Use it only when you intentionally want a full rebuild.

---

# 🗂️ Repository Structure

```text
west-tripura-testing/
│
├── backend/                         # FastAPI application
│   ├── main.py                      # API entry point
│   ├── core/                        # Configuration and app setup
│   ├── api/v1/                      # REST endpoints
│   ├── schemas/                     # Pydantic request/response models
│   ├── services/                    # RAG business logic
│   │   ├── intent_router.py
│   │   ├── query_analysis.py
│   │   ├── retrieval_service.py
│   │   ├── reranker_service.py
│   │   ├── confidence_service.py
│   │   ├── response_formatter.py
│   │   ├── document_resolver.py
│   │   ├── rag_service.py
│   │   └── providers/
│   │       ├── embedding.py
│   │       ├── llm.py
│   │       ├── vector_store.py
│   │       └── bm25_retriever.py
│   └── middleware/                  # Auth, logging, rate limiting
│
├── src/ingestion/                   # Knowledge-base ingestion
│   ├── crawler.py                   # Crawl4AI website crawler
│   ├── auto_ingest.py               # One-command full refresh
│   ├── materialize_documents.py     # Discover/download document assets
│   ├── embed_and_load.py            # Embeddings + Pinecone loading
│   ├── build_chunks.py              # Chunking CLI
│   ├── core/
│   │   ├── preprocess_documents.py
│   │   ├── production_chunker.py
│   │   ├── document_builder.py
│   │   └── config.py
│   └── ...
│
├── output/                          # Runtime crawl/document data (ignored by Git)
├── processed_documents/             # Runtime processed documents (ignored)
├── processed_chunks/                # Runtime chunks (ignored)
│
├── telegram_bot.py                  # Telegram interface
├── whatsapp_bot.py                  # OpenWA/WhatsApp interface
├── docker-compose.yml               # API + Telegram + WhatsApp + data services
├── Dockerfile                       # Application container
├── requirements.txt                  # Lightweight API/runtime dependencies
├── requirements-ingestion.txt       # Crawl/document ingestion dependencies
├── .env.example                     # Safe environment variable template
└── README.md
```

---

# 🧠 RAG Architecture

## Online query path

```text
Citizen
  ↓
Intent + language analysis
  ↓
Fast path for simple conversation
  ↓
Query analysis / entity detection
  ↓
Dense search + BM25
  ↓
RRF fusion
  ↓
Reranking
  ↓
Confidence gate
  ├── official grounded answer
  ├── broader retrieval retry
  └── safe general-LLM fallback
  ↓
Response formatting
  ↓
Source + document links
  ↓
Telegram / WhatsApp / API
```

## Offline ingestion path

```text
westtripura.nic.in
        ↓
      Crawl4AI
        ↓
  Pages + document links
        ↓
Document download/extraction
        ↓
Preprocessing + metadata
        ↓
Production semantic chunking
        ↓
Embeddings
        ↓
Pinecone
        +
BM25 local index
        ↓
Ready for citizen queries
```

---

# 🧾 Document Ingestion Details

The crawler starts from:

```text
https://westtripura.nic.in/
```

The crawler is configured for:

- BFS/deep crawling
- internal-domain crawling
- crash/resume checkpoints
- retries
- rate/politeness delay
- clean Markdown extraction
- page manifests

The current crawler implementation writes page content into `output/pages/` and keeps a crawl manifest/checkpoint for recovery.

Document assets discovered from official pages are materialized into runtime storage under:

```text
output/documents/
```

The extracted document content is then turned into searchable material and ultimately embedded into the configured vector index.

---

# 🧩 Chunking Strategy

Government pages contain paragraphs, headings, lists, procedures, and tables. The production chunker therefore prefers document structure over blind character splitting.

Typical settings:

```text
Target tokens   : 550
Maximum tokens  : 700
Minimum tokens  : 100
Overlap tokens   : 60
```

Chunks preserve heading hierarchy and document metadata so that a retrieved answer can keep useful context such as:

```text
Department
  → Service
      → Procedure
          → Required documents
```

---

# 🔎 Retrieval & Ranking

The current retrieval layer combines:

### Dense retrieval
Semantic similarity from the configured embedding provider.

### BM25
Keyword-oriented retrieval for exact names, acronyms, forms, phone numbers, and other lexical matches.

### RRF
Reciprocal Rank Fusion combines the dense and sparse result lists.

### Reranking
The candidate pool can be reranked with a neural CrossEncoder. If the neural reranker is unavailable, the application has a lightweight fallback.

### Context expansion
Retrieved chunks can be expanded through related chunks in the same document/section.

---

# 🛡️ Grounding and Safety

Official government answers follow these principles:

1. Use verified retrieved context.
2. Never invent official facts.
3. Prefer explicit uncertainty over a fabricated answer.
4. Include source information when available.
5. Keep general LLM answers separate from official grounded answers.

The response includes internal information such as mode/grounding/confidence for debugging and evaluation.

---

# 📄 Document Delivery

A citizen may receive both:

```text
Answer
+
Official source page
+
Direct official document link (when discovered)
```

This is especially useful for:

- forms
- application documents
- notifications
- recruitment notices
- tenders
- reports
- certificates/service-related forms

The system **does not require the document binary to be committed to Git**. Runtime downloads stay under ignored output storage.

---

# 🐳 Docker Services

The main Compose stack contains services for:

```text
PostgreSQL
Redis
FastAPI API
Telegram bot
OpenWA WhatsApp gateway
WhatsApp bot
OpenWA bootstrap
Docker socket proxy
```

Start the stack:

```bash
docker compose up -d
```

Check services:

```bash
docker compose ps
```

View API logs:

```bash
docker compose logs -f api
```

View Telegram logs:

```bash
docker compose logs -f telegram
```

View WhatsApp logs:

```bash
docker compose logs -f whatsapp
```

---

# 🧪 Local Development / API Testing

The API exposes Swagger documentation.

With the current Compose mapping:

```text
http://localhost:8001/docs
```

For direct RAG testing, use the `/chat` or `/query` endpoint shown by the running Swagger schema.

Example citizen query:

```json
{
  "query": "How can I get a PRTC certificate and what documents are required?",
  "top_k": 5,
  "session_id": "test-001"
}
```

Useful test categories:

```text
1. Greetings
2. English government questions
3. Bengali questions
4. Benglish questions
5. Long procedure questions
6. Contact/phone/address questions
7. Document/form requests
8. Follow-up questions
9. Out-of-domain general knowledge
10. Deliberately unavailable official facts
```

---

# 🔄 Keeping the Knowledge Base Updated

For a fresh official-site refresh:

```bash
pip install -r requirements-ingestion.txt
python src/ingestion/auto_ingest.py
```

If the crawl is interrupted:

```bash
python src/ingestion/auto_ingest.py --resume
```

After ingestion, the expected runtime artifacts are:

```text
output/pages/
output/documents/
processed_documents/
processed_chunks/
```

and updated vectors in Pinecone.

> Keep ingestion credentials in `.env`. Do not commit `.env` or downloaded runtime data.

---

# ⚙️ Environment Configuration

Start from:

```bash
cp .env.example .env
```

Typical configuration includes:

```ini
TELEGRAM_BOT_TOKEN=...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=...
NV_API_KEY=...
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/ragplatform
OPENWA_API_KEY=...
```

The exact settings and provider choices are controlled by the project's `.env` / configuration classes.

---

# 🔧 Troubleshooting

## Docker cannot pull `python:3.12-slim`

Test Docker Hub connectivity:

```bash
docker pull python:3.12-slim
```

If the error mentions `auth.docker.io` DNS resolution, check the host DNS resolver and restart Docker Desktop after DNS is repaired.

## API container starts but RAG fails

Check:

```bash
docker compose logs -f api
```

Then verify:

- Pinecone credentials
- embedding provider credentials
- LLM provider credentials
- Redis connectivity
- expected vector index name/dimension

## Search returns no useful results

Run the retrieval endpoint from Swagger and inspect:

- rewritten/retrieval query
- result titles
- scores
- sections
- source URLs
- timing

Then verify that the latest ingestion has actually been run.

## A document is not returned

Check whether the official page actually exposes a downloadable document link. If the website does not publish the document, the crawler cannot invent or manufacture it.

---

# 🧑‍💻 For NIC / Local Operators

Recommended operational workflow:

```text
1. Pull latest code
2. Configure .env
3. Run the crawler/ingestion pipeline
4. Verify downloaded documents
5. Verify processed chunks
6. Verify Pinecone vector count
7. Start Docker services
8. Test Swagger / Telegram / WhatsApp
9. Inspect logs and retrieval traces
```

Daily/weekly refresh can be run by scheduling:

```bash
python src/ingestion/auto_ingest.py
```

Before a production refresh, inspect the crawl logs and document count so a website-side failure does not silently replace a healthy knowledge base with an incomplete one.

---

# 📚 Additional Documentation

More detailed backend documentation is available in:

```text
backend/README.md
```

This file contains a deeper explanation of:

- FastAPI routes
- provider interfaces
- database models
- middleware
- API endpoints
- authentication
- environment settings
- backend request flow

---

# ⚠️ Current Scope

The knowledge base is primarily grounded in official West Tripura district content and official documents discovered from that content.

Not every citizen service is necessarily published directly on `westtripura.nic.in`. For services hosted by another official Tripura department/municipality/e-District system, the correct next step is to add those **approved official sources** to the ingestion scope rather than making unsupported claims.

Birth-certificate, marriage-registration, municipal, and other services may therefore require additional official Tripura sources if the district portal does not publish the required procedure or document.

---

# 📜 License / Usage

Use this project according to the repository's licensing and the applicable policies for the official government source data being crawled.
