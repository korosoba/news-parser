# telegram_bot.py
import os
import time
import requests
import json
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# Загружаем переменные из файла (укажи правильное имя)
load_dotenv("korosoba.env")  # или просто load_dotenv() если переименовал в .env

# Отладка загрузки переменных
print("=== Отладка переменных из .env ===")
print("TELEGRAM_BOT_TOKEN:", os.getenv("TELEGRAM_BOT_TOKEN", "не найден"))
print("GITHUB_TOKEN:", os.getenv("GITHUB_TOKEN", "не найден")[:10] + "..." if os.getenv("GITHUB_TOKEN") else "не найден")
print("GITHUB_REPO_OWNER:", os.getenv("GITHUB_REPO_OWNER", "не найден"))
print("GITHUB_REPO_NAME:", os.getenv("GITHUB_REPO_NAME", "не найден"))
print("GITHUB_WORKFLOW_NAME:", os.getenv("GITHUB_WORKFLOW_NAME", "не найден"))
print("TELEGRAM_CHAT_ID:", os.getenv("TELEGRAM_CHAT_ID", "не найден"))
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

ALLOWED_DOMAINS = ["screenrant.com", "cbr.com", "collider.com", "movieweb.com"]

def is_valid_url(url: str) -> bool:
    return any(domain in url.lower() for domain in ALLOWED_DOMAINS)

def dispatch_workflow(article_url: str) -> str:
    """Запускает workflow с URL статьи как input"""
    dispatch_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    
    data = {
        "ref": "main",
        "inputs": {"urls": article_url}
    }
    
    print(f"[dispatch] Отправляем в workflow ссылку: {article_url}")
    print(f"[dispatch] Запрос на: {dispatch_url}")
    print(f"[dispatch] Body: {data}")
    
    response = requests.post(dispatch_url, headers=GITHUB_HEADERS, json=data)
    
    print(f"[dispatch] Ответ GitHub: {response.status_code} {response.text[:200]}")
    
    if response.status_code == 204:
        print("Workflow dispatched successfully")
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
            print(f"[wait] Статус run {run_id}: {status} / conclusion: {conclusion}")
            if status == "completed":
                return conclusion == "success"
        time.sleep(interval)
    raise TimeoutError("Workflow timeout")

async def handle_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    
    if not url.startswith("http"):
        await update.message.reply_text("Это не похоже на ссылку. Отправь URL статьи.")
        return
    
    if "api.github.com" in url:
        await update.message.reply_text("Это служебный URL GitHub, а не статья. Отправь ссылку на новость.")
        return
    
    if not is_valid_url(url):
        await update.message.reply_text("Ссылка должна быть с screenrant.com, cbr.com, collider.com или movieweb.com.")
        return
    
    print(f"[handle_url] Получена ссылка от пользователя: {url}")
    await update.message.reply_text(f"Обрабатываю: {url}")
    
    try:
        await update.message.reply_text("Запускаю обработку... (1–3 минуты)")
        
        run_id = dispatch_workflow(url)
        success = wait_for_run_completion(run_id)
        
        if not success:
            await update.message.reply_text("Workflow завершился с ошибкой. Проверь логи в GitHub Actions.")
            return
        
        # Даём GitHub время на push файлов (увеличил для надёжности)
        await asyncio.sleep(30)
        
        # Получаем список файлов в extracted_articles
        contents_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/extracted_articles?ref=main"
        resp = requests.get(contents_url, headers=GITHUB_HEADERS)
        if not resp.ok:
            raise Exception(f"Не удалось получить список файлов: {resp.status_code} {resp.text}")
        
        files = resp.json()
        
        # Ищем все report.json и сортируем по имени (timestamp в имени: YYYYMMDD_HHMMSS — по убыванию, чтобы взять самый новый)
        report_files = [f for f in files if f["name"].startswith("extraction_report_") and f["name"].endswith(".json")]
        if not report_files:
            raise Exception("Не найден ни один extraction_report.json")
        
        # Сортировка: самый свежий — с самым большим timestamp в имени
        report_files.sort(key=lambda f: f["name"], reverse=True)
        report_file = report_files[0]  # берём первый (самый новый)
        
        print(f"[handle_url] Выбран самый свежий report: {report_file['name']}")
        
        # Скачиваем отчёт
        json_resp = requests.get(report_file["download_url"])
        if not json_resp.ok:
            raise Exception("Не удалось скачать report.json")
        
        reports = json_resp.json()
        if not reports:
            raise Exception("Report пустой")
        
        latest = reports[0]
        summary_info = latest.get("summary", {})
        summary_filename = summary_info.get("summary_file")
        
        if not summary_filename:
            raise Exception("В отчёте нет summary_file (Groq не сработал?)")
        
        # Формируем raw-URL для скачивания
        raw_summary_url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/extracted_articles/{summary_filename}"
        
        # Скачиваем
        summary_resp = requests.get(raw_summary_url)
        if not summary_resp.ok:
            raise Exception(f"Не удалось скачать саммари: {summary_resp.status_code} {summary_resp.text}")
        
        temp_file = "temp_groq_summary.txt"
        with open(temp_file, "wb") as f:
            f.write(summary_resp.content)
        
        await update.message.reply_document(
            document=open(temp_file, "rb"),
            caption=f"Groq-саммари для статьи:\n{url}"
        )
        
        os.remove(temp_file)
        await update.message.reply_text("Готово! Если нужно — присылай следующую ссылку.")
    
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")
        print(f"Полная ошибка: {type(e).__name__}: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("Бот запущен и ожидает сообщений...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
