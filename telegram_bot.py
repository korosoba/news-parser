# telegram_bot.py
import os
import time
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

load_dotenv()

print("=== Отладка переменных из .env ===")
print("TELEGRAM_BOT_TOKEN:", os.getenv("TELEGRAM_BOT_TOKEN", "не найден"))
print("GITHUB_TOKEN:", os.getenv("GITHUB_TOKEN", "не найден")[:10] + "..." if os.getenv("GITHUB_TOKEN") else "не найден")
print("GITHUB_REPO_OWNER:", os.getenv("GITHUB_REPO_OWNER", "не найден"))
print("====================================")

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

# Сайты для проверки URL (опционально)
ALLOWED_DOMAINS = ["screenrant.com", "cbr.com", "collider.com", "movieweb.com"]

def is_valid_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)

def dispatch_workflow(url: str) -> str:
    """Запускает workflow с URL как input"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    data = {
        "ref": "main",  # твоя default ветка
        "inputs": {"urls": url}
    }
    response = requests.post(url, headers=GITHUB_HEADERS, json=data)
    if response.status_code == 204:
        print("Workflow dispatched successfully")
        return get_latest_run_id()
    else:
        raise Exception(f"Dispatch failed: {response.text}")

def get_latest_run_id() -> str:
    """Получает ID последнего запущенного run"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1"
    response = requests.get(url, headers=GITHUB_HEADERS)
    if response.ok:
        runs = response.json()["workflow_runs"]
        if runs:
            return runs[0]["id"]
    raise Exception("No runs found")

def wait_for_run_completion(run_id: str, timeout=300, interval=10) -> bool:
    """Ждёт завершения run (success or failure)"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        if response.ok:
            status = response.json()["status"]
            conclusion = response.json()["conclusion"]
            if status == "completed":
                print(f"Run completed with {conclusion}")
                return conclusion == "success"
        time.sleep(interval)
    raise TimeoutError("Workflow timeout")

def get_summary_file_url(title: str, pub_date: str) -> str:
    """Генерирует URL для скачивания __groq_summary.txt"""
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip("_")[:100]
    filename = f"{safe_title}__{pub_date}__groq_summary.txt"
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/extracted_articles/{filename}"

async def handle_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    if not is_valid_url(url):
        await update.message.reply_text("Неверный URL. Отправь ссылку на статью с screenrant/cbr/collider/movieweb.")
        return

    try:
        await update.message.reply_text("Запускаю обработку...")
        run_id = dispatch_workflow(url)
        success = wait_for_run_completion(run_id)

        if success:
            # Здесь нужно получить title и pub_date — для простоты предположим, что мы знаем их (или парсим из repo API)
            # В реальности: можно парсить json-отчёт из repo, но для начала используй фиксированные (подставь из лога)
            # Пример: из лога ты знаешь title и date
            # Альтернатива: после run скачать extraction_report.json и взять оттуда
            title = "Marvel Is Officially Rewriting a Major Part of Captain America_s Origin After 64 Years"  # подставь реальный
            pub_date = "2026-02-20"
            file_url = get_summary_file_url(title, pub_date)

            # Скачиваем файл
            response = requests.get(file_url)
            if response.ok:
                with open("temp_summary.txt", "wb") as f:
                    f.write(response.content)
                await update.message.reply_document(document=open("temp_summary.txt", "rb"), caption="Groq-саммари статьи")
                os.remove("temp_summary.txt")
            else:
                await update.message.reply_text("Не удалось скачать саммари.")
        else:
            await update.message.reply_text("Workflow завершился с ошибкой.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.run_polling()

if __name__ == "__main__":
    main()
