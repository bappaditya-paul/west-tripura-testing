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
GREETINGS = {"hi", "hello", "hey", "namaste", "good morning", "good evening", "নমস্কার", "হাই", "হ্যালো"}


async def query_rag(question: str, session_id: str) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{API_BASE_URL}/chat",
            json={"query": question},
            headers={
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def reset_session_api(session_id: str) -> dict:
    return {"status": "ok"}


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
    await update.message.reply_text("Conversation reset.")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok = await health_check()
    if ok:
        await update.message.reply_text("✅ API is healthy and running.")
    else:
        await update.message.reply_text("❌ API is unreachable. Please check docker services.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_query = update.message.text
    if not user_query:
        return

    clean_q = user_query.strip().lower().rstrip(".!")
    user_id = update.effective_user.id
    sid = _session_id(user_id)
    logger.info("Query from user %d: %s", user_id, user_query)

    # Friendly immediate response for greetings
    if clean_q in GREETINGS:
        is_bengali = any(ord(char) >= 0x0980 and ord(char) <= 0x09FF for char in user_query)
        if is_bengali:
            greeting_text = (
                "👋 **নমস্কার!** আমি পশ্চিম ত্রিপুরা জেলা তথ্য সহকারী।\n\n"
                "আমি আপনাকে জেলা প্রশাসন, ডিএম/এসডিএম নির্দেশিকা, "
                "নিয়োগ এবং সরকারি পরিষেবা সম্পর্কিত তথ্য দিতে পারি।\n\n"
                "💡 আপনার প্রশ্নটি নিচে টাইপ করুন! (যেমন: *পশ্চিম ত্রিপুরার ডিএম কে?*)"
            )
        else:
            greeting_text = (
                "👋 **Hello!** I am the West Tripura District Information Assistant.\n\n"
                "How can I help you today? You can ask me about district offices, DM/SDM guidelines, "
                "employee lists, recruitment notifications, or public services in West Tripura.\n\n"
                "💡 Type your question below! (e.g. *Who is the DM of West Tripura?*)"
            )
        await update.message.reply_text(greeting_text, parse_mode=ParseMode.MARKDOWN)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        result = await query_rag(user_query, sid)
        answer = result.get("answer", "No answer received.")
        sources = result.get("sources", [])

        if sources:
            ref_lines = ["\n\U0001f4ce *Sources / উৎসসমূহ:*"]
            for i, ref in enumerate(sources, 1):
                title = ref.get("title", "Document")
                url = ref.get("url", "")
                section = ref.get("section")
                if section:
                    ref_lines.append(f"{i}. [{section} - {title}]({url})")
                else:
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
