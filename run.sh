#!/usr/bin/env bash
set -euo pipefail

# ── RAG Platform CLI Dispatcher ───────────────────────────────────────────
# Usage: ./run.sh <command>

VENV="$(dirname "$0")/.venv"
if [ -d "$VENV" ]; then
    source "$VENV/bin/activate"
fi
cd "$(dirname "$0")"

usage() {
    cat <<EOF
Usage: ./run.sh <command>

Commands:
    api         Start FastAPI server (http://127.0.0.1:8000)
    api-docker  Start with Docker Compose (production)
    dev         Start with Docker Compose (development, hot-reload)
    stop        Stop all Docker services
    embed       Re-embed all processed chunks into Pinecone
    test        Smoke test the API
    migrate     Run database migrations
    logs        Tail Docker logs
    help        Show this help
EOF
}

cmd_api() {
    echo "Starting FastAPI server on http://127.0.0.1:8000 ..."
    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
}

cmd_api_docker() {
    echo "Starting production stack with Docker Compose ..."
    docker compose up -d --build
}

cmd_dev() {
    echo "Starting development stack with hot-reload ..."
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
}

cmd_stop() {
    docker compose down
}

cmd_embed() {
    echo "Re-embedding all processed chunks into Pinecone ..."
    python src/ingestion/embed_and_load.py --clear-index
}

cmd_test() {
    echo "Sending test query to API ..."
    curl -s -X POST http://127.0.0.1:8000/api/v1/query \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer test-token" \
        -d '{"query":"Who is the DM of West Tripura?"}' | python -m json.tool
}

cmd_migrate() {
    echo "Running database migrations ..."
    python -c "import asyncio; from backend.db.engine import init_db; asyncio.run(init_db())"
    echo "Done."
}

cmd_logs() {
    docker compose logs -f
}

case "${1:-help}" in
    api)        cmd_api        ;;
    api-docker) cmd_api_docker ;;
    dev)        cmd_dev        ;;
    stop)       cmd_stop       ;;
    embed)      cmd_embed      ;;
    test)       cmd_test       ;;
    migrate)    cmd_migrate    ;;
    logs)       cmd_logs       ;;
    *)          usage          ;;
esac
