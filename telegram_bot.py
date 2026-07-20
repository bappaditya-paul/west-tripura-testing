from __future__ import annotations

import logging
import os
import sys

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WELCOME = """\
👋 Welcome to the West Tripura District Assistant!
I can answer your queries about district notifications, office details, recruitment, guidelines, and public services in West Tripura.

💬 Feel free to ask me anything in English or Bengali (বাংলা)!
Example: Who is the DM of West Tripura? or পশ্চিম ত্রিপুরার ডিএম কে?

---
👋 পশ্চিম ত্রিপুরা জেলা সহকারীতে আপনাকে স্বাগতম!
আমি আপনাকে জেলা নোটিফিকেশন, অফিসের বিবরণ, নিয়োগ, গাইডলাইন এবং জনসাধারণের জন্য উপলব্ধ নানা পরিষেবা সম্পর্কিত প্রশ্নের উত্তর দিতে পারি।

💬 যেকোনো প্রশ্ন ইংরেজি বা বাংলায় নির্দ্বিধায় জিজ্ঞাসা করুন!"""

HELP_TEXT = """\
*Available Commands:*
/start - Show welcome message
/help - Show this help
/reset - Clear conversation history
/health - Check API status

*Example questions:*
• Who is the DM of West Tripura?
• What are the office hours of the collector?
• Show me recruitment notices
• পশ্চিম ত্রিপুরার ডিএম কে?
• কালেক্টরের অফিসের সময় কী?"""  # noqa: E501

RESPONSE_500 = "\u26a0\ufe0f Processing error. Try rephrasing your question."
RESPONSE_TIMEOUT = "\u23f3 Taking longer than usual. Please try again."
RESPONSE_404 = "\u2753 That information isn't in my knowledge base yet."


def _session_id(user_id: int) -> str:
    return f"tg-{user_id}"


async def query_rag(question: str, session_id: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{API_BASE_URL}/api/v1/query",
            json={"query": question, "top_k": 5, "session_id": session_id},
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "telegram-bot-internal",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def reset_session_api(session_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{API_BASE_URL}/api/v1/query",
            json={"query": "", "top_k": 5, "session_id": session_id, "reset": True},
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "telegram-bot-internal",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{API_BASE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sid = _session_id(update.effective_user.id)
    try:
        await reset_session_api(sid)
        await update.message.reply_text("Conversation history cleared. How can I help you?")
    except Exception:
        await update.message.reply_text("Could not reset session. Please try again.")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok = await health_check()
    if ok:
        await update.message.reply_text("\u2705 API is healthy and running.")
    else:
        await update.message.reply_text("\u274c API is unreachable. Please check the docker services.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_query = update.message.text
    if not user_query:
        return

    user_id = update.effective_user.id
    sid = _session_id(user_id)
    logger.info("Query from user %d: %s", user_id, user_query)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        result = await query_rag(user_query, sid)
        answer = result.get("answer", "No answer received.")
        references = result.get("references", [])

        if references:
            ref_lines = ["\n\U0001f4ce *Sources:*"]
            for i, ref in enumerate(references, 1):
                title = ref.get("title", "Document")
                url = ref.get("url", "")
                ref_lines.append(f"{i}. [{title}]({url})")
            answer += "\n" + "\n".join(ref_lines)

        await update.message.reply_text(
            answer,
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN,
        )
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        logger.error("API error %d: %s", status, e)
        if status == 404:
            msg = RESPONSE_404
        elif status >= 500:
            msg = RESPONSE_500
        else:
            msg = f"API returned an error ({status}). Please try again later."
        await update.message.reply_text(msg)
    except httpx.TimeoutException:
        await update.message.reply_text(RESPONSE_TIMEOUT)
    except Exception as e:
        logger.error("Error handling message: %s", e)
        await update.message.reply_text(
            "An error occurred while processing your question. Please try again later."
        )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    logger.info("Starting Telegram bot, API at %s", API_BASE_URL)
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == "__main__":
    main()
