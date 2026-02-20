# extract_article.py
import argparse
import sys
import trafilatura
from datetime import datetime
from pathlib import Path
import json

def extract_article(url: str, output_dir: Path):
    """
    Скачивает статью по URL и сохраняет чистый текст в указанную папку.
    Возвращает путь к файлу и метаданные или (None, None) при неудаче.
    """
    print(f"→ Processing: {url}")
    
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print("  Failed to download (possible block / 4xx / 5xx / empty response)")
            return None, None

        # Извлекаем текст + метаданные одним вызовом
        result = trafilatura.extract(
            downloaded,
            with_metadata=True,            # ← вот ключевой параметр
            include_comments=False,
            include_tables=False,
            include_links=False,
            include_formatting=False,
            favor_precision=True,
        )

        if result is None:
            print("  Extraction returned None → fallback mode")
            result = trafilatura.extract(downloaded, no_fallback=False, with_metadata=True)
            if result is None:
                print("  Even fallback failed")
                return None, None

        # result теперь объект Document
        text = result.text
        if not text or len(text.strip()) < 150:
            print("  Text too short after extraction")
            return None, None

        title = result.title or "No title"
        pub_date = result.date or datetime.utcnow().strftime("%Y-%m-%d")

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
        description="Extract article text using trafilatura (GitHub Actions friendly)"
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

    # Сохраняем краткий отчёт в json
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
    
    # Для отладки — выводим версию
    print(f"trafilatura version: {trafilatura.__version__}")
    
    main()
