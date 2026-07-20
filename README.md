# 🏛️ West Tripura District RAG & Telegram Assistant

A self-hostable, production-hardened Retrieval-Augmented Generation (RAG) platform and Telegram bot assistant. Grounded in the official West Tripura knowledge base, this assistant answers public queries in English and Bengali (বাংলা) with verified citations.

---

## 📖 For Non-Technical Minds: How It Works

Retrieval-Augmented Generation (RAG) is a technique that keeps AI chatbots accurate and grounded. Instead of letting the AI guess or invent answers (hallucination), the system acts like a smart librarian:

```
[ User Query ] ──▶ [ 1. Search Query Optimizer ] ──▶ [ 2. Knowledge Base Search ]
                                                             │ (Pinecone & BM25)
                                                             ▼
[ Verified Answer ] ◀── [ 4. Grounded LLM Response ] ◀── [ 3. Top-k Diverse Pages ]
```

1. **Ask a Question**: You ask a question (e.g. *"Who is the DM of West Tripura?"*).
2. **Optimize Query**: The system expands abbreviations (like DM ➜ District Magistrate) and resolves conversation context if you're in a multi-turn chat.
3. **Retrieve Documents**: The assistant searches the local indexed database (official notifications, contacts, and guidelines) for the top matches.
4. **Deduplicate & Clean**: The system selects the most diverse pages, removing duplicates to ensure the AI gets a complete picture.
5. **Grounded Generation**: The AI reads the retrieved web pages and documents, drafting a clear answer *strictly* using the facts on those pages, complete with clickable source links.

---

## 🛠️ Key Features

- **🗣️ Bilingual Support**: Responds fluently in English or Bengali (বাংলা) based on the user's query language.
- **📱 Telegram Integration**: Built-in polling bot container (`rag-telegram`) with typing indicators, `/reset` commands, and formatted link previews.
- **⚡ Hybrid Search**: Combines semantic embeddings (NVIDIA NIM) and keyword search (BM25) with weighted fusion (`0.7` vector / `0.3` keyword) for optimal relevance.
- **🧹 URL Deduplication**: Candidate oversampling (`candidate_k=20`) and page-level deduplication prevent duplicate tables or announcements from crowding out answers.
- **🔐 Secure API Key Auth**: Hardened endpoints with `STATIC_API_KEY` validation to block unauthorized programmatic access.

---

## 📁 Project Directory Tour

Here is a map of the repository to help you find your way around:

```
west-tripura-rag-chatbot/
├── backend/                       # 🧠 Core Application Code
│   ├── main.py                    # Entry point to start the FastAPI web server
│   ├── core/
│   │   ├── config.py              # Configuration manager loaded from .env
│   │   └── app_factory.py         # App initialization (middleware, databases)
│   ├── api/v1/                    # 🌐 REST Endpoints (URLs)
│   │   ├── auth.py                # User login, registration, and API keys
│   │   ├── search.py              # Search and query endpoints
│   │   ├── chat.py                # Conversational search endpoints
│   │   └── health.py              # Health check status indicators
│   ├── middleware/                # 🛡️ Request Interceptors
│   │   ├── auth.py                # Validates JWT tokens and X-API-Keys
│   │   └── rate_limit.py          # Prevents spam (rate-limiting by IP)
│   ├── models/
│   │   └── orm.py                 # SQLAlchemy Database models (Users, Logs)
│   ├── services/                  # ⚙️ Business Logic
│   │   ├── providers/             # Pluggable backends (Pinecone, NVIDIA, OpenAI)
│   │   │   ├── vector_store.py    # Vector database connections
│   │   │   ├── embedding.py       # Text embedding generation
│   │   │   └── llm.py             # Language model chat generation
│   │   └── rag_service.py         # Orchestrates query optimization & retrieval
│   └── db/
│       └── engine.py              # PostgreSQL database connection pool
│
├── processed_chunks/              # 📄 Offline Document Store
│   └── chunk_*.json               # Chunked raw text segments of district documents
│
├── telegram_bot.py                # 🤖 Telegram Bot polling application script
├── docker-compose.yml             # 🐳 Multi-container production deployment config
├── Dockerfile                     # Docker image recipe for both API and Telegram bot
├── requirements.txt               # 📦 Python dependency list
├── .env                           # 🔒 Local environment settings (secret keys)
└── README.md                      # 📖 This documentation file
```

---

## 🚀 Quick Start (Docker Composition)

### Prerequisites
Make sure you have [Docker](https://docs.google.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

### 1. Configure the Environment
Clone the repository, create your `.env` file from the template, and fill in your actual credentials:
```bash
cp .env.example .env
```

Ensure the following variables are configured:
```ini
TELEGRAM_BOT_TOKEN=your_bot_token_here
NV_API_KEY=your_nvidia_nim_key_here
PINECONE_API_KEY=your_pinecone_key_here
PINECONE_INDEX_NAME=rag-platform
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/ragplatform
REDIS_URL=redis://redis:6379/0
```

### 2. Deploy the Stack
Launch all services in the background:
```bash
docker compose up -d
```

### 3. Verify Container Status
Check that all 4 containers are running and healthy:
```bash
docker ps
```
Expected output:
```
NAMES             STATUS                        PORTS
rag-telegram      Up About a minute             8000/tcp
rag-api           Up About a minute (healthy)   0.0.0.0:8001->8000/tcp
rag-postgres      Up About a minute (healthy)   0.0.0.0:5434->5432/tcp
rag-redis         Up About a minute (healthy)   0.0.0.0:6381->6379/tcp
```

---

## 📱 Using the Bot & API

### Telegram Commands
Open your Telegram Bot interface and use the following:
* `/start` — Greet the bot and read the bilingual welcome greeting.
* `/help` — View information about what queries you can ask.
* `/reset` — Clear your conversation memory to start a new topic.
* `/health` — Check the live status of the district backend services.

### Swagger REST API
FastAPI automatically compiles interactive documentation. Open your browser and navigate to:
```
http://localhost:8001/docs
```
1. Click **🔒 Authorize** at the top right.
2. In the `X-API-Key (apiKey)` field, paste your configured key (default: `telegram-bot-internal`).
3. Scroll to `POST /api/v1/query` and click **Try it out** to query the RAG pipeline directly!

---

## 🔒 Security Policy
The REST API is hardened with an authorization header constraint:
- Every external client request to `/api/v1/query` or `/api/v1/search` must supply the header `X-API-Key` matching `STATIC_API_KEY` in settings.
- Anonymous requests are rejected with a `401 Unauthorized` response to prevent API abuse.
