# telegram_bot_webhook.py
import os
import time
import requests
import json
import asyncio
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# =========================
# 🔹 Flask для Render
# =========================
web_app = Flask(__name__)

# =========================
# 🔹 Загрузка переменных
# =========================
load_dotenv("korosoba.env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO_NAME")
GITHUB_WORKFLOW = os.getenv("GITHUB_WORKFLOW_NAME")

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

ALLOWED_DOMAINS = ["screenrant.com", "cbr.com", "collider.com", "movieweb.com"]

# =========================
# 🔹 Проверка URL
# =========================
def is_valid_url(url: str) -> bool:
    return any(domain in url.lower() for domain in ALLOWED_DOMAINS)

# =========================
# 🔹 GitHub workflow dispatch + безопасный run_id
# =========================
def dispatch_workflow(article_url: str) -> str:
    dispatch_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    data = {"ref": "main", "inputs": {"urls": article_url}}
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
        raise Exception(f"Cannot get workflow runs: {response.status_code} {response.text}")
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
            status = response.json()["status"]
            conclusion = response.json()["conclusion"]
            if status == "completed":
                return conclusion == "success"
        time.sleep(interval)
    raise TimeoutError("Workflow timeout")

# =========================
# 🔹 Обработка сообщений
# =========================
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("Это не похоже на ссылку. Отправь URL статьи.")
        return
    if not is_valid_url(url):
        await update.message.reply_text(
            "Ссылка должна быть с screenrant.com, cbr.com, collider.com или movieweb.com."
        )
        return
    await update.message.reply_text(f"Обрабатываю: {url}")
    try:
        await update.message.reply_text("Запускаю обработку... (1–3 минуты)")
        run_id = dispatch_workflow(url)
        success = wait_for_run_completion(run_id)
        if not success:
            await update.message.reply_text("Workflow завершился с ошибкой. Проверь логи GitHub Actions.")
            return
        await asyncio.sleep(20)
        contents_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/extracted_articles?ref=main"
        resp = requests.get(contents_url, headers=GITHUB_HEADERS)
        if not resp.ok:
            raise Exception(f"Не удалось получить список файлов: {resp.status_code} {resp.text}")
        files = resp.json()
        report_files = [f for f in files if f["name"].startswith("extraction_report_") and f["name"].endswith(".json")]
        if not report_files:
            raise Exception("Не найден ни один extraction_report.json")
        report_files.sort(key=lambda f: f["name"], reverse=True)
        report_file = report_files[0]
        json_resp = requests.get(report_file["download_url"])
        if not json_resp.ok:
            raise Exception("Не удалось скачать report.json")
        reports = json_resp.json()
        if not reports:
            raise Exception("Report пустой")
        latest = reports[0]
        summary_filename = latest.get("summary", {}).get("summary_file")
        if not summary_filename:
            raise Exception("В отчёте нет summary_file")
        raw_summary_url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/extracted_articles/{summary_filename}"
        summary_resp = requests.get(raw_summary_url)
        if not summary_resp.ok:
            raise Exception(f"Не удалось скачать саммари: {summary_resp.status_code} {summary_resp.text}")
        temp_file = "temp_summary.txt"
        with open(temp_file, "wb") as f:
            f.write(summary_resp.content)
        await update.message.reply_document(
            document=open(temp_file, "rb"),
            caption=f"Groq-саммари для статьи:\n{url}"
        )
        os.remove(temp_file)
        await update.message.reply_text("Готово! Можешь прислать следующую ссылку.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")
        print(f"Полная ошибка: {type(e).__name__}: {str(e)}")

# =========================
# 🔹 MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    # =========================
    # Настройка webhook на Render
    # =========================
    # Ваш публичный URL Render:
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")  # автоматически доступен на Render
    webhook_url = f"{RENDER_URL}/{TELEGRAM_BOT_TOKEN}"
    app.bot.set_webhook(webhook_url)
    print(f"Webhook установлен: {webhook_url}")

    # Flask endpoint для webhook
    @web_app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
    def webhook():
        update = Update.de_json(request.get_json(force=True), app.bot)
        asyncio.run(app.update_queue.put(update))
        return "ok", 200

    # Flask слушает порт
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
