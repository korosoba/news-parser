import os
import time
import json
import asyncio
import logging
import requests
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# =========================
# ЛОГИ
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# FLASK (Render Web Service)
# =========================
web_app = Flask(__name__)

# =========================
# ENV
# =========================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO_NAME")
GITHUB_WORKFLOW = os.getenv("GITHUB_WORKFLOW_NAME")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

ALLOWED_DOMAINS = ["screenrant.com", "cbr.com", "collider.com", "movieweb.com"]

# =========================
# Проверка URL
# =========================
def is_valid_url(url: str) -> bool:
    return any(domain in url.lower() for domain in ALLOWED_DOMAINS)

# =========================
# GitHub workflow
# =========================
def dispatch_workflow(article_url: str) -> str:
    dispatch_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"

    data = {
        "ref": "main",
        "inputs": {
            "urls": article_url
        }
    }

    response = requests.post(dispatch_url, headers=GITHUB_HEADERS, json=data)

    if response.status_code != 204:
        raise Exception(f"Dispatch failed: {response.status_code} {response.text}")

    time.sleep(2)
    return get_latest_dispatch_run_id()

def get_latest_dispatch_run_id() -> str:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs"
    params = {"event": "workflow_dispatch", "branch": "main", "per_page": 5}

    response = requests.get(url, headers=GITHUB_HEADERS, params=params)

    if not response.ok:
        raise Exception(f"Cannot get runs: {response.status_code} {response.text}")

    runs = response.json().get("workflow_runs", [])

    if not runs:
        raise Exception("No workflow_dispatch runs found")

    runs.sort(key=lambda r: r["created_at"], reverse=True)
    return str(runs[0]["id"])

def wait_for_run_completion(run_id: str, timeout=300, interval=10) -> bool:
    start_time = time.time()

    while time.time() - start_time < timeout:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}"
        response = requests.get(url, headers=GITHUB_HEADERS)

        if response.ok:
            data = response.json()
            status = data["status"]
            conclusion = data["conclusion"]

            logging.info(f"Workflow status: {status}")

            if status == "completed":
                return conclusion == "success"

        time.sleep(interval)

    raise TimeoutError("Workflow timeout")

# =========================
# Telegram handler
# =========================
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    logging.info(f"Получен URL: {url}")

    if not url.startswith("http"):
        await update.message.reply_text("Это не ссылка. Отправь URL статьи.")
        return

    if not is_valid_url(url):
        await update.message.reply_text(
            "Разрешены только screenrant.com, cbr.com, collider.com, movieweb.com"
        )
        return

    await update.message.reply_text("🚀 Запускаю обработку...")

    try:
        run_id = dispatch_workflow(url)
        success = wait_for_run_completion(run_id)

        if not success:
            await update.message.reply_text("Workflow завершился с ошибкой.")
            return

        await update.message.reply_text("✅ Обработка завершена!")

    except Exception as e:
        logging.error(str(e))
        await update.message.reply_text(f"Ошибка: {str(e)}")

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if not RENDER_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL не найден!")

    webhook_url = f"{RENDER_URL}/{TELEGRAM_BOT_TOKEN}"

    async def setup():
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.bot.set_webhook(webhook_url)
        logging.info(f"Webhook установлен: {webhook_url}")

    asyncio.run(setup())

    # Health endpoint
    @web_app.route("/")
    def health():
        return "Bot is alive", 200

    # Telegram webhook endpoint
    @web_app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
    def webhook():
        update = Update.de_json(request.get_json(force=True), app.bot)
        asyncio.run(app.process_update(update))
        return "ok", 200

    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
