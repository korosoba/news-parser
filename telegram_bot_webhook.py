import os
import asyncio
import logging
from flask import Flask, request, abort
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

# Flask app
web_app = Flask(__name__)

# Telegram Application
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Хендлер для сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logging.info(f"Получено сообщение: {text} от {update.effective_user.id}")
    await update.message.reply_text(f"Ты написал: {text}")

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# HEALTH CHECK — синхронный, чтобы избежать ошибок с HEAD
@web_app.route("/", methods=["GET", "HEAD"])
def health():
    return "Bot is alive 🚀", 200

# WEBHOOK — асинхронный для эффективной обработки
@web_app.route("/webhook", methods=["POST"])
async def webhook():
    if request.headers.get("content-type") == "application/json":
        json_data = request.get_json(silent=True)
        if json_data:
            logging.info(f"Получен update от Telegram: {json_data}")
            update = Update.de_json(json_data, application.bot)
            if update:
                # Запускаем обработку в фоне
                asyncio.create_task(application.process_update(update))
            else:
                logging.warning("Не удалось десериализовать update")
        else:
            logging.warning("Пустой JSON в запросе")
        return "ok", 200
    logging.warning("Неверный content-type")
    abort(403)

# Инициализация приложения при старте
async def init_app():
    await application.initialize()
    await application.start()

    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        raise RuntimeError("RENDER_EXTERNAL_URL не найден! Проверь переменные окружения в Render Dashboard.")

    webhook_url = f"{render_url}/webhook"
    await application.bot.delete_webhook(drop_pending_updates=True)
    success = await application.bot.set_webhook(webhook_url)
    if success:
        logging.info(f"Webhook успешно установлен: {webhook_url}")
    else:
        logging.error("Не удалось установить webhook! Проверь URL и доступность.")

# Запускаем инициализацию
loop = asyncio.get_event_loop()
loop.run_until_complete(init_app())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # threaded=False для стабильности на бесплатном Render
    web_app.run(host="0.0.0.0", port=port, debug=False, threaded=False)
