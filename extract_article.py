# extract_article.py
import argparse
import sys
import trafilatura
from datetime import datetime
from pathlib import Path
import json

def extract_article(url: str, output_dir: Path):
    print(f"→ Processing: {url}")
    
    try:
        downloaded = trafilatura.fetch_url(url, decode=True)
        if not downloaded:
            print("  Failed to download (possible block / 4xx / 5xx)")
            return None, None

        # Основной текст
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
            if not text:
                print("  Even fallback failed")
                return None, None

        # Метаданные
        metadata = trafilatura.metadata.extract(downloaded) or {}
        title = metadata.get("title") or "No title"
        pub_date = metadata.get("date") or datetime.utcnow().strftime("%Y-%m-%d")

        # Безопасное имя файла
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip("_")[:100]
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
        return out_path, {"url": url, "title": title, "file": str(filename)}

    except Exception as e:
        print(f"  Error: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(description="Extract article text using trafilatura (GitHub Actions friendly)")
    parser.add_argument("urls", nargs="+", help="One or more article URLs")
    parser.add_argument("--output-dir", default="extracted_articles", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    results = []

    for url in args.urls:
        path, meta = extract_article(url, output_dir)
        if meta:
            results.append(meta)

    # Сохраняем краткий отчёт в json (удобно для последующих шагов)
    if results:
        report_path = output_dir / f"extraction_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Report saved: {report_path}")

    print(f"Done. Extracted {len(results)} / {len(args.urls)} articles")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage (examples):")
        print("  python extract_article.py https://screenrant.com/article-slug/")
        print("  python extract_article.py url1 url2 url3 --output-dir my_articles")
        sys.exit(1)
    main()
