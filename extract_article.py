# extract_article.py
import argparse
import sys
import trafilatura
from datetime import datetime
from pathlib import Path
import json

import os

try:
    from groq import Groq
    GROQ_AVAILABLE = True
    print("Groq библиотека установлена и импортирована успешно")
except ImportError:
    GROQ_AVAILABLE = False
    print("Библиотека groq НЕ установлена → саммаризация будет пропущена")

def extract_article(url: str, output_dir: Path):
    """
    Скачивает статью по URL и сохраняет чистый текст + метаданные.
    Совместимо с trafilatura 2.0.0+
    """
    print(f"→ Processing: {url}")
    
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print("  Failed to download (possible block / 4xx / 5xx / empty response)")
            return None, None

        # 1. Метаданные отдельно (возвращает Document или None)
        metadata = trafilatura.extract_metadata(downloaded)
        
        title = getattr(metadata, 'title', "No title") if metadata else "No title"
        pub_date = getattr(metadata, 'date', None)
        if pub_date is None:
            pub_date = datetime.utcnow().strftime("%Y-%m-%d")

        # 2. Чистый текст без метаданных в выводе
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            include_links=False,
            include_formatting=False,
            favor_precision=True,
        )

        if not text or len(text.strip()) < 150:
            print("  Text too short / not found → fallback mode")
            text = trafilatura.extract(downloaded, no_fallback=False)
            if not text or len(text.strip()) < 100:
                print("  Even fallback failed or text too short")
                return None, None

        # Безопасное имя файла
        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in title
        ).strip("_")[:100]

        if not safe_title:
            safe_title = url.split("/")[-1].split("?")[0][:80] or "article"

        filename = f"{safe_title}__{pub_date}.txt"
        out_path = output_dir / filename

        output_dir.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"URL: {url}\n")
            f.write(f"Title: {title}\n")
            f.write(f"Published: {pub_date}\n")
            f.write(f"Extracted: {datetime.utcnow().isoformat()}\n")
            f.write("-" * 70 + "\n\n")
            f.write(text)

        print(f"  Saved → {out_path}")
        print(f"  Text length: {len(text):,} characters")

        # ────────────────────────────────────────────────
        # Groq: полноценный пересказ статьи
        # ────────────────────────────────────────────────
        summary_path = None
        summary_meta = None

        if GROQ_AVAILABLE and os.getenv("GROQ_API_KEY"):
            try:
                client = Groq()

                # Ограничиваем текст, чтобы уложиться в контекст модели
                preview_text = text[:12000].strip()  # ~3000–4000 токенов, безопасно для большинства моделей
                if len(preview_text) < 300:
                    preview_text = text

                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",      # или llama-3.3-70b, mixtral-8x7b-32768, gemma2-27b-it — подбери по цене/качеству
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Ты эксперт по кино и сериалам. "
                                "Прочитай статью и напиши краткий пересказ на русском языке (180–350 слов). "
                                "Сфокусируйся на ключевых идеях, теориях, анализе, историческом контексте, символизме, влиянии. "
                                "Избегай спойлеров к сюжету. Держись близко к тексту. "
                                "Если статья о актёре — подчеркни его роль и карьеру. "
                                "Если подборка — перечисли основные пункты."
                            )
                        },
                        {"role": "user", "content": f"Статья:\n{preview_text}"}
                    ],
                    temperature=0.5,
                    max_tokens=600,
                    top_p=0.9
                )

                summary_text = response.choices[0].message.content.strip()

                # Сохраняем
                summary_filename = f"{safe_title}__{pub_date}__groq_summary.txt"
                summary_path = output_dir / summary_filename

                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(f"URL: {url}\n")
                    f.write(f"Title: {title}\n")
                    f.write(f"Original file: {filename}\n")
                    f.write(f"Model: {response.model}\n")
                    f.write(f"Tokens: {response.usage.total_tokens if hasattr(response.usage, 'total_tokens') else 'N/A'}\n")
                    f.write("-" * 70 + "\n\n")
                    f.write(summary_text)

                print(f" Groq summary saved → {summary_path}")
                print(f" Summary length: {len(summary_text):,} characters")

                summary_meta = {
                    "summary_file": str(summary_filename),
                    "summary_length": len(summary_text),
                    "model": response.model,
                    "tokens": response.usage.total_tokens if hasattr(response.usage, 'total_tokens') else None
                }

            except Exception as e:
                print(f" Groq error: {type(e).__name__}: {str(e)}")
                summary_meta = {"error": str(e)}

        # Добавляем в мета-данные
        meta_dict = {
            "url": url,
            "title": title,
            "published": pub_date,
            "file": str(filename),
            "text_length": len(text),
            "summary": summary_meta or {"summary_file": None}
        }

        return out_path, meta_dict

        return out_path, {
            "url": url,
            "title": title,
            "published": pub_date,
            "file": str(filename),
            "text_length": len(text)
        }

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Extract article text using trafilatura 2.0+ (GitHub Actions friendly)"
    )
    parser.add_argument("urls", nargs="+", help="One or more article URLs")
    parser.add_argument("--output-dir", default="extracted_articles",
                        help="Output directory (will be created if not exists)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    results = []

    for url in args.urls:
        path, meta = extract_article(url, output_dir)
        if meta:
            results.append(meta)

    if results:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"extraction_report_{timestamp}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Report saved: {report_path}")

    print(f"Done. Extracted {len(results)} / {len(args.urls)} articles")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage examples:")
        print("  python extract_article.py https://screenrant.com/article-slug/")
        print("  python extract_article.py url1 url2 url3 --output-dir my_articles")
        sys.exit(1)
    
    print(f"trafilatura version: {trafilatura.__version__}")
    
    main()
