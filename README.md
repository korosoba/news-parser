# 📰 news-parser

> Система для сбора новостей о кино и создания тематических дайджестов через AI.

Парсит RSS-ленты каждые 30 минут → накапливает статьи → каждое утро автоматически отправляет дайджест в Telegram через Groq (Llama 3.3 70B).

---

## Как всё работает

```
[каждые 30 мин]  parse.yml → parse_news.py → news_feed.md → коммит в репо
[каждый день в 06:00 МСК]  daily-news.yml → отправляет news_feed.md боту → бот делает дайджест → сбрасывает файл
[вручную]  extract-articles.yml → extract_article.py → текст + AI-пересказ в extracted_articles/
```

---

## GitHub Actions (автоматизация)

### `parse.yml` — парсинг RSS каждые 30 минут
Запускается автоматически по расписанию (и вручную через workflow_dispatch).
- Устанавливает `feedparser`
- Запускает `parse_news.py`
- Коммитит обновлённые `news_feed.md` и `seen_guids.json` обратно в репо

### `daily-news.yml` — ежедневный отчёт в 06:00 МСК (03:00 UTC)
Запускается автоматически каждый день (и вручную).
- Проверяет, что `news_feed.md` не пустой
- Копирует файл с именем `news-ДАТА.md`
- Отправляет файл в Telegram-бот через Bot API (`sendDocument`)
- Бот получает файл, прогоняет через Groq и возвращает дайджест
- После отправки **сбрасывает** `news_feed.md` до пустого состояния и коммитит

### `extract-articles.yml` — ручное извлечение статей
Запускается только вручную — нужно вставить список URL в поле ввода.
- Запускает `extract_article.py` для каждого URL
- Если задан `GROQ_API_KEY` — делает AI-пересказ каждой статьи
- Сохраняет результаты в папку `extracted_articles/` и коммитит

---

## Файлы проекта

| Файл | Назначение |
|---|---|
| `parse_news.py` | Парсит RSS-ленты, фильтрует дубли, обновляет `news_feed.md` |
| `telegram_bot_webhook.py` | Основной бот: принимает ссылки и `.md` файлы, общается с Groq |
| `extract_article.py` | CLI-утилита: скачивает текст статьи по URL, опционально делает AI-пересказ |
| `news_feed.md` | Накопленная лента статей (генерируется `parse_news.py`, сбрасывается ежедневно) |
| `seen_guids.json` | Хеши уже обработанных статей — защита от дублей |
| `requirements.txt` | Python-зависимости |
| `Procfile` | Инструкция для Render: `web: python telegram_bot_webhook.py` |

---

## Что умеет Telegram-бот

**Отправь ссылку** → бот извлечёт текст и вернёт краткое резюме на русском (5–7 предложений)

**Отправь `.md` файл** → бот создаст дайджест и вернёт `digest-ДАТА.txt` с категориями:
- 📋 Подборки
- 🎬 Новые фильмы и сериалы
- 🏛 Классика
- 🌟 Персоны

Если Groq недоступен — бот автоматически повторяет попытки: первые 4 раза каждые 15 минут, затем каждый час до 20:00 МСК.

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
```

Задать переменные окружения:

```bash
export TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
export GROQ_API_KEY=ваш_ключ_от_console.groq.com
export RENDER_EXTERNAL_URL=https://ваш-сервис.onrender.com
```

Обновить ленту вручную:

```bash
python parse_news.py
```

Запустить бот:

```bash
python telegram_bot_webhook.py
```

---

## Деплой на Render

Бот задеплоен как **web-сервис** на [Render](https://render.com). Переменные окружения задаются в настройках сервиса:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `GROQ_API_KEY` | API-ключ от [console.groq.com](https://console.groq.com) |
| `RENDER_EXTERNAL_URL` | Публичный URL сервиса (Render подставляет автоматически) |

GitHub Secrets для Actions:

| Secret | Используется в |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `daily-news.yml` — отправка файла боту |
| `TELEGRAM_CHAT_ID` | `daily-news.yml` — ID чата для отправки |
| `GROQ_API_KEY` | `extract-articles.yml` — AI-пересказы |

---

## Стек

- **Python 3.12**
- [feedparser](https://feedparser.readthedocs.io) — чтение RSS
- [trafilatura](https://trafilatura.readthedocs.io) — извлечение текста из статей
- [python-telegram-bot](https://python-telegram-bot.org) — Telegram Bot API
- [Flask](https://flask.palletsprojects.com) — веб-сервер для webhook
- [Groq](https://console.groq.com) — Llama 3.3 70B для AI-обработки
- [GitHub Actions](https://github.com/features/actions) — автоматизация парсинга и рассылки
