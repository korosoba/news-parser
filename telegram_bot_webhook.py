import os
import asyncio
import logging
import tempfile
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, request, abort
import trafilatura
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    filters, ContextTypes
)
from groq import Groq

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY не задан!")

groq_client = Groq(api_key=GROQ_API_KEY)

BATCH_SIZE = 50
MSK = timezone(timedelta(hours=3))
RETRY_PHASE_1_INTERVAL = 15   # минут
RETRY_PHASE_1_COUNT = 4       # попыток (первый час)
RETRY_PHASE_2_INTERVAL = 60   # минут
DEADLINE_HOUR_MSK = 20        # до 20:00 МСК

# Flask app
web_app = Flask(__name__)

# Telegram Application
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()


# --- Groq ---

def groq_call(messages: list, max_tokens: int = 1024, temperature: float = 0.5) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# --- Обработка ссылки ---

def fetch_article(url: str):
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(downloaded)


def process_with_groq(article_text: str) -> str:
    prompt = f"""Ты — помощник, который обрабатывает англоязычные статьи.

Твоя задача:
1. Сделай краткое резюме статьи (5-7 предложений), выдели главные мысли
2. Переведи это резюме на русский язык

Отвечай ТОЛЬКО на русском языке. Формат ответа:

📌 Краткое резюме:
[текст резюме на русском]

Статья:
{article_text[:6000]}
"""
    return groq_call(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1024,
    )


# --- Дайджест ---

def parse_articles(md_text: str) -> list[dict]:
    articles = []
    blocks = md_text.split("---------")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        title = lines[0].lstrip("# ").strip()
        tags = lines[1] if len(lines) > 1 else ""
        url = next((l for l in lines if l.startswith("http")), "")
        description = lines[-1] if not lines[-1].startswith("http") else ""
        articles.append({"title": title, "tags": tags, "url": url, "description": description})
    return articles


DIGEST_PROMPT = """Ты — редактор, который сортирует статьи о кино и сериалах.

Вот список статей. Распредели каждую по категориям по правилам ниже.

ПРАВИЛА КАТЕГОРИЗАЦИИ:
- ПРОПУСТИТЬ (не включать): новости, анонсы, игры, техника, аниме, комиксы, статьи об индустрии (сборы, рейтинги, бизнес)
- 📋 ПОДБОРКИ: статьи формата "Лучшие X...", "10 лучших...", рейтинги, списки фильмов/сериалов
- 🎬 НОВЫЕ ФИЛЬМЫ И СЕРИАЛЫ: статьи о фильмах/сериалах вышедших примерно в последние 1-3 года (НЕ рецензии, НЕ подборки)
- 🏛 КЛАССИКА: статьи о фильмах/сериалах вышедших 10 и более лет назад (ключевые слова: "X years later", "classic", "cult", старые названия)
- 🌟 ПЕРСОНЫ: статьи о конкретных актёрах, режиссёрах, других интересных людях

ВАЖНО:
- Обработай ВСЕ статьи из списка, не пропускай ни одну подходящую
- Одна статья может попасть только в одну категорию
- Статьи о персонах (актёрах) включай в ПЕРСОНЫ, даже если они про старый фильм

ФОРМАТ ОТВЕТА — строго такой, каждая категория на новой строке:

📋 ПОДБОРКИ
• [Название статьи](ссылка)

🎬 НОВЫЕ ФИЛЬМЫ И СЕРИАЛЫ
• [Название статьи](ссылка)

🏛 КЛАССИКА
• [Название статьи](ссылка)

🌟 ПЕРСОНЫ
• [Название статьи](ссылка)

Если в категории нет статей — пропусти эту категорию совсем.
Названия статей НЕ переводи.

Вот статьи:
"""


def digest_batch_with_groq(articles: list[dict]) -> str:
    articles_text = ""
    for i, a in enumerate(articles, 1):
        articles_text += f"{i}. {a['title']}\n   Теги: {a['tags']}\n   {a['description']}\n   {a['url']}\n\n"
    return groq_call(
        messages=[{"role": "user", "content": DIGEST_PROMPT + articles_text}],
        temperature=0.3,
        max_tokens=4000,
    )


def merge_digests(batch_results: list[str]) -> str:
    categories = {
        "📋 ПОДБОРКИ": [],
        "🎬 НОВЫЕ ФИЛЬМЫ И СЕРИАЛЫ": [],
        "🏛 КЛАССИКА": [],
        "🌟 ПЕРСОНЫ": [],
    }
    current_cat = None
    for result in batch_results:
        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line in categories:
                current_cat = line
            elif line.startswith("•") and current_cat:
                if line not in categories[current_cat]:
                    categories[current_cat].append(line)
    parts = []
    for cat, items in categories.items():
        if items:
            parts.append(cat)
            parts.extend(items)
            parts.append("")
    return "\n".join(parts).strip()


