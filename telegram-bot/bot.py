"""Telegram bot — bridge between Telegram and the Agent container.

- File upload/download support (tar.gz, documents, images)
- Markdown → Telegram HTML conversion
- Typing indicator while agent thinks
- Graceful timeout handling
"""
import asyncio
import html
import json
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
ALLOWED_CHAT_IDS = set(os.environ.get("TELEGRAM_CHAT_ID", "").split(","))
AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8000")
PLATFORM_URL = os.environ.get("PLATFORM_API_URL", "http://platform-api:8000")
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/opt/pleng/projects")


def _is_allowed(update: Update) -> bool:
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALLOWED_CHAT_IDS:
        logger.warning(f"Blocked: {chat_id}")
        return False
    return True


# ── Markdown → Telegram HTML ────────────────────────────

def md_to_tg(text: str) -> str:
    text = html.escape(text)
    def replace_code_block(m):
        lang = m.group(1)
        code = m.group(2)
        return f'<pre><code class="language-{lang}">{code}</code></pre>' if lang else f'<pre>{code}</pre>'
    text = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, text, flags=re.DOTALL)
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^[-•]\s+', '• ', text, flags=re.MULTILINE)
    return text


# ── Commands ────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "<b>Pleng</b> — Your AI Platform Engineer\n\n"
        "Tell me what you need:\n"
        "• <i>deploy github.com/user/repo</i>\n"
        "• <i>build me a booking API with Postgres</i>\n"
        "• Send me a tar.gz or any file\n\n"
        "/sites — list sites\n"
        "/new — new conversation\n"
        "/help — help",
        parse_mode="HTML",
    )


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    try:
        requests.post(f"{AGENT_URL}/chat/reset", json={"session_id": chat_id}, timeout=5)
    except Exception:
        pass
    await update.message.reply_text("Session reset.")


async def cmd_sites(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
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
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "<b>Pleng — Your AI Platform Engineer</b>\n\n"
        "<b>Commands:</b>\n"
        "/new — new conversation\n"
        "/sites — list sites\n"
        "/help — help\n\n"
        "<b>You can say:</b>\n"
        "• deploy github.com/user/repo\n"
        "• build me an app that does X\n"
        "• logs / stop / restart my-app\n"
        "• promote my-app to app.example.com\n\n"
        "<b>Files:</b>\n"
        "• Send tar.gz, zip, or any file\n"
        "• Ask me to send you a project as tar.gz",
        parse_mode="HTML",
    )


# ── Message handler (text + files) ──────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    message = update.message
    user_text = message.text or message.caption or ""

    # Handle file attachments
    attachments = []
    if message.document:
        doc = message.document
        file = await doc.get_file()
        save_dir = os.path.join(PROJECTS_DIR, "_uploads")
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, doc.file_name or f"file_{doc.file_id}")
        await file.download_to_drive(file_path)
        attachments.append({"name": doc.file_name, "path": file_path, "size": doc.file_size})
        if not user_text:
            user_text = f"I'm sending you the file: {doc.file_name}"

    if message.photo:
        photo = message.photo[-1]
        file = await photo.get_file()
        save_dir = os.path.join(PROJECTS_DIR, "_uploads")
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, f"photo_{photo.file_id}.jpg")
        await file.download_to_drive(file_path)
        attachments.append({"name": "photo.jpg", "path": file_path})
        if not user_text:
            user_text = "I'm sending you a photo"

    if not user_text:
        return

    # Add attachment info to message
    if attachments:
        user_text += "\n\nAttached files:\n"
        for a in attachments:
            user_text += f"- {a['name']} (saved at {a['path']})\n"
        user_text += "You can read these files with the Read tool."

    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    threading.Thread(
        target=_agent_respond,
        args=(chat_id, user_text),
        daemon=True,
    ).start()


def _agent_respond(chat_id: str, message: str):
    """Call agent, keep typing, send response + any files."""
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
            timeout=900,  # 15 minutes for big generations
        )
        data = r.json()
        response = data.get("response", "No response.")
    except requests.exceptions.ReadTimeout:
        response = "The agent is still working but it's taking too long for one message. Try asking for the status or a simpler task."
    except requests.ConnectionError:
        response = "Agent not available. Try again in a moment."
    except Exception as e:
        response = f"Error: {e}"

    typing = False

    # Send text response
    _send_text(chat_id, response)

    # Check if response mentions sending a file
    _check_and_send_files(chat_id, response)


def _check_and_send_files(chat_id: str, response: str):
    """If the agent mentions a file path, offer to send it."""
    # Look for tar.gz or zip paths in the response
    file_patterns = re.findall(r'(/opt/pleng/projects/[^\s\n]+\.(?:tar\.gz|zip|tgz))', response)
    for path in file_patterns:
        if os.path.exists(path):
            _send_file(chat_id, path)


def _send_text(chat_id: str, text: str):
    if not _app or not _loop:
        return

    formatted = md_to_tg(text)
    chunks = [formatted[i:i + 4000] for i in range(0, len(formatted), 4000)] if len(formatted) > 4000 else [formatted]

    for chunk in chunks:
        async def _do_send(c=chunk):
            try:
                await _app.bot.send_message(chat_id=chat_id, text=c, parse_mode="HTML")
            except Exception:
                try:
                    plain = re.sub(r'<[^>]+>', '', c)
                    await _app.bot.send_message(chat_id=chat_id, text=plain)
                except Exception as e:
                    logger.error(f"Send failed: {e}")

        asyncio.run_coroutine_threadsafe(_do_send(), _loop)


def _send_file(chat_id: str, file_path: str):
    """Send a file as a Telegram document."""
    if not _app or not _loop:
        return

    async def _do_send():
        try:
            with open(file_path, "rb") as f:
                await _app.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=os.path.basename(file_path),
                )
        except Exception as e:
            logger.error(f"File send failed: {e}")

    asyncio.run_coroutine_threadsafe(_do_send(), _loop)


_app = None
_loop = None


def main():
    global _app, _loop

    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    # Create uploads dir
    os.makedirs(os.path.join(PROJECTS_DIR, "_uploads"), exist_ok=True)

    logger.info("Starting Telegram bot...")

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    _app = Application.builder().token(TOKEN).build()

    _app.add_handler(CommandHandler("start", cmd_start))
    _app.add_handler(CommandHandler("new", cmd_new))
    _app.add_handler(CommandHandler("sites", cmd_sites))
    _app.add_handler(CommandHandler("help", cmd_help))
    _app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.PHOTO, handle_message))

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
