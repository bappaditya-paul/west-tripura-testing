"""
whatsapp_bot.py
===============
WhatsApp Channel Integration Service for West Tripura RAG Platform.
Mirrors telegram_bot.py structure:
1. Auto-registers webhook on OpenWA startup.
2. Listens for incoming WhatsApp messages on /webhook (port 9000).
3. Routes citizen queries to RAG backend (POST /chat).
4. Sends generated answers back to user via OpenWA REST API.
"""

import asyncio
import logging
import os
import sys
import httpx
from fastapi import FastAPI, Request
from starlette.background import BackgroundTask
from fastapi.responses import JSONResponse
import uvicorn

# ── Environment & Settings ──────────────────────────────────────────────────
OPENWA_BASE_URL = os.getenv("OPENWA_BASE_URL", "http://openwa:2785").rstrip("/")
OPENWA_API_KEY = os.getenv(
    "OPENWA_API_KEY",
    "owa_k1_3402c841e8eaef19ca0fccce89d07d9520ee8aec6f582e2fd0c56dba3bccbb96"
)
OPENWA_SESSION = os.getenv("OPENWA_SESSION_ID", "bot")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://rag-whatsapp:9000/webhook")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("whatsapp_bot")

app = FastAPI(title="West Tripura RAG - WhatsApp Bot Service")

GREETINGS = {"hi", "hello", "hey", "namaste", "good morning", "good evening", "নমস্কার", "হাই", "হ্যালো"}


# ── OpenWA API Helpers ─────────────────────────────────────────────────────

def get_openwa_headers() -> dict:
    return {
        "X-API-Key": OPENWA_API_KEY,
        "Content-Type": "application/json"
    }


async def resolve_session_id(client: httpx.AsyncClient) -> str:
    """Finds the active session ID (UUID or name) from OpenWA API."""
    try:
        resp = await client.get(f"{OPENWA_BASE_URL}/api/sessions", headers=get_openwa_headers())
        if resp.status_code == 200:
            sessions = resp.json()
            for s in sessions:
                if s.get("name") == OPENWA_SESSION or s.get("id") == OPENWA_SESSION or s.get("status") == "ready":
                    session_id = s.get("id") or s.get("name")
                    logger.info(f"Resolved active OpenWA session: {session_id} ({s.get('phone')})")
                    return session_id
    except Exception as e:
        logger.warning(f"Could not query OpenWA sessions list: {e}")
    return OPENWA_SESSION


async def ensure_webhook_registered():
    """Auto-detects and registers the WhatsApp webhook on OpenWA if missing."""
    logger.info("Checking OpenWA webhook registration status...")
    async with httpx.AsyncClient(timeout=15) as client:
        # Retry loop to wait for OpenWA API to be ready
        for attempt in range(1, 10):
            try:
                session_id = await resolve_session_id(client)
                
                # Check existing webhooks
                resp = await client.get(
                    f"{OPENWA_BASE_URL}/api/sessions/{session_id}/webhooks",
                    headers=get_openwa_headers()
                )
                
                if resp.status_code == 200:
                    webhooks = resp.json()
                    already_registered = any(
                        wh.get("url") == WEBHOOK_URL for wh in webhooks if isinstance(wh, dict)
                    )
                    
                    if already_registered:
                        logger.info(f"✅ Webhook {WEBHOOK_URL} is already registered on OpenWA.")
                        return
                    
                    # Register webhook
                    reg_resp = await client.post(
                        f"{OPENWA_BASE_URL}/api/sessions/{session_id}/webhooks",
                        json={
                            "url": WEBHOOK_URL,
                            "events": ["message.received"]
                        },
                        headers=get_openwa_headers()
                    )
                    
                    if reg_resp.status_code in (200, 201):
                        logger.info(f"✅ Webhook registered successfully: {WEBHOOK_URL}")
                        return
                    else:
                        logger.warning(f"Webhook registration response ({reg_resp.status_code}): {reg_resp.text}")
            except Exception as e:
                logger.warning(f"[Attempt {attempt}/10] OpenWA setup wait: {e}")
            await asyncio.sleep(5)


async def send_whatsapp_message(chat_id: str, text: str):
    """Sends a text message to a WhatsApp chat via OpenWA REST API."""
    async with httpx.AsyncClient(timeout=30) as client:
        session_id = await resolve_session_id(client)
        
        # Try primary send-text endpoint
        url = f"{OPENWA_BASE_URL}/api/sessions/{session_id}/messages/send-text"
        payload = {"chatId": chat_id, "text": text}
        
        try:
            resp = await client.post(url, json=payload, headers=get_openwa_headers())
            if resp.status_code not in (200, 201):
                logger.error(f"Failed to send WhatsApp message ({resp.status_code}): {resp.text}")
            else:
                logger.info(f"Message sent successfully to {chat_id}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp message to {chat_id}: {e}")


