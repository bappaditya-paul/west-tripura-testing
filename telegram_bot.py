"""Telegram channel adapter for the West Tripura Citizen RAG API.

The bot is intentionally thin: Telegram handles transport and formatting while
FastAPI owns the RAG pipeline, session state, retrieval, grounding and sources.
"""

from __future__ import annotations

import logging
import os
import sys
from html import escape

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
API_TIMEOUT_SECONDS = float(os.getenv("TELEGRAM_API_TIMEOUT", "90"))
MAX_TELEGRAM_MESSAGE = 4000

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("west_tripura.telegram")

WELCOME = (
    "👋 Welcome to the West Tripura District Assistant!\n\n"
    "Ask me about government services, certificates, forms, district offices, "
    "notifications and other official West Tripura information.\n\n"
    "You can write in English, Bengali or Benglish.\n\n"
    "বাংলাতেও প্রশ্ন করতে পারেন।\n\n"
    "Example: How can I apply for PRTC?"
)

HELP_TEXT = (
    "Available commands:\n"
    "/start - Welcome message\n"
    "/help - Show help\n"
    "/health - Check the RAG API\n"
    "/reset - Start a new conversation\n\n"
    "Example questions:\n"
    "• How can I apply for PRTC?\n"
    "• PRTC er jonno ki ki document lagbe?\n"
    "• পশ্চিম ত্রিপুরার ডিএম অফিসের নম্বর কী?"
)

GREETINGS = {
    "hi", "hello", "hey", "namaste", "good morning", "good evening",
    "নমস্কার", "হাই", "হ্যালো",
}


def _session_id(update: Update) -> str:
    """Create a stable API session identifier for one Telegram chat."""
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    user_id = update.effective_user.id if update.effective_user else "unknown"
    return f"telegram:{chat_id}:{user_id}"


def _split_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE) -> list[str]:
    """Split long answers so Telegram's message-size limit is respected."""
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < 500:
            cut = remaining.rfind(" ", 0, limit)
        if cut < 500:
            cut = limit
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


async def query_rag(question: str, session_id: str) -> dict:
    """Call the canonical FastAPI RAG endpoint."""
    payload = {
        "query": question,
        "top_k": 5,
        "session_id": session_id,
    }
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{API_BASE_URL}/chat",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{API_BASE_URL}/health")
            return response.status_code == 200
    except Exception as exc:
        logger.warning("RAG API health check failed: %s", exc)
        return False


async def _reply(update: Update, text: str) -> None:
    """Send a long answer safely without relying on Markdown parsing."""
    if not update.message:
        return
    for part in _split_message(text):
        await update.message.reply_text(part, disable_web_page_preview=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, WELCOME)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, HELP_TEXT)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # The API accepts a session_id on chat requests. A reset is represented by
    # a fresh Telegram session id on the next message; no vector data is deleted.
    await _reply(update, "✅ Conversation reset. Your next question will start a fresh chat context.")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok = await health_check()
    await _reply(
        update,
        "✅ RAG API is healthy and reachable."
        if ok
        else "❌ RAG API is unreachable. Check: docker compose ps && docker compose logs api",
    )


def _format_result(result: dict) -> str:
    answer = str(result.get("answer") or "I could not generate an answer.").strip()
    sources = result.get("sources") or result.get("references") or []
    document_links = result.get("document_links") or result.get("documents") or []

    blocks = [answer]

    source_lines: list[str] = []
    for index, source in enumerate(sources[:5], 1):
        if not isinstance(source, dict):
            continue
        title = source.get("title") or "Official source"
        url = source.get("url")
        if url:
            source_lines.append(f"{index}. {title}\n   {url}")
        else:
            source_lines.append(f"{index}. {title}")
    if source_lines:
        blocks.append("📚 Sources\n" + "\n".join(source_lines))

    doc_lines: list[str] = []
    for index, document in enumerate(document_links[:5], 1):
        if isinstance(document, str):
            doc_lines.append(f"{index}. {document}")
            continue
        if isinstance(document, dict):
            title = document.get("title") or document.get("name") or "Official document"
            url = document.get("url") or document.get("download_url")
            if url:
                doc_lines.append(f"{index}. {title}\n   {url}")
    if doc_lines:
        blocks.append("📄 Official documents\n" + "\n".join(doc_lines))

    return "\n\n".join(blocks)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_query = update.message.text.strip()
    clean_q = user_query.lower().rstrip(".!?")
    logger.info(
        "Telegram query user=%s chat=%s: %s",
        update.effective_user.id if update.effective_user else "unknown",
        update.effective_chat.id if update.effective_chat else "unknown",
        user_query,
    )

    if clean_q in GREETINGS:
        bengali = any("\u0980" <= char <= "\u09ff" for char in user_query)
        greeting = (
            "👋 নমস্কার! আমি পশ্চিম ত্রিপুরা জেলা তথ্য সহকারী।\n\n"
            "সরকারি পরিষেবা, সার্টিফিকেট, ফর্ম, অফিস বা নোটিশ সম্পর্কে প্রশ্ন করুন।"
            if bengali
            else "👋 Hello! I am the West Tripura District Information Assistant.\n\n"
                 "Ask me about government services, certificates, forms, offices or notices."
        )
        await _reply(update, greeting)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        result = await query_rag(user_query, _session_id(update))
        await _reply(update, _format_result(result))
    except httpx.HTTPStatusError as exc:
        logger.error("RAG API returned HTTP %s: %s", exc.response.status_code, exc)
        await _reply(update, f"⚠️ The RAG API returned an error ({exc.response.status_code}). Please try again.")
    except httpx.TimeoutException:
        logger.error("RAG API timed out for query: %s", user_query)
        await _reply(update, "⏳ The request took too long. Please try again with a shorter question.")
    except Exception as exc:
        logger.error("Telegram message handling failed: %s", exc, exc_info=True)
        await _reply(update, "⚠️ I could not process that request. Please check the RAG API status and try again.")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        sys.exit(1)

    logger.info("Starting Telegram bot; RAG API=%s", API_BASE_URL)
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
