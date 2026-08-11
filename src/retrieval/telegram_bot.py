"""
telegram_bot.py
===============
Telegram Bot Client using python-telegram-bot.
Runs in polling mode locally to receive questions, queries the local RAG engine,
and replies with user-friendly formatting and sources.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent))

from dotenv import load_dotenv
load_dotenv(_HERE.parent.parent / ".env")

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from query_pipeline import RAGPipeline

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load Telegram Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Initialize pipeline
try:
    pipeline = RAGPipeline()
    logger.info("✓ RAG Pipeline initialized successfully inside Telegram Bot.")
except Exception as exc:
    logger.error(f"✗ Failed to initialize RAG Pipeline: {exc}")
    sys.exit(1)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a friendly greeting explaining what the bot can do."""
    welcome_text = (
        "👋 Welcome to the **West Tripura District Assistant**!\n\n"
        "I can answer your queries about district notifications, office details, "
        "recruitment, guidelines, and public services in West Tripura.\n\n"
        "💬 Feel free to ask me anything in **English** or **Bengali** (বাংলা)!\n"
        "Example: *Who is the DM of West Tripura?* or *পশ্চিম ত্রিপুরার ডিএম কে?*\n\n"
        "---"
        "\n👋 **পশ্চিম ত্রিপুরা জেলা সহকারীতে** আপনাকে স্বাগতম!\n\n"
        "আমি আপনাকে জেলা নোটিফিকেশন, অফিসের বিবরণ, নিয়োগ, গাইডলাইন এবং "
        "জনসাধারণের জন্য উপলব্ধ নানা পরিষেবা সম্পর্কিত প্রশ্নের উত্তর দিতে পারি।\n\n"
        "💬 যেকোনো প্রশ্ন **ইংরেজি** বা **বাংলায়** নির্দ্বিধায় জিজ্ঞাসা করুন!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


GREETINGS = {"hi", "hello", "hey", "namaste", "good morning", "good evening", "নমস্কার", "হাই", "হ্যালো", "নমস্কার।"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive text queries, request answers from the RAG engine, and reply."""
    user_query = update.message.text
    if not user_query:
        return

    clean_q = user_query.strip().lower()
    logger.info(f"Received query from user {update.effective_user.id}: {user_query}")

    # 1. Immediate friendly handling for simple greetings
    if clean_q in GREETINGS or clean_q.rstrip(".!") in GREETINGS:
        is_bengali = any(ord(char) >= 0x0980 and ord(char) <= 0x09FF for char in user_query)
        if is_bengali:
            greeting_resp = (
                "👋 **নমস্কার!** আমি পশ্চিম ত্রিপুরা জেলা তথ্য সহকারী।\n\n"
                "আমি আপনাকে জেলা প্রশাসন, অফিসের সময়সূচী, ডিএম/এসডিএম অফিস নির্দেশিকা, "
                "নিয়োগ এবং সরকারি পরিষেবা সম্পর্কিত তথ্যে সহায়তা করতে পারি।\n\n"
                "💡 যেকোনো প্রশ্ন নিচে টাইপ করুন! (যেমন: *পশ্চিম ত্রিপুরার ডিএম কে?*)"
            )
        else:
            greeting_resp = (
                "👋 **Hello!** I am the West Tripura District Information Assistant.\n\n"
                "How can I help you today? You can ask me about district offices, DM/SDM guidelines, "
                "employee lists, recruitment notifications, or government services in West Tripura.\n\n"
                "💡 Type your question below! (e.g. *Who is the DM of West Tripura?*)"
            )
        await update.message.reply_text(greeting_resp, parse_mode="Markdown")
        return

    # 2. Send typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Run RAGService answer generation with RRF Hybrid Retrieval & Benglish Query Normalization
        from backend.services.rag_service import get_rag_service
        rag_service = get_rag_service()
        
        result = await rag_service.answer(query=user_query, top_k=5)
        answer = result["answer"]
        sources = result.get("sources", [])

        # If there are sources, append formatted source list
        if sources:
            ref_lines = []
            for src in sources:
                title = src.get("title") or "West Tripura Document"
                section = src.get("section")
                url = src.get("url")
                if url:
                    if section:
                        ref_text = f"📍 [{section} - {title}]({url})"
                    else:
                        ref_text = f"📍 [{title}]({url})"
                    ref_lines.append(ref_text)
            
            if ref_lines:
                is_bengali = any(ord(char) >= 0x0980 and ord(char) <= 0x09FF for char in user_query)
                ref_header = "\n\n📖 **Verified Sources / উৎসসমূহ:**\n" if is_bengali else "\n\n📖 **Verified Sources:**\n"
                answer_with_sources = answer + ref_header + "\n".join(ref_lines)
            else:
                answer_with_sources = answer
        else:
            answer_with_sources = answer

        # Reply to user
        await update.message.reply_text(
            answer_with_sources,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ An error occurred while processing your question. Please try again later.\n\n"
            "⚠️ আপনার প্রশ্নটি প্রক্রিয়া করার সময় একটি ত্রুটি ঘটেছে। অনুগ্রহ করে পরে আবার চেষ্টা করুন।"
        )


def main() -> None:
    """Start the bot using polling."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    # Build bot application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run polling loop
    logger.info("⚡ Starting Telegram Bot polling loop locally...")
    application.run_polling()


if __name__ == "__main__":
    main()
