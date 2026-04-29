# 📰 news-parser

> Система для сбора новостей о кино и автоматической отправки дайджеста в Telegram.

Парсит RSS-ленты каждые 30 минут → накапливает статьи → каждое утро автоматически отправляет сводку на обработку в [SR_bot](https://github.com/korosoba/SR_bot), который возвращает готовый дайджест через Groq AI.

---

## Как всё работает

```
[каждые 30 мин]   parse.yml → parse_news.py → news_feed.md → коммит в репо
[06:00 МСК]       daily-news.yml → POST /process на SR_bot → Groq AI → дайджест в Telegram
[вручную]         extract-articles.yml → extract_article.py → текст + AI-пересказ
```

---

## GitHub Actions

### `parse.yml` — парсинг RSS каждые 30 минут
- Запускает `parse_news.py`
- Коммитит обновлённые `news_feed.md` и `seen_guids.json` в репо

### `daily-news.yml` — ежедневный дайджест в 06:00 МСК (03:00 UTC)
- Проверяет что `news_feed.md` не пустой
- Отправляет содержимое файла напрямую на эндпоинт `POST /process` сервиса SR_bot на Render
- SR_bot обрабатывает сводку через Groq и присылает дайджест в Telegram
- После отправки сбрасывает `news_feed.md` до пустого состояния и коммитит

> ⚠️ Файл отправляется не через Telegram API, а напрямую на HTTP-эндпоинт бота —
> это важно, так как боты не обрабатывают сообщения от самих себя.

### `extract-articles.yml` — ручное извлечение статей
- Запускается вручную, принимает список URL
- Извлекает текст через trafilatura, делает AI-пересказ через Groq
- Сохраняет результаты в `extracted_articles/` и коммитит

---

## Файлы проекта

| Файл | Назначение |
|---|---|
| `parse_news.py` | Парсит RSS-ленты, фильтрует дубли, обновляет `news_feed.md` |
| `extract_article.py` | CLI-утилита: скачивает текст статьи по URL, делает AI-пересказ |
| `news_feed.md` | Накопленная лента статей (генерируется `parse_news.py`, сбрасывается ежедневно) |
| `seen_guids.json` | Хеши обработанных статей — защита от дублей |
| `requirements.txt` | Python-зависимости |

---

## Источники новостей

- [Screen Rant](https://screenrant.com)
- [CBR](https://cbr.com)
- [Collider](https://collider.com)
- [MovieWeb](https://movieweb.com)

---

## Установка и локальный запуск

```bash
git clone https://github.com/korosoba/news-parser
cd news-parser
pip install -r requirements.txt

python parse_news.py
```

---

## GitHub Secrets

| Secret | Используется в |
|---|---|
| `TELEGRAM_CHAT_ID` | `daily-news.yml` — ID чата куда SR_bot пришлёт дайджест |
| `GROQ_API_KEY` | `extract-articles.yml` — AI-пересказы статей |

---

## Стек

- **Python 3.12**
- [feedparser](https://feedparser.readthedocs.io) — чтение RSS
- [trafilatura](https://trafilatura.readthedocs.io) — извлечение текста из статей
- [Groq](https://console.groq.com) — Llama 4 Scout 17B для AI-пересказов
- [GitHub Actions](https://github.com/features/actions) — автоматизация парсинга и отправки
