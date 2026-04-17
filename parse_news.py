# parse_news.py
import feedparser
import json
import hashlib
import os
import requests
from datetime import datetime

# Файлы для хранения
SEEN_FILE = "seen_guids.json"  # Для дублей
OUTPUT_FILE = "news_feed.md"   # Вывод в Markdown для удобства

# Ленты
FEEDS = [
    "https://screenrant.com/feed/",
    "https://cbr.com/feed/",
    "https://collider.com/feed/",
    "https://movieweb.com/feed/",
]

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "1550347468"


def load_seen_guids() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen_guids(guids: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(guids), f, ensure_ascii=False, indent=2)

def normalize_text(text: str) -> str:
    return (text or "").strip().replace("\n\n", "\n").replace("\n", " ")

def get_categories(entry) -> str:
    tags = entry.get("tags", [])
    if tags:
        return ", ".join([tag.get("term", "") for tag in tags if tag.get("term")])
    return "Нет категорий"

def get_date(entry) -> str:
    pub = entry.get("published") or entry.get("updated") or "Не указана"
    try:
        dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        return pub

def format_item(item: dict) -> str:
    return f"""# {item['title']}

{item['categories']}

{item['published']}

{item['link']}

{item['description']}
---------
"""

def send_file_to_bot(filepath: str):
    """Отправляет md-файл боту через Telegram API."""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN не задан, пропускаем отправку")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"news-{date_str}.md"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

    with open(filepath, "rb") as f:
        response = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID},
            files={"document": (filename, f, "text/plain")},
        )

    if response.ok:
        print(f"✅ Файл {filename} отправлен боту")
    else:
        print(f"❌ Ошибка отправки: {response.status_code} {response.text}")

def main():
    seen = load_seen_guids()
    new_items = []

    for url in FEEDS:
        print(f"→ Парсим {url}")
        d = feedparser.parse(url)

        if d.bozo:
            print(f"  ⚠️ Ошибка: {d.bozo_exception}")
            continue

        feed_title = d.feed.get("title", "Без названия")

        for entry in d.entries:
            guid = entry.get("guid") or entry.get("link")
            if not guid:
                continue

            guid_hash = hashlib.md5(guid.encode()).hexdigest()

            if guid_hash in seen:
                continue

            item = {
                "source": feed_title,
                "title": entry.get("title", "(без заголовка)"),
                "link": entry.get("link"),
                "published": get_date(entry),
                "description": normalize_text(entry.get("description") or entry.get("summary")),
                "categories": get_categories(entry),
                "guid_hash": guid_hash,
            }

            new_items.append(item)
            seen.add(guid_hash)

    if new_items:
        print(f"Нашли {len(new_items)} новых статей")

        existing_content = ""
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_content = f.read()

        new_content = "\n".join([format_item(item) for item in new_items])

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(new_content + "\n" + existing_content)

        save_seen_guids(seen)
        print(f"Обновили {OUTPUT_FILE}")

        # Отправляем файл боту на обработку
        send_file_to_bot(OUTPUT_FILE)
    else:
        print("Новых статей нет")

if __name__ == "__main__":
    main()
