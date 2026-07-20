# RAG Platform — Running Guide

Complete guide to run the RAG Platform on your machine.

---

## Prerequisites

Before you start, make sure you have:

### For Docker (Recommended)
- [Docker](https://docs.docker.com/get-docker/) installed (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) installed (v2.0+)
- API keys (see Step 2 below)

### For Local (No Docker)
- Python 3.11 or higher
- PostgreSQL 14+ running
- Redis 7+ running
- API keys (see Step 2 below)

---

## Step 1: Clone the Repository

```bash
git clone <your-repo-url>
cd west-tripura-testing
```

---

## Step 2: Get API Keys

You need at minimum:

| Key | Where to get it | Required |
|-----|----------------|----------|
| `NV_API_KEY` | [NVIDIA NIM](https://build.nvidia.com/) | Yes (embeddings) |
| `NV_CHAT_API_KEY` | [NVIDIA NIM](https://build.nvidia.com/) | Yes (chat) |
| `PINECONE_API_KEY` | [Pinecone Console](https://app.pinecone.io/) | Yes (vector DB) |
| `PINECONE_INDEX_NAME` | Create in Pinecone Console | Yes |
| `PINECONE_HOST` | From Pinecone Console after creating index | Yes |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram | Optional |

---

## Step 3: Configure Environment

```bash
cp .env.example .env
```

Open `.env` in any editor and fill in your keys:

```env
# ── NVIDIA NIM APIs ──────────────────────────────────────────
NV_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxx
NV_CHAT_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxx

# ── Pinecone ─────────────────────────────────────────────────
PINECONE_API_KEY=pcsk_xxxxxxxxxxxxxxxxxxxxx
PINECONE_INDEX_NAME=west-tripura
PINECONE_HOST=https://xxxxx.svc.aped-4627-b74a.pinecone.io

# ── Telegram (optional) ─────────────────────────────────────
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

Leave everything else as default — it works out of the box.

---

## Option A: Run with Docker (Recommended)

This is the easiest way. One command starts everything.

### Start All Services

```bash
docker compose up -d
```

This starts 4 containers:

| Container | Service | Port |
|-----------|---------|------|
| `rag-postgres` | PostgreSQL 16 | 5432 |
| `rag-redis` | Redis 7 | 6379 |
| `rag-api` | FastAPI REST API | 8000 |
| `rag-telegram` | Telegram Bot | — |

### Check Status

```bash
docker compose ps
```

Expected output:
```
NAME             STATUS          PORTS
rag-postgres     Up (healthy)    0.0.0.0:5432->5432/tcp
rag-redis        Up (healthy)    0.0.0.0:6379->6379/tcp
rag-api          Up (healthy)    0.0.0.0:8000->8000/tcp
rag-telegram     Up                              (connected to API)
```

### View Logs

```bash
# All services
docker compose logs -f

# API only
docker compose logs -f api

# Telegram only
docker compose logs -f telegram

# Specific time range
docker compose logs --since 10m api
```

### Verify It Works

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Open Swagger docs in browser
# Visit: http://localhost:8000/docs

# 3. Test a query
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who is the District Magistrate of West Tripura?"}'

# 4. Test search
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "tourism packages in Tripura", "top_k": 3}'
```

### Restart Services

```bash
# Restart everything
docker compose restart

# Restart only API
docker compose restart api

# Restart only Telegram
docker compose restart telegram
```

### Stop Services

```bash
# Stop all (keeps data)
docker compose down

# Stop all and delete volumes (DELETES ALL DATA)
docker compose down -v
```

### Rebuild After Code Changes

```bash
# Rebuild and restart
docker compose up -d --build

# Force rebuild (no cache)
docker compose build --no-cache && docker compose up -d
```

---

## Option B: Run Locally (No Docker)

Use this if you already have PostgreSQL and Redis running, or prefer not to use Docker.

### 1. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start PostgreSQL and Redis

If you don't have them running, use Docker for just these two:

```bash
docker compose up -d postgres redis
```

Or use your local installations:

```bash
# PostgreSQL (if installed locally)
sudo systemctl start postgresql

# Redis (if installed locally)
sudo systemctl start redis
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

Update the database URL if your PostgreSQL is local:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ragplatform
REDIS_URL=redis://localhost:6379/0
```

### 5. Initialize Database

```bash
python -c "import asyncio; from backend.db.engine import init_db; asyncio.run(init_db())"
```

### 6. Start the API Server

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Start the Telegram Bot (separate terminal)

```bash
# Open a new terminal
source .venv/bin/activate
API_BASE_URL=http://localhost:8000 python telegram_bot.py
```

---

## Option C: Use the Makefile

```bash
# Show all commands
make help

# Start production (Docker)
make up

# Start development with hot-reload
make dev

# Run locally without Docker
make run

# Stop everything
make down

# View logs
make logs

# Run tests
make test

# Test API
make test-api

# Reset database (DELETES ALL DATA)
make db-reset
```

---

## Option D: Use the CLI Script

```bash
chmod +x run.sh

./run.sh api           # Start API server locally
./run.sh api-docker    # Start with Docker (production)
./run.sh dev           # Start with Docker (development)
./run.sh stop          # Stop Docker services
./run.sh test          # Test the API
./run.sh migrate       # Initialize database
./run.sh logs          # View Docker logs
./run.sh help          # Show commands
```

---

## API Endpoints Reference

Once running, open **http://localhost:8000/docs** for interactive Swagger docs.

### Health Check
```bash
curl http://localhost:8000/health
```

### Register User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "username": "testuser", "password": "password123"}'
```

### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'
```

### Create Project
```bash
# Use the token from login response
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"name": "My Knowledge Base", "description": "Internal docs"}'
```

### Upload Document
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<project-uuid>" \
  -H "Authorization: Bearer <your-token>" \
  -F "file=@./my-document.pdf"
```

### Query (RAG)
```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"query": "What are the tourist places in West Tripura?"}'
```

### Chat (Streaming)
```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"messages": [{"role": "user", "content": "Tell me about West Tripura"}]}'
```

---

## Telegram Bot

### Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token
4. Add it to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your-token-here
   ```

### Test

1. Start a chat with your bot on Telegram
2. Send `/start`
3. Ask any question
4. The bot queries the RAG API and responds with answers + sources

---

## Troubleshooting

### API won't start
```bash
# Check logs
docker compose logs api

# Common issues:
# - Missing API keys in .env
# - Port 8000 already in use
# - Database not ready
```

### Telegram bot not responding
```bash
# Check logs
docker compose logs telegram

# Common issues:
# - Invalid TELEGRAM_BOT_TOKEN
# - API service not healthy yet
```

### Database connection error
```bash
# Check if Postgres is running
docker compose ps postgres

# Reset database
docker compose down -v
docker compose up -d

# Reinitialize
docker compose exec api python -c "import asyncio; from backend.db.engine import init_db; asyncio.run(init_db())"
```

### Port already in use
```bash
# Find what's using port 8000
lsof -i :8000

# Kill it or change the port in docker-compose.yml
```

### Rebuild from scratch
```bash
docker compose down -v
docker compose up -d --build
```

---

## Quick Reference

| What | Command |
|------|---------|
| Start everything | `docker compose up -d` |
| Stop everything | `docker compose down` |
| View logs | `docker compose logs -f` |
| Restart API | `docker compose restart api` |
| Rebuild | `docker compose up -d --build` |
| API docs | http://localhost:8000/docs |
| Health check | `curl http://localhost:8000/health` |
| Run locally | `uvicorn backend.main:app --reload` |
| Run tests | `make test` |
