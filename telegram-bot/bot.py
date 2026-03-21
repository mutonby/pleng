"""Telegram bot — thin bridge between Telegram and the Agent container.

Receives messages, POSTs to agent /chat, sends response back.
"""
import asyncio
import logging
import os
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


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Pleng</b> — AI PaaS\n\n"
        "Dime que quieres desplegar:\n"
        "• <i>despliega github.com/user/repo</i>\n"
        "• <i>crea una API de reservas con Postgres</i>\n"
        "• <i>muestra los logs de mi-app</i>\n\n"
        "/sites — listar sites\n"
        "/new — nueva conversacion\n"
        "/help — ayuda",
        parse_mode="HTML",
    )


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    try:
        requests.post(f"{AGENT_URL}/chat/reset", json={"session_id": chat_id}, timeout=5)
    except Exception:
        pass
    await update.message.reply_text("Sesion limpia. Empezamos de nuevo.")


async def cmd_sites(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        sites = requests.get(f"{PLATFORM_URL}/api/sites", timeout=10).json()
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    if not sites:
        await update.message.reply_text("No hay sites desplegados.")
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
        "<b>Pleng — AI PaaS</b>\n\n"
        "<b>Comandos:</b>\n"
        "/new — nueva conversacion\n"
        "/sites — listar sites\n"
        "/help — ayuda\n\n"
        "<b>Puedes decirme:</b>\n"
        "• despliega github.com/user/repo\n"
        "• crea una app de X\n"
        "• logs de mi-app\n"
        "• para mi-app / reinicia mi-app\n"
        "• ponle reservas.midominio.com a mi-app",
        parse_mode="HTML",
    )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = update.message.text or update.message.caption or ""
    if not text:
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Run in background to not block
    threading.Thread(target=_agent_respond, args=(chat_id, text), daemon=True).start()


def _agent_respond(chat_id: str, message: str):
    """Call agent and send response back via Telegram."""
    import time

    # Keep typing indicator alive
    app_ref = _app
    loop_ref = _loop
    typing = True

    def keep_typing():
        while typing:
            try:
                asyncio.run_coroutine_threadsafe(
                    app_ref.bot.send_chat_action(chat_id=chat_id, action="typing"),
                    loop_ref,
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
        data = r.json()
        response = data.get("response", "Sin respuesta.")
    except Exception as e:
        response = f"Error: {e}"

    typing = False

    # Send response
    _send(chat_id, response)


def _send(chat_id: str, text: str):
    if not _app or not _loop:
        return

    # Split long messages
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)] if len(text) > 4000 else [text]

    for chunk in chunks:
        async def _do_send(c=chunk):
            try:
                await _app.bot.send_message(chat_id=chat_id, text=c, parse_mode=None)
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
