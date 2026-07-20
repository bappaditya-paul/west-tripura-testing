# Backend — RAG Platform

## What is this backend?

This is a **RAG (Retrieval-Augmented Generation) Platform** backend. It lets you:

1. **Upload documents** (PDF, DOCX, Excel, Markdown, text, HTML, CSV)
2. **Crawl websites** to extract content
3. **Convert documents into embeddings** (vectors) and store them in a vector database
4. **Search** through those documents semantically (by meaning, not just keywords)
5. **Ask questions** in a chat — the system finds relevant documents and has an AI generate an answer
6. **Rate the answers** to give feedback

It is built with **FastAPI** (Python web framework) and uses **PostgreSQL** for storing data, **Pinecone/Qdrant** for vector search, and various AI providers (NVIDIA, OpenAI, Ollama) for embeddings and chat.

---

## Folder Structure (Simple Explanation)

```
backend/
├── __init__.py           — Makes "backend" a Python package
├── main.py               — Entry point that starts the server
│
├── core/                 — Core setup: config and app factory
│   ├── config.py         — All settings (API keys, DB URLs, etc.)
│   └── app_factory.py    — Builds the FastAPI app with all middlewares and routes
│
├── db/                   — Database connection
│   └── engine.py         — Connects to PostgreSQL, creates tables, gives sessions
│
├── models/               — Database table definitions (SQLAlchemy ORM)
│   └── orm.py            — Defines: User, Project, Document, Chunk, CrawlJob, etc.
│
├── schemas/              — Request/Response shape definitions (Pydantic models)
│   ├── auth.py           — Login/Register data shapes
│   ├── project.py        — Project CRUD data shapes
│   ├── document.py       — Document upload/list data shapes
│   ├── crawl.py          — Web crawl data shapes
│   ├── embeddings.py     — Embedding data shapes
│   ├── search.py         — Search & query data shapes
│   ├── chat.py           — Chat & streaming data shapes
│   ├── feedback.py       — Feedback & evaluation data shapes
│   ├── admin.py          — Admin stats data shapes
│   └── health.py         — Health check data shapes
│
├── api/                  — API endpoints (routes)
│   └── v1/               — Version 1 of the API
│       ├── health.py     — /health, /ready, /live, /version
│       ├── auth.py       — /auth/register, /auth/login, /auth/me, /auth/api-key
│       ├── projects.py   — /projects (CRUD)
│       ├── documents.py  — /documents (upload, list, delete, reindex)
│       ├── crawl.py      — /crawl (start, stop, status, list)
│       ├── embeddings.py — /embeddings (create, rebuild, status)
│       ├── search.py     — /search (pure retrieval), /query (full RAG)
│       ├── chat.py       — /chat (sync + streaming)
│       ├── feedback.py   — /evaluate, /feedback
│       └── admin.py      — /admin/stats, /admin/version, /admin/logs
│
├── services/             — Business logic
│   ├── rag_service.py    — Main RAG logic: retrieve → fallback → generate answer
│   ├── interfaces/       — Abstract base classes (contracts)
│   │   └── base.py       — Defines what every provider MUST implement
│   └── providers/        — Actual implementations that plug in
│       ├── embedding.py  — Embedding providers (NVIDIA, OpenAI, BGE)
│       ├── llm.py        — LLM providers (NVIDIA, OpenAI, Ollama)
│       └── vector_store.py — Vector DB providers (Pinecone, Qdrant)
│
├── middleware/            — Request processing pipeline
│   ├── auth.py           — JWT + API Key authentication (protects endpoints)
│   ├── logging.py        — Logs every request with ID and timing
│   └── rate_limit.py     — Limits requests per IP (60/min)
│
└── utils/                — Utility helpers (currently empty)
    └── __init__.py
```

---

## What each folder does (Beginner-Friendly)

### 1. `backend/core/` — The Brain (Core Setup)

This folder sets up the entire application.

- **`config.py`**: All settings live here. Database URL, API keys for NVIDIA/OpenAI/Pinecone, which provider to use for embeddings/LLM/vector store, chunk sizes, rate limits, etc. It reads from the `.env` file. If you want to change the AI model or database, you change it here (or in `.env`).

- **`app_factory.py`**: Builds the FastAPI app. Think of it like a factory assembly line:
  1. Adds CORS (lets websites access the API)
  2. Adds logging middleware
  3. Adds rate-limiting middleware
  4. Registers all API routes (health, auth, projects, documents, crawl, etc.)
  5. Sets up a global error handler
  6. On startup, creates database tables
  7. On shutdown, closes database connections

