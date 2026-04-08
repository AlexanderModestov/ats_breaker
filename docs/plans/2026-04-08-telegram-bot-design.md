# Telegram Bot Design

## Overview

Telegram-интерфейс для HR-Breaker: пользователь отправляет ссылку на вакансию или описание прямо в бот — получает оптимизированное резюме PDF. Coach доступен через Telegram Mini App (встроенный браузер с нашим Next.js фронтом).

## Architecture

```
┌─────────────────────────────────────────────┐
│              Telegram                        │
│                                              │
│  User ──► Bot (aiogram, Python)              │
│              │                               │
│              └─► "Open Coach" button         │
│                       │                      │
│                       ▼                      │
│              Mini App (Next.js)              │
└──────┬───────────────┬──────────────────────┘
       │ HTTP (bot)    │ HTTPS (mini app)
       ▼               ▼
┌─────────────────────────────────────────────┐
│         FastAPI Backend (существующий)       │
│   + новые эндпоинты: Telegram auth, linking  │
└─────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│  Supabase    │  + колонка telegram_id в profiles
└──────────────┘
```

**Два компонента:**
- **Bot** — отдельный Python сервис (aiogram 3.x), деплоится рядом с FastAPI. Разговаривает с бэком через HTTP, собственной БД нет — всё через существующий API.
- **Mini App** — тот же Next.js фронт, открывается по кнопке внутри Telegram. Добавляем `@twa-dev/sdk` и мобильную адаптацию на `/coach` и `/signin`. Отдельного деплоя не нужно.

## Authentication Flow

### Первый вход (новый пользователь или незалинкованный)

1. Пользователь пишет боту `/start`
2. Бот смотрит: `telegram_id` привязан к аккаунту? → **Нет**
3. Бот отвечает: "Добро пожаловать! Войдите или создайте аккаунт" + кнопка → открывается Mini App на `/signin`
4. Пользователь логинится через Google (тот же flow что на сайте)
5. После успешного OAuth фронт знает `telegram_id` из `window.Telegram.WebApp.initData` → автоматически отправляет `POST /api/auth/telegram/link`
6. Бэк сохраняет `telegram_id` в `profiles`
7. Mini App закрывается, бот приветствует пользователя

Для существующих веб-пользователей — то же самое: открывают Mini App, логинятся через Google, `telegram_id` сохраняется.

### Открытие Mini App (Coach)

Telegram автоматически передаёт `initData` при открытии Mini App — криптографически подписанные данные с `telegram_id`. Бэк валидирует подпись, находит юзера, выдаёт Supabase session token. Фронт инициализирует Supabase с этим токеном — пользователь авторизован без логина.

## Database Migration

```sql
ALTER TABLE profiles ADD COLUMN telegram_id BIGINT UNIQUE;
```

## Backend API Extensions

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/auth/telegram/link` | Сохраняет telegram_id для авторизованного юзера |
| `POST` | `/api/auth/telegram/session` | Mini App присылает initData → возвращает Supabase session token |
| `GET` | `/api/auth/telegram/me` | Бот получает юзера по `X-Telegram-User-Id` header |

**Bot middleware:** все запросы от бота идут с заголовком `X-Telegram-User-Id`. Новый middleware в FastAPI находит юзера по `telegram_id` вместо JWT.

## Optimization Flow

```
User: https://linkedin.com/jobs/view/12345
         (или текст описания вакансии)

Bot:  ⏳ Оптимизирую резюме под вакансию...
         (если CV не загружено → "Пришлите резюме файлом")

Bot:  ✅ Готово! [Software_Engineer_Acme.pdf]

      [🎓 Открыть Coach]
```

**Детали:**
- Бот детектирует URL или текст вакансии автоматически, без команды
- Берёт `default_cv_id` из профиля пользователя; если нет — просит файл, сохраняет как новый CV
- Вызывает существующий `POST /api/optimize`, получает `run_id`
- Поллит `GET /api/optimize/{run_id}` каждые 4 сек до завершения
- Присылает PDF + кнопка "Открыть Coach" → Mini App открывается на `/coach?runId={run_id}`

## Bot Commands

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие / auth flow если не привязан |
| `/settings` | Выбрать резюме по умолчанию (inline кнопки со списком CVs) |
| `/history` | Последние 5 оптимизаций с кнопками скачать PDF |
| `/help` | Список команд |

## Bot Project Structure

```
telegram_bot/
├── bot/
│   ├── main.py           # Запуск, webhook/polling
│   ├── config.py         # BOT_TOKEN, API_URL, WEBHOOK_SECRET
│   ├── handlers/
│   │   ├── start.py      # /start, auth flow
│   │   ├── optimize.py   # Детект URL/текста, polling, отправка PDF
│   │   ├── settings.py   # /settings — выбор CV по умолчанию
│   │   └── history.py    # /history
│   ├── services/
│   │   ├── api_client.py # httpx-клиент к FastAPI
│   │   └── polling.py    # Async polling статуса оптимизации
│   └── middlewares/
│       └── auth.py       # Проверка: telegram_id привязан к аккаунту?
├── pyproject.toml        # aiogram, httpx, pydantic-settings
└── Dockerfile
```

## Deployment

Бот запускается как отдельный контейнер рядом с FastAPI (тот же `docker-compose` / Render). Использует **webhook** в проде (Telegram пушит апдейты на наш URL), polling только локально для разработки.

## Error Handling

| Ситуация | Ответ бота |
|----------|------------|
| Незалинкованный юзер | "Войдите в аккаунт" + кнопка Mini App |
| CV не загружено | "Пришлите резюме файлом (PDF, DOCX, TXT)" |
| Вакансия недоступна | "Не удалось открыть ссылку. Вставьте текст описания вакансии" |
| Оптимизация > 5 мин | "Занимает дольше обычного. Результат придёт когда будет готов" |
| Нет запросов (paywall) | "Запросы закончились. Пополните на сайте: {url}" |
| Неподдерживаемый файл | "Поддерживаются PDF, DOCX, TXT, MD. Максимум 10 МБ" |