def digest_with_groq(articles: list[dict]) -> tuple[str, int]:
    batches = [articles[i:i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    batch_results = []
    for i, batch in enumerate(batches):
        logging.info(f"Обрабатываю батч {i+1}/{len(batches)} ({len(batch)} статей)")
        batch_results.append(digest_batch_with_groq(batch))
    return merge_digests(batch_results), len(batches)


def is_before_deadline() -> bool:
    return datetime.now(MSK).hour < DEADLINE_HOUR_MSK


async def process_digest_with_retry(bot, chat_id: str, md_text: str, date_str: str, status_msg):
    articles = parse_articles(md_text)
    if not articles:
        await status_msg.edit_text("❌ Не удалось найти статьи в файле.")
        return

    n_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE
    attempt = 0

    while True:
        attempt += 1
        now_msk = datetime.now(MSK).strftime("%H:%M МСК")
        logging.info(f"Попытка #{attempt} обработки дайджеста в {now_msk}")

        try:
            await status_msg.edit_text(
                f"🤖 Попытка #{attempt}: обрабатываю {len(articles)} статей через Groq ({n_batches} запроса)..."
            )
            result, n_batches_done = digest_with_groq(articles)

            result_filename = f"digest-{date_str}.txt"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as out:
                out.write(result)
                out_path = out.name

            await status_msg.delete()
            await bot.send_document(
                chat_id=chat_id,
                document=open(out_path, "rb"),
                filename=result_filename,
                caption=f"✅ Дайджест за {date_str} готов — {len(articles)} статей (попытка #{attempt})",
            )
            os.unlink(out_path)
            return

        except Exception as e:
            logging.warning(f"Попытка #{attempt} не удалась: {e}")

            pause_minutes = RETRY_PHASE_1_INTERVAL if attempt <= RETRY_PHASE_1_COUNT else RETRY_PHASE_2_INTERVAL
            next_try_msk = datetime.now(MSK) + timedelta(minutes=pause_minutes)

            if not is_before_deadline() or next_try_msk.hour >= DEADLINE_HOUR_MSK:
                await status_msg.edit_text(
                    f"❌ Groq недоступен весь день. Дайджест за {date_str} не удалось получить.\n"
                    f"Последняя попытка: {now_msk}.\nОшибка: {str(e)[:200]}"
                )
                return

            await status_msg.edit_text(
                f"⚠️ Попытка #{attempt} не удалась ({now_msk})\n"
                f"Следующая попытка через {pause_minutes} мин."
            )
            await asyncio.sleep(pause_minutes * 60)


# --- Handlers ---

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text(
            "👋 Привет! Отправь ссылку на статью — сделаю краткое резюме на русском.\n"
            "Или отправь md-файл для обработки дайджеста."
        )
        return

    status_msg = await update.message.reply_text("⏳ Читаю статью...")
    article_text = fetch_article(url)

    if not article_text:
        await status_msg.edit_text("❌ Не удалось извлечь текст. Попробуй другую ссылку.")
        return

    await status_msg.edit_text("🤖 Обрабатываю через Groq...")

    # Retry: 6 попыток с паузой 10 секунд = 1 минута
    last_error = None
    for attempt in range(1, 7):
        try:
            result = process_with_groq(article_text)
            await status_msg.edit_text(result)
            return
        except Exception as e:
            last_error = e
            logging.warning(f"Groq попытка {attempt}/6 не удалась: {e}")
            if attempt < 6:
                await status_msg.edit_text(f"⏳ Попытка {attempt}/6 не удалась, повторяю через 10 сек...")
                await asyncio.sleep(10)

    await status_msg.edit_text(
        f"❌ Groq недоступен — все 6 попыток за минуту не удались.\n"
        f"Попробуй отправить ссылку позже.\n"
        f"Ошибка: {str(last_error)[:200]}"
    )


async def handle_digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📎 Отправь мне md-файл с дайджестом.")


async def handle_digest_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document

    if not doc.file_name.endswith(".md"):
        await update.message.reply_text("❌ Нужен файл формата .md")
        return

    status_msg = await update.message.reply_text("⏳ Читаю файл...")

    tg_file = await context.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        await tg_file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    with open(tmp_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    os.unlink(tmp_path)

    date_str = doc.file_name.replace("news-", "").replace(".md", "")

    asyncio.create_task(
        process_digest_with_retry(
            bot=context.bot,
            chat_id=str(update.message.chat_id),
            md_text=md_text,
            date_str=date_str,
            status_msg=status_msg,
        )
    )


application.add_handler(CommandHandler("digest", handle_digest_command))
application.add_handler(MessageHandler(filters.Document.MimeType("text/plain"), handle_digest_file))
application.add_handler(MessageHandler(filters.Document.FileExtension("md"), handle_digest_file))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))


# --- Flask routes ---

@web_app.route("/", methods=["GET", "HEAD"])
def health():
    return "Bot is alive 🚀", 200


@web_app.route("/webhook", methods=["POST"])
async def webhook():
    if request.headers.get("content-type") == "application/json":
        json_data = request.get_json(silent=True)
        if json_data:
            logging.info(f"Получен update от Telegram: {json_data}")
            update = Update.de_json(json_data, application.bot)
            if update:
                asyncio.create_task(application.process_update(update))
            else:
                logging.warning("Не удалось десериализовать update")
        else:
            logging.warning("Пустой JSON в запросе")
        return "ok", 200
    logging.warning("Неверный content-type")
    abort(403)


# --- Инициализация ---

async def init_app():
    await application.initialize()
    await application.start()

    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        raise RuntimeError("RENDER_EXTERNAL_URL не найден!")

    webhook_url = f"{render_url}/webhook"
    await application.bot.delete_webhook(drop_pending_updates=True)
    success = await application.bot.set_webhook(webhook_url)
    if success:
        logging.info(f"Webhook успешно установлен: {webhook_url}")
    else:
        logging.error("Не удалось установить webhook!")


loop = asyncio.get_event_loop()
loop.run_until_complete(init_app())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port, debug=False, threaded=False)