### 2. `backend/db/` — The Database (Storage)

- **`engine.py`**: Manages the connection to PostgreSQL database.
  - Creates an async connection pool
  - Provides a `get_db()` function that API endpoints use to get a database session
  - On startup, automatically creates all the tables (User, Project, Document, etc.)
  - On shutdown, closes connections cleanly

### 3. `backend/models/` — Table Definitions

- **`orm.py`**: Defines what data we store in PostgreSQL. Each class = one table.
  - **User** — who logs in
  - **APIKey** — programmatic access keys
  - **Project** — a workspace where you upload documents
  - **Document** — a file or URL you uploaded
  - **Chunk** — a piece of a document (documents are split into chunks)
  - **CrawlJob** — a website crawl task
  - **Conversation** — a Q&A interaction
  - **Feedback** — user rating of an answer

### 4. `backend/schemas/` — Data Shapes

Each file defines what data the API accepts and returns. Uses **Pydantic** (a Python library that validates data). For example:
- When you register, the API expects `{email, username, password}`
- When you search, the API returns `{query, hits, total, latency_ms, source}`
- If you send wrong data (e.g., email without `@`), it automatically rejects with a clear error

### 5. `backend/api/v1/` — API Endpoints (Entry Points)

This is where the HTTP endpoints live. Each file handles a group of related features.

**What each file does:**

| File | What you can do with it |
|---|---|
| `health.py` | Check if the server is alive (`/health`, `/ready`, `/live`, `/version`) |
| `auth.py` | Register an account, log in, get your profile, create/manage API keys |
| `projects.py` | Create, list, view, update, delete projects (each project is a workspace) |
| `documents.py` | Upload a file, add a URL, list documents, get details, delete, reindex |
| `crawl.py` | Start a web crawl, stop it, check status, list all crawl jobs |
| `embeddings.py` | Create embeddings from text, rebuild all embeddings, check status |
| `search.py` | Semantic search (`/search`) and full Q&A with AI (`/query`) |
| `chat.py` | Chat with AI (`/chat`) and stream responses in real-time (`/chat/stream`) |
| `feedback.py` | Evaluate answer quality (`/evaluate`) and submit user ratings (`/feedback`) |
| `admin.py` | Get system stats, version info, and logs (admin dashboard) |

### 6. `backend/services/` — Business Logic

This is where the actual "thinking" happens.

- **`rag_service.py`** (RAG = Retrieval-Augmented Generation):
  1. Takes your question
  2. Converts it to a vector (embedding)
  3. Searches the vector database for similar documents
  4. If nothing found, falls back to searching DuckDuckGo for government websites
  5. Builds a context from the found information
  6. Sends the context + question to an AI (LLM) to generate an answer
  7. Returns the answer with references (source URLs/titles)

- **`interfaces/base.py`**: Defines the rules for providers:
  - Every Vector Store must implement: upsert, query, delete, count, health
  - Every Embedding provider must implement: embed, dimensions, model_name, health
  - Every LLM must implement: generate, generate_stream, model_name, health

- **`providers/`**: Actual implementations that follow those rules:
  - **`embedding.py`**: NVIDIA (nv-embed-v1), OpenAI (text-embedding-3-large), BGE (local)
  - **`llm.py`**: NVIDIA (Llama 3.1 70B), OpenAI (GPT-4o), Ollama (local models)
  - **`vector_store.py`**: Pinecone, Qdrant

  The system picks which one to use based on the settings in your `.env` file. You can swap providers without changing any code!

### 7. `backend/middleware/` — Security & Logging

These are processed for EVERY request before it reaches the API endpoint.

- **`auth.py`**: Checks if the user is logged in. Supports:
  - JWT tokens (Bearer token in the Authorization header)
  - API keys (X-API-Key header)
  - If not authenticated, returns 401 error

- **`logging.py`**: For every request:
  - Generates a unique request ID (shown in response headers as `X-Request-ID`)
  - Logs the method, path, status code, and response time
  - Adds `X-Response-Time` header to the response

- **`rate_limit.py`**: Prevents abuse by limiting requests:
  - Default: 60 requests per minute per IP address
  - Returns 429 Too Many Requests if exceeded
  - Health check endpoints are excluded from rate limiting

### 8. `backend/utils/` — Helpers

Currently empty. Meant for utility functions that don't fit elsewhere.

---

## How requests flow through the system

