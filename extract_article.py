# extract_article.py
import argparse
import sys
import os
import requests
import trafilatura
from datetime import datetime
from pathlib import Path
import json

# ────────────────────────────────────────────────
# Настройки Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-70b-versatile"  # или "llama-3.3-70b-tool-use", "mixtral-8x7b-32768" и т.д.

def get_groq_summary(text: str) -> str | None:
    if not GROQ_API_KEY:
        print("  GROQ_API_KEY не найден в переменных окружения → пересказ пропущен")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    
    prompt = f"""Ты эксперт по кино и сериалам. 
Прочитай текст статьи и сделай качественный, лаконичный пересказ на русском языке (примерно 400–700 символов).
Сохрани ключевые факты, анализ, теории, имена актёров/режиссёров/режиссёра.
Не добавляй ничего от себя, не придумывай. Пиши увлекательно, без спойлеров, если они не критичны.
Текст статьи:
{text[:100000]}"""  # обрезаем, если статья огромная

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.65,
        "max_tokens": 900,
        "top_p": 0.95,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        print(f"  Groq пересказ получен ({len(content)} символов)")
        return content
    except Exception as e:
        print(f"  Groq ошибка: {type(e).__name__} → {e}")
        return None


def extract_article(url: str, output_dir: Path):
    print(f"→ Processing: {url}")
    
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print("  Failed to download")
            return None, None

        metadata = trafilatura.extract_metadata(downloaded)
        title = getattr(metadata, 'title', "No title") if metadata else "No title"
        pub_date = getattr(metadata, 'date', None) or datetime.utcnow().strftime("%Y-%m-%d")

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            include_links=False,
            include_formatting=False,
            favor_precision=True,
        )

        if not text or len(text.strip()) < 150:
            print("  Text too short → fallback")
            text = trafilatura.extract(downloaded, no_fallback=False)
            if not text or len(text.strip()) < 100:
                print("  Even fallback failed")
                return None, None

        # ─── Сохраняем оригинал ───────────────────────────────────────
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip("_")[:100]
        if not safe_title:
            safe_title = url.split("/")[-1].split("?")[0][:80] or "article"

        orig_filename = f"{safe_title}__{pub_date}.txt"
        orig_path = output_dir / orig_filename

        output_dir.mkdir(parents=True, exist_ok=True)

        with open(orig_path, "w", encoding="utf-8") as f:
            f.write(f"URL: {url}\n")
            f.write(f"Title: {title}\n")
            f.write(f"Published: {pub_date}\n")
            f.write(f"Extracted: {datetime.utcnow().isoformat()}\n")
            f.write("-" * 70 + "\n\n")
            f.write(text)

        print(f"  Оригинал сохранён → {orig_path}")

        # ─── Пересказ от Groq ─────────────────────────────────────────
        summary = get_groq_summary(text)
        summary_path = None

        if summary:
            summary_filename = f"{safe_title}__{pub_date}__summary.txt"
            summary_path = output_dir / summary_filename

            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n")
                f.write(f"Title: {title}\n")
                f.write(f"Published: {pub_date}\n")
                f.write(f"Summarized: {datetime.utcnow().isoformat()}\n")
                f.write(f"Model: {GROQ_MODEL}\n")
                f.write("-" * 70 + "\n\n")
                f.write(summary)

            print(f"  Пересказ сохранён → {summary_path}")

        return orig_path, {
            "url": url,
            "title": title,
            "published": pub_date,
            "original_file": str(orig_filename),
            "summary_file": str(summary_path.name) if summary_path else None,
            "text_length": len(text),
            "summary_length": len(summary) if summary else 0
        }

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(description="Extract + Groq summary (GitHub Actions)")
    parser.add_argument("urls", nargs="+", help="URLs")
    parser.add_argument("--output-dir", default="extracted_articles")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    results = []

    for url in args.urls:
        _, meta = extract_article(url, output_dir)
        if meta:
            results.append(meta)

    if results:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report = output_dir / f"report_{ts}.json"
        with open(report, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Отчёт: {report}")

    print(f"Готово. Обработано {len(results)} / {len(args.urls)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Пример:")
        print("  python extract_article.py https://screenrant.com/... ")
        sys.exit(1)
    
    print(f"trafilatura {trafilatura.__version__}")
    main()
