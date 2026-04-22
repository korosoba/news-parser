# 📰 news-parser

> Система для сбора новостей о кино и создания тематических дайджестов через AI.

Парсит RSS-ленты → накапливает статьи → по команде создаёт дайджест через Groq (Llama 3.3 70B) и отправляет в Telegram.

---

## Как всё работает

```
RSS-ленты → parse_news.py → news_feed.md → [Telegram] → telegram_bot_webhook.py → Groq AI → digest.txt
```

1. Запускаешь `parse_news.py` — он собирает новые статьи с 4 сайтов и дописывает их в `news_feed.md`
2. Отправляешь `news_feed.md` в Telegram-бот
3. Бот прогоняет статьи через Groq и возвращает готовый дайджест по категориям

---

## Файлы проекта

| Файл | Назначение |
|---|---|
| `parse_news.py` | Парсит RSS-ленты, фильтрует дубли, обновляет `news_feed.md` |
| `telegram_bot_webhook.py` | Основной бот: принимает ссылки и `.md` файлы, общается с Groq |
| `extract_article.py` | CLI-утилита: скачивает текст статьи по URL, опционально делает AI-пересказ |
| `news_feed.md` | Накопленная лента статей (генерируется `parse_news.py`) |
| `seen_guids.json` | Хеши уже обработанных статей — защита от дублей |
| `telegram_bot.py` | Старая версия бота (polling), не используется |
| `Procfile` | Инструкция для Render |
| `requirements.txt` | Python-зависимости |

---

## Источники новостей

- [Screen Rant](https://screenrant.com)
- [CBR](https://cbr.com)
- [Collider](https://collider.com)
- [MovieWeb](https://movieweb.com)

---

## Что умеет Telegram-бот

**Отправь ссылку** → бот извлечёт текст и вернёт краткое резюме на русском (5–7 предложений)

**Отправь `.md` файл** → бот создаст дайджест и вернёт `digest-ДАТА.txt` с категориями:
- 📋 Подборки
- 🎬 Новые фильмы и сериалы
- 🏛 Классика
- 🌟 Персоны

---

## Установка и запуск

### 1. Клонировать репозиторий

```bash
git clone https://github.com/korosoba/news-parser
cd news-parser
pip install -r requirements.txt
```

### 2. Задать переменные окружения

```bash
export TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
export GROQ_API_KEY=ваш_ключ_от_console.groq.com
export RENDER_EXTERNAL_URL=https://ваш-сервис.onrender.com
```

### 3. Обновить ленту новостей

```bash
python parse_news.py
```

### 4. Запустить бот

```bash
python telegram_bot_webhook.py
```

---

## Деплой на Render

Проект настроен для деплоя на [Render](https://render.com).

Переменные окружения задаются в настройках сервиса на Render:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `GROQ_API_KEY` | API-ключ от [console.groq.com](https://console.groq.com) |
| `RENDER_EXTERNAL_URL` | Публичный URL сервиса (Render ставит автоматически) |

---

## Стек

- **Python 3.11+**
- [feedparser](https://feedparser.readthedocs.io) — чтение RSS
- [trafilatura](https://trafilatura.readthedocs.io) — извлечение текста из статей
- [python-telegram-bot](https://python-telegram-bot.org) — Telegram Bot API
- [Flask](https://flask.palletsprojects.com) — веб-сервер для webhook
- [Groq](https://console.groq.com) — Llama 3.3 70B для AI-обработки
