import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

web_app = Flask(__name__)

# Создаём один event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# =========================
# HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logging.info(f"Получено сообщение: {text}")
    await update.message.reply_text(f"Ты написал: {text}")

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# =========================
# STARTUP (ОДИН РАЗ)
# =========================
async def startup():
    await app.initialize()
    await app.start()

    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    webhook_url = f"{render_url}/{TELEGRAM_BOT_TOKEN}"

    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_webhook(webhook_url)

    logging.info(f"Webhook установлен: {webhook_url}")

loop.run_until_complete(startup())

# =========================
# HEALTH CHECK
# =========================
@web_app.route("/")
def health():
    return "Bot is alive", 200

# =========================
# WEBHOOK ENDPOINT
# =========================
@web_app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    loop.create_task(app.process_update(update))
    return "ok", 200

# =========================
# RUN FLASK
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)