# ── RAG Processing & Webhook Handler ───────────────────────────────────────

async def process_incoming_message(chat_id: str, user_query: str):
    """Async background task to query RAG backend and send WhatsApp response."""
    clean_q = user_query.strip().lower().rstrip(".!")
    
    # 1. Handle simple greetings
    if clean_q in GREETINGS:
        is_bengali = any(ord(char) >= 0x0980 and ord(char) <= 0x09FF for char in user_query)
        if is_bengali:
            greeting_resp = (
                "👋 *নমস্কার!* আমি পশ্চিম ত্রিপুরা জেলা তথ্য সহকারী।\n\n"
                "আমি আপনাকে জেলা প্রশাসন, অফিসের সময়সূচী, ডিএম/এসডিএম নির্দেশিকা, "
                "নিয়োগ এবং সরকারি পরিষেবা সম্পর্কিত তথ্যে সহায়তা করতে পারি।\n\n"
                "💡 যেকোনো প্রশ্ন নিচে টাইপ করুন! (যেমন: *পশ্চিম ত্রিপুরার ডিএম কে?*)"
            )
        else:
            greeting_resp = (
                "👋 *Hello!* I am the West Tripura District Information Assistant.\n\n"
                "How can I help you today? You can ask me about district offices, DM/SDM guidelines, "
                "employee lists, recruitment notifications, or government services in West Tripura.\n\n"
                "💡 Type your question below! (e.g. *Who is the DM of West Tripura?*)"
            )
        await send_whatsapp_message(chat_id, greeting_resp)
        return

    # 2. RAG Chat Endpoint Request
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            rag_resp = await client.post(
                f"{API_BASE_URL}/chat",
                json={"query": user_query},
                headers={"Content-Type": "application/json"}
            )
            rag_resp.raise_for_status()
            data = rag_resp.json()
            
        answer = data.get("answer", "No response generated.")
        sources = data.get("sources", [])
        
        # Append verified sources if present
        if sources:
            ref_lines = ["\n📌 *Verified Sources / উৎসসমূহ:*"]
            for i, src in enumerate(sources, 1):
                title = src.get("title", "West Tripura Document")
                url = src.get("url", "")
                section = src.get("section")
                if section:
                    ref_lines.append(f"{i}. {section} - {title}\n🔗 {url}")
                else:
                    ref_lines.append(f"{i}. {title}\n🔗 {url}")
            answer += "\n" + "\n".join(ref_lines)
            
        await send_whatsapp_message(chat_id, answer)

    except Exception as e:
        logger.error(f"Error processing RAG query for WhatsApp user {chat_id}: {e}", exc_info=True)
        err_msg = (
            "⚠️ An error occurred while processing your question. Please try again later.\n\n"
            "⚠️ আপনার প্রশ্নটি প্রক্রিয়া করার সময় একটি ত্রুটি ঘটেছে। অনুগ্রহ করে পরে আবার চেষ্টা করুন।"
        )
        await send_whatsapp_message(chat_id, err_msg)


@app.on_event("startup")
async def startup_event():
    """Trigger background task to ensure webhook is registered on launch."""
    asyncio.create_task(ensure_webhook_registered())


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "rag-whatsapp"}


@app.post("/webhook")
async def handle_openwa_webhook(request: Request):
    """OpenWA webhook event listener endpoint."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)
    
    # OpenWA payload extraction
    event = payload.get("event")
    data = payload.get("data") or payload
    
    # Ignore non-message events or messages sent by the bot itself
    is_from_me = False
    if isinstance(data.get("fromMe"), bool):
        is_from_me = data["fromMe"]
    elif isinstance(data.get("id"), dict) and data["id"].get("fromMe") is True:
        is_from_me = True

    if is_from_me:
        return JSONResponse({"status": "ignored", "reason": "Self message"})

    chat_id = data.get("from") or data.get("chatId") or data.get("chat", {}).get("id")
    user_query = data.get("body") or data.get("content") or data.get("text")
    
    if chat_id and user_query:
        logger.info(f"Received WhatsApp message from {chat_id}: {user_query}")
        # Run RAG processing asynchronously in background to acknowledge OpenWA webhook quickly (<1s)
        return JSONResponse(
            {"status": "processing"},
            background=BackgroundTask(process_incoming_message, chat_id, user_query)
        )
        
    return JSONResponse({"status": "ignored", "reason": "No query content"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
