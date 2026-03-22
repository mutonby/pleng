"""Telegram bot — bridge between Telegram and the Agent container.

- Markdown → Telegram HTML conversion
- Typing indicator while agent thinks
- /sites, /new, /help commands
"""
import asyncio
import html
import logging
import os
import re
import sys
import threading
import time

import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("telegram-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8000")
PLATFORM_URL = os.environ.get("PLATFORM_API_URL", "http://platform-api:8000")


# ── Markdown → Telegram HTML ────────────────────────────

def md_to_tg(text: str) -> str:
    """Convert Claude's markdown to Telegram-compatible HTML."""
    # Escape HTML entities first
    text = html.escape(text)

    # Code blocks: ```lang\n...\n``` → <pre><code>...</code></pre>
    def replace_code_block(m):
        lang = m.group(1)
        code = m.group(2)
        if lang:
            return f'<pre><code class="language-{lang}">{code}</code></pre>'
        return f'<pre>{code}</pre>'
    text = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, text, flags=re.DOTALL)

    # Inline code: `...` → <code>...</code>
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)

    # Bold: **...** → <b>...</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # Italic: *...* → <i>...</i>
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', text)

    # Strikethrough: ~~...~~ → <s>...</s>
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Headers: # ... → <b>...</b>
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Bullet lists
    text = re.sub(r'^[-•]\s+', '• ', text, flags=re.MULTILINE)

    return text


# ── Commands ────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Pleng</b> — Your AI Platform Engineer\n\n"
        "Tell me what you need:\n"
        "• <i>deploy github.com/user/repo</i>\n"
        "• <i>build me a booking API with Postgres</i>\n"
        "• <i>show me the logs for my-app</i>\n\n"
        "/sites — list sites\n"
        "/new — new conversation\n"
        "/help — help",
        parse_mode="HTML",
    )


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    try:
        requests.post(f"{AGENT_URL}/chat/reset", json={"session_id": chat_id}, timeout=5)
    except Exception:
        pass
    await update.message.reply_text("Session reset.")


async def cmd_sites(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        sites = requests.get(f"{PLATFORM_URL}/api/sites", timeout=10).json()
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    if not sites:
        await update.message.reply_text("No sites deployed yet.")
        return

    icons = {"staging": "🟡", "production": "🟢", "stopped": "🔴", "generating": "🟣", "error": "❌"}
    text = "<b>Sites:</b>\n\n"
    for s in sites:
        icon = icons.get(s["status"], "⚪")
        domain = s.get("production_domain") or s.get("staging_domain") or ""
        url = f"https://{domain}" if s.get("production_domain") else f"http://{domain}" if domain else ""
        text += f"{icon} <b>{s['name']}</b> — {s['status']}\n"
        if url:
            text += f"    {url}\n"
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Pleng — Your AI Platform Engineer</b>\n\n"
        "<b>Commands:</b>\n"
        "/new — new conversation\n"
        "/sites — list sites\n"
        "/help — help\n\n"
        "<b>You can say:</b>\n"
        "• deploy github.com/user/repo\n"
        "• build me an app that does X\n"
        "• logs for my-app\n"
        "• stop / restart my-app\n"
        "• promote my-app to app.example.com",
        parse_mode="HTML",
    )


# ── Message handler ─────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = update.message.text or update.message.caption or ""
    if not text:
        return

    # Send typing indicator
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Process in background
    threading.Thread(
        target=_agent_respond,
        args=(chat_id, text),
        daemon=True,
    ).start()


def _agent_respond(chat_id: str, message: str):
    """Call agent, keep typing, send formatted response."""
    # Keep typing while waiting
    typing = True

    def keep_typing():
        while typing:
            try:
                asyncio.run_coroutine_threadsafe(
                    _app.bot.send_chat_action(chat_id=chat_id, action="typing"),
                    _loop,
                ).result(timeout=5)
            except Exception:
                pass
            time.sleep(4)

    t = threading.Thread(target=keep_typing, daemon=True)
    t.start()

    try:
        r = requests.post(
            f"{AGENT_URL}/chat",
            json={"message": message, "session_id": chat_id},
            timeout=600,
        )
        response = r.json().get("response", "No response.")
    except requests.ConnectionError:
        response = "Agent not available. Try again."
    except Exception as e:
        response = f"Error: {e}"

    typing = False

    # Convert markdown to Telegram HTML and send
    _send(chat_id, response)


def _send(chat_id: str, text: str):
    """Send message with HTML formatting, fallback to plain text."""
    if not _app or not _loop:
        return

    formatted = md_to_tg(text)

    # Split long messages
    chunks = [formatted[i:i + 4000] for i in range(0, len(formatted), 4000)] if len(formatted) > 4000 else [formatted]

    for chunk in chunks:
        async def _do_send(c=chunk):
            try:
                await _app.bot.send_message(chat_id=chat_id, text=c, parse_mode="HTML")
            except Exception:
                # HTML parse failed — send as plain text
                try:
                    plain = re.sub(r'<[^>]+>', '', c)
                    await _app.bot.send_message(chat_id=chat_id, text=plain)
                except Exception as e:
                    logger.error(f"Send failed: {e}")

        asyncio.run_coroutine_threadsafe(_do_send(), _loop)


_app = None
_loop = None


def main():
    global _app, _loop

    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    logger.info("Starting Telegram bot...")

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    _app = Application.builder().token(TOKEN).build()

    _app.add_handler(CommandHandler("start", cmd_start))
    _app.add_handler(CommandHandler("new", cmd_new))
    _app.add_handler(CommandHandler("sites", cmd_sites))
    _app.add_handler(CommandHandler("help", cmd_help))
    _app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_message))

    async def run():
        await _app.initialize()
        await _app.bot.delete_webhook(drop_pending_updates=True)
        await _app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        await _app.start()
        logger.info("Telegram bot polling started")
        while True:
            await asyncio.sleep(3600)

    _loop.run_until_complete(run())


if __name__ == "__main__":
    main()
