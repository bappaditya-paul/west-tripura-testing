#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# OpenWA Bootstrap — Idempotent Session & Webhook Setup
# ═══════════════════════════════════════════════════════════════════════════
# This script runs once on 'docker compose up' to ensure:
#   1. OpenWA is healthy
#   2. WhatsApp session exists (creates if missing)
#   3. RAG API is healthy
#   4. Webhook is registered (creates if missing)
# Then exits 0. It is safe to run multiple times (idempotent).
# ═══════════════════════════════════════════════════════════════════════════

set -e

OPENWA_URL="${OPENWA_BASE_URL:-http://openwa:2785}"
API_KEY="${OPENWA_API_KEY}"
SESSION_ID="${OPENWA_SESSION_ID:-bot}"
WEBHOOK_URL="${WEBHOOK_TARGET_URL:-http://rag-whatsapp:9000/webhook}"
HEADERS="X-API-Key: ${API_KEY}"

echo "═══════════════════════════════════════════════"
echo "  OpenWA Bootstrap — Session & Webhook Setup"
echo "═══════════════════════════════════════════════"
echo ""

# ── 1. Wait for OpenWA to be healthy ────────────────────────────────────
echo "[1/4] Waiting for OpenWA at ${OPENWA_URL}..."
MAX_WAIT=120
WAITED=0
until curl -fsS "${OPENWA_URL}/api/health" > /dev/null 2>&1; do
    if [ "${WAITED}" -ge "${MAX_WAIT}" ]; then
        echo "  ❌ OpenWA did not become healthy within ${MAX_WAIT}s. Exiting."
        exit 1
    fi
    echo "  ... OpenWA not ready, retrying in 5s (${WAITED}/${MAX_WAIT}s)"
    sleep 5
    WAITED=$((WAITED + 5))
done
echo "  ✅ OpenWA is healthy."
echo ""

# ── 2. Check if session exists ──────────────────────────────────────────
echo "[2/4] Checking for session '${SESSION_ID}'..."
SESSIONS=$(curl -s -H "${HEADERS}" "${OPENWA_URL}/api/sessions" 2>/dev/null || echo "[]")
SESSION_EXISTS=$(echo "${SESSIONS}" | grep -c "\"${SESSION_ID}\"" || true)

if [ "${SESSION_EXISTS}" -gt 0 ]; then
    echo "  ✅ Session '${SESSION_ID}' already exists."
    
    # Check session status
    SESSION_STATUS=$(echo "${SESSIONS}" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
    echo "  📊 Session status: ${SESSION_STATUS}"
    
    if [ "${SESSION_STATUS}" != "ready" ] && [ "${SESSION_STATUS}" != "connected" ]; then
        echo "  ⚠️  Session is not ready. Attempting to start..."
        curl -s -X POST \
            -H "${HEADERS}" \
            "${OPENWA_URL}/api/sessions/${SESSION_ID}/start" > /dev/null 2>&1 || true
        echo "  ↻  Start request sent. Check OpenWA logs for QR code if needed."
    fi
else
    echo "  ⚠️  Session not found. Creating '${SESSION_ID}'..."
    CREATE_RESULT=$(curl -s -X POST \
        -H "${HEADERS}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${SESSION_ID}\"}" \
        "${OPENWA_URL}/api/sessions" 2>/dev/null || echo "{}")
    echo "  Create result: ${CREATE_RESULT}"

    echo "  Starting session..."
    START_RESULT=$(curl -s -X POST \
        -H "${HEADERS}" \
        "${OPENWA_URL}/api/sessions/${SESSION_ID}/start" 2>/dev/null || echo "{}")
    echo "  Start result: ${START_RESULT}"

    echo "  ✅ Session created. Check OpenWA logs for QR code on first run:"
    echo "     docker compose logs openwa --tail=100"
fi
echo ""

# ── 3. Wait for RAG API to be healthy ──────────────────────────────────
echo "[3/4] Waiting for RAG API at http://api:8000..."
WAITED=0
until curl -fsS "http://api:8000/health" > /dev/null 2>&1; do
    if [ "${WAITED}" -ge "${MAX_WAIT}" ]; then
        echo "  ❌ RAG API did not become healthy within ${MAX_WAIT}s. Exiting."
        exit 1
    fi
    echo "  ... RAG API not ready, retrying in 5s (${WAITED}/${MAX_WAIT}s)"
    sleep 5
    WAITED=$((WAITED + 5))
done
echo "  ✅ RAG API is healthy."
echo ""

# ── 4. Check/create webhook (idempotent) ───────────────────────────────
echo "[4/4] Checking webhooks for session '${SESSION_ID}'..."
WEBHOOKS=$(curl -s -H "${HEADERS}" \
    "${OPENWA_URL}/api/sessions/${SESSION_ID}/webhooks" 2>/dev/null || echo "[]")
WEBHOOK_EXISTS=$(echo "${WEBHOOKS}" | grep -c "${WEBHOOK_URL}" || true)

if [ "${WEBHOOK_EXISTS}" -gt 0 ]; then
    echo "  ✅ Webhook already registered: ${WEBHOOK_URL}"
else
    echo "  ⚠️  Webhook not found. Registering..."
    RESULT=$(curl -s -X POST \
        -H "${HEADERS}" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"${WEBHOOK_URL}\", \"events\": [\"message.received\"]}" \
        "${OPENWA_URL}/api/sessions/${SESSION_ID}/webhooks" 2>/dev/null || echo "{}")
    echo "  Result: ${RESULT}"
    echo "  ✅ Webhook registration attempted."
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Bootstrap complete!"
echo "  Session : ${SESSION_ID}"
echo "  Webhook : ${WEBHOOK_URL}"
echo "  OpenWA  : ${OPENWA_URL}"
echo "═══════════════════════════════════════════════"
