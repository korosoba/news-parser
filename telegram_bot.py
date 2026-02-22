# telegram_bot.py

import os
import time
import requests
import json
import asyncio
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# =========================
# 🔹 Flask для Render
# =========================

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot is running", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 🔹 Загрузка переменных
# =========================

load_dotenv("korosoba.env")

print("=== Отладка переменных из .env ===")
print("TELEGRAM_BOT_TOKEN:", "OK" if os.getenv("TELEGRAM_BOT_TOKEN") else "не найден")
print("GITHUB_TOKEN:", "OK" if os.getenv("GITHUB_TOKEN") else "не найден")
print("GITHUB_REPO_OWNER:", os.getenv("GITHUB_REPO_OWNER", "не найден"))
print("GITHUB_REPO_NAME:", os.getenv("GITHUB_REPO_NAME", "не найден"))
print("GITHUB_WORKFLOW_NAME:", os.getenv("GITHUB_WORKFLOW_NAME", "не найден"))
print("====================================")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
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
# 🔹 Вся твоя логика ниже — без изменений
# =========================

def is_valid_url(url: str) -> bool:
    return any(domain in url.lower() for domain in ALLOWED_DOMAINS)


def dispatch_workflow(article_url: str) -> str:
    dispatch_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"

    data = {
        "ref": "main",
        "inputs": {"urls": article_url}
    }

    response = requests.post(dispatch_url, headers=GITHUB_HEADERS, json=data)

    if response.status_code == 204:
        return get_latest_run_id()
    else:
        raise Exception(f"Dispatch failed: {response.status_code} {response.text}")


def get_latest_run_id() -> str:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1"
    response = requests.get(url, headers=GITHUB_HEADERS)
    if response.ok:
        runs = response.json()["workflow_runs"]
        if runs:
            return runs[0]["id"]
    raise Exception("No runs found")


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


async def handle_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("Это не похоже на ссылку.")
        return

    if not is_valid_url(url):
        await update.message.reply_text("Ссылка должна быть с разрешённого домена.")
        return

    await update.message.reply_text("Запускаю обработку...")

    try:
        run_id = dispatch_workflow(url)
        success = wait_for_run_completion(run_id)

        if not success:
            await update.message.reply_text("Workflow завершился с ошибкой.")
            return

        await asyncio.sleep(20)

        contents_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/extracted_articles?ref=main"
        resp = requests.get(contents_url, headers=GITHUB_HEADERS)

        files = resp.json()
        report_files = [f for f in files if f["name"].startswith("extraction_report_")]
        report_files.sort(key=lambda f: f["name"], reverse=True)
        report_file = report_files[0]

        json_resp = requests.get(report_file["download_url"])
        reports = json_resp.json()
        latest = reports[0]

        summary_filename = latest.get("summary", {}).get("summary_file")

        raw_summary_url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/extracted_articles/{summary_filename}"
        summary_resp = requests.get(raw_summary_url)

        temp_file = "temp_summary.txt"
        with open(temp_file, "wb") as f:
            f.write(summary_resp.content)

        await update.message.reply_document(
            document=open(temp_file, "rb"),
            caption=f"Саммари для статьи:\n{url}"
        )

        os.remove(temp_file)
        await update.message.reply_text("Готово!")

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")
        print(f"Ошибка: {e}")


# =========================
# 🔹 MAIN
# =========================

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    print("Бот запущен.")

    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_web, daemon=True).start()

    # Запускаем Telegram polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
