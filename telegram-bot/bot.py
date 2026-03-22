"""Telegram bot — bridge between Telegram and the Agent container.

Features:
- Streaming responses via sendMessageDraft (Bot API 9.5)
- Markdown → Telegram HTML conversion
- /sites, /new, /help commands
"""
import asyncio
import html
import logging
import os
import re
import sys
import threading

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

def md_to_telegram_html(text: str) -> str:
    """Convert Claude's markdown to Telegram-compatible HTML."""
    # Escape HTML first
    text = html.escape(text)

    # Code blocks: ```lang\n...\n``` → <pre><code>...</code></pre>
    text = re.sub(
        r'```(\w*)\n(.*?)```',
        lambda m: f'<pre><code class="language-{m.group(1)}">{m.group(2)}</code></pre>' if m.group(1) else f'<pre>{m.group(2)}</pre>',
        text, flags=re.DOTALL,
    )

    # Inline code: `...` → <code>...</code>
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)

    # Bold: **...** → <b>...</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # Italic: *...* → <i>...</i>  (but not inside <b> tags)
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', text)

    # Strikethrough: ~~...~~ → <s>...</s>
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Headers: # ... → <b>...</b> (Telegram has no headers)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Bullet lists: - ... or • ... → • ...
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
    await update.message.reply_text("Session reset. Starting fresh.")


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
        "• stop my-app / restart my-app\n"
        "• promote my-app to app.example.com",
        parse_mode="HTML",
    )


# ── Message handler with streaming ──────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = update.message.text or update.message.caption or ""
    if not text:
        return

    # Start streaming response in background
    threading.Thread(
        target=_agent_respond_streaming,
        args=(chat_id, text, ctx.bot),
        daemon=True,
    ).start()


def _agent_respond_streaming(chat_id: str, message: str, bot):
    """Call agent with streaming and use sendMessageDraft for progressive display."""
    try:
        r = requests.post(
            f"{AGENT_URL}/chat/stream",
            json={"message": message, "session_id": chat_id},
            timeout=600,
            stream=True,
        )

        if r.status_code != 200:
            # Fallback to non-streaming
            r2 = requests.post(
                f"{AGENT_URL}/chat",
                json={"message": message, "session_id": chat_id},
                timeout=600,
            )
            response = r2.json().get("response", "No response.")
            _send_html(chat_id, md_to_telegram_html(response))
            return

        # Stream chunks via sendMessageDraft
        import json
        accumulated = ""
        draft_business_connection_id = None
        last_update = 0
        import time

        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk_data = json.loads(line)
                chunk = chunk_data.get("chunk", "")
                is_done = chunk_data.get("done", False)

                if chunk:
                    accumulated += chunk

                now = time.time()

                if is_done or (now - last_update > 0.8 and len(accumulated) > 20):
                    # Send draft update
                    telegram_text = md_to_telegram_html(accumulated)
                    if is_done:
                        # Final message — send as regular message
                        _send_html(chat_id, telegram_text)
                    else:
                        # Draft update
                        _send_draft(chat_id, telegram_text)
                    last_update = now

            except (json.JSONDecodeError, Exception):
                continue

        # If we never sent a final message
        if accumulated and not accumulated.strip():
            _send_html(chat_id, "No response.")
        elif not accumulated:
            _send_html(chat_id, "No response.")

    except requests.ConnectionError:
        _send_html(chat_id, "Agent not available. Try again in a moment.")
    except Exception as e:
        logger.error(f"Streaming failed: {e}", exc_info=True)
        # Fallback to non-streaming
        try:
            r = requests.post(
                f"{AGENT_URL}/chat",
                json={"message": message, "session_id": chat_id},
                timeout=600,
            )
            response = r.json().get("response", "No response.")
            _send_html(chat_id, md_to_telegram_html(response))
        except Exception as e2:
            _send_html(chat_id, f"Error: {e2}")


def _send_html(chat_id: str, text: str):
    """Send a final message with HTML formatting."""
    if not _app or not _loop:
        return

    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)] if len(text) > 4000 else [text]

    for chunk in chunks:
        async def _do_send(c=chunk):
            try:
                await _app.bot.send_message(chat_id=chat_id, text=c, parse_mode="HTML")
            except Exception:
                # Fallback without HTML if parsing fails
                try:
                    # Strip HTML tags for plain text fallback
                    plain = re.sub(r'<[^>]+>', '', c)
                    await _app.bot.send_message(chat_id=chat_id, text=plain)
                except Exception as e:
                    logger.error(f"Send failed: {e}")

        asyncio.run_coroutine_threadsafe(_do_send(), _loop)


def _send_draft(chat_id: str, text: str):
    """Send a streaming draft message."""
    if not _app or not _loop:
        return

    async def _do_draft():
        try:
            await _app.bot.send_message_draft(
                business_connection_id=None,
                chat_id=int(chat_id),
                text=text,
                parse_mode="HTML",
            )
        except AttributeError:
            # sendMessageDraft not available in this version, skip
            pass
        except Exception as e:
            logger.debug(f"Draft send failed: {e}")

    asyncio.run_coroutine_threadsafe(_do_draft(), _loop)


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