```
1. HTTP Request comes in
       │
2. Middleware processes it (in order):
       │  ┌─ CORS (allows cross-origin requests)
       │  ├─ Request Logging (adds request ID)
       │  └─ Rate Limiting (checks if IP is over limit)
       │
3. Auth middleware checks if user is logged in
       │  (JWT token or API Key)
       │
4. Request reaches the API endpoint
       │  e.g., POST /api/v1/chat
       │
5. Endpoint calls RAGService
       │  RAGService does:
       │   1. Embeds the question → vector
       │   2. Searches vector DB for similar content
       │   3. Falls back to DuckDuckGo if nothing found
       │   4. Sends context + question to LLM
       │   5. Returns answer with references
       │
6. Response goes back to the client
```

---

## How the providers work (Pluggable Architecture)

The system uses a **plug-and-play** design. You can switch between different AI providers by just changing a setting in `.env`.

```
┌─────────────────────────────────────────────────────┐
│                   Your Question                       │
└─────────────────────┬───────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                  │
    ▼                 ▼                  ▼
Embedding        Vector DB           LLM (AI)
Provider         Provider            Provider
─────────────────────────────────────────────
NVIDIA           Pinecone            NVIDIA
OpenAI           Qdrant              OpenAI
BGE (local)                          Ollama
```

Each provider family follows the same rules (defined in `interfaces/base.py`), so swapping is seamless.

---

## Quick Reference: Environment Variables

Set these in your `.env` file (see `.env.example`):

| Variable | What it controls |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `VECTOR_DB_PROVIDER` | `pinecone` or `qdrant` |
| `EMBEDDING_PROVIDER` | `nvidia` or `openai` or `bge` |
| `LLM_PROVIDER` | `nvidia` or `openai` or `ollama` |
| `NV_API_KEY` | NVIDIA API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `PINECONE_API_KEY` | Pinecone API key |
| `JWT_SECRET` | Secret for signing auth tokens |

---

## How to run the backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn backend.main:app --reload --port 8000

# Open API docs in browser
# http://localhost:8000/docs   (Swagger UI)
# http://localhost:8000/redoc  (ReDoc)
```

---

## API Endpoints Summary

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Health check |
| GET | `/ready` | No | Readiness (DB, Redis, Vector DB) |
| GET | `/live` | No | Liveness check |
| GET | `/version` | No | Version info |
| POST | `/api/v1/auth/register` | No | Register user |
| POST | `/api/v1/auth/login` | No | Login, get JWT |
| GET | `/api/v1/auth/me` | Yes | Current user |
| POST | `/api/v1/auth/api-key` | Yes | Create API key |
| GET | `/api/v1/auth/api-keys` | Yes | List API keys |
| POST | `/api/v1/projects` | Yes | Create project |
| GET | `/api/v1/projects` | Yes | List projects |
| GET | `/api/v1/projects/{id}` | Yes | Get project |
| PATCH | `/api/v1/projects/{id}` | Yes | Update project |
| DELETE | `/api/v1/projects/{id}` | Yes | Delete project |
| POST | `/api/v1/documents/upload` | Yes | Upload file |
| POST | `/api/v1/documents/url` | Yes | Add URL |
| GET | `/api/v1/documents` | Yes | List documents |
| GET | `/api/v1/documents/{id}` | Yes | Get document |
| DELETE | `/api/v1/documents/{id}` | Yes | Delete document |
| POST | `/api/v1/documents/reindex` | Yes | Reindex documents |
| POST | `/api/v1/crawl/start` | Yes | Start crawl |
| POST | `/api/v1/crawl/stop/{id}` | Yes | Stop crawl |
| GET | `/api/v1/crawl/status/{id}` | Yes | Crawl status |
| GET | `/api/v1/crawl/jobs` | Yes | List crawl jobs |
| POST | `/api/v1/embeddings/create` | Yes | Create embeddings |
| POST | `/api/v1/embeddings/rebuild` | Yes | Rebuild embeddings |
| GET | `/api/v1/embeddings/status` | Yes | Embedding status |
| POST | `/api/v1/search` | Yes | Semantic search |
| POST | `/api/v1/query` | Yes | Full RAG query |
| POST | `/api/v1/chat` | Yes | Chat with AI |
| POST | `/api/v1/chat/stream` | Yes | Streaming chat |
| POST | `/api/v1/evaluate` | Yes | Evaluate answer |
| POST | `/api/v1/feedback` | Yes | Submit feedback |
| GET | `/api/v1/admin/stats` | Yes | Admin stats |
| GET | `/api/v1/admin/version` | Yes | Version info |
| GET | `/api/v1/admin/logs` | Yes | System logs |
