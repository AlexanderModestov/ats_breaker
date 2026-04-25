# Telegram Bot Fixes — Comprehensive Design

## Overview

Текущая реализация Telegram-бота из плана `2026-04-08-telegram-bot-plan.md` имеет несколько критических багов: основной флоу оптимизации не работает (несовпадение API-путей и отсутствие bot-side auth), callback-кнопки падают, OAuth теряет Telegram-контекст. Этот документ — план комплексной починки P0/P1/P2 в одном проходе.

## Problems

### P0 — бот не работает с реальными пользователями

1. **Пути API не совпадают с бэкендом.** `api_client.py` зовёт `/api/optimize/start`, `/api/optimize/{id}/status`, `/api/cvs/upload`, `/api/users/profile`. Реально существуют: `POST /api/optimize`, `GET /api/optimize/{id}`, `POST /api/cvs`, `PATCH /api/users/me`. Все 4 эндпоинта бота возвращают 404.
2. **Авторизация бот→бэкенд отсутствует.** `/api/cvs`, `/api/optimize/*`, `/api/users/*` защищены JWT (`CurrentUser`), а бот шлёт `X-Telegram-User-Id` + `X-Bot-Api-Key`. Эти заголовки никем не читаются — все вызовы пользователя из бота возвращают 401.
3. **Middleware `AuthMiddleware` навешен только на `dp.message`.** Callback-хэндлеры (`set_default_cv`, `dl_pdf`) объявляют `api_client: APIClient` как параметр — при нажатии любой inline-кнопки падает с TypeError.
4. **Webhook-режим в `main.py` не взлетит.** `web.AppRunner(app)` создаётся без `await runner.setup()`, `TCPSite` получает неинициализированный runner.

### P1 — UX дыры

5. **Google OAuth из Mini App теряет Telegram-контекст.** На мобиле OAuth уходит во внешний браузер, возврат — туда же. `getTelegramUserId()` вернёт null, `PENDING_TG_ID_KEY` пишется в localStorage, но никогда не читается. На iOS внешний браузер и in-app webview Telegram не делят localStorage → telegram_id не привязывается.
6. **В `/settings` галочка `✅` рядом с дефолтным CV никогда не показывается** — `cv.is_default` бэкенд не возвращает.
7. **`/help` упоминается в приветствии, но хэндлера нет.**
8. **Все ошибки показываются одним сообщением.** Paywall, недоступная вакансия, упавший бэкенд — одинаковое «❌ Couldn't optimize». Логов нет.

### P2 — полировка

9. Короткий текст без URL (< 100 символов) молча игнорируется — нет fallback-хэндлера.
10. Устаревшие signin-сообщения при логине через веб не чистятся (закрывается бесплатно фиксом #5).

## Architecture Decision: вариант A для bot↔backend auth

Выбран путь **A — двойная auth dependency** вместо первоначально задуманного варианта B (mint JWT по `initData`).

Причина: `initData` живёт только в Mini App. Бот работает с обычными апдейтами Telegram, у него `from_user.id`, но не подписанные initData. Реализация B для бота означала бы дополнительный admin-запрос к Supabase для выпуска JWT, кэширование TTL — лишний слой над тем же доверенным каналом `X-Bot-Api-Key + telegram_id`. Mini App уже работает через обычный Supabase JWT и в endpoint `/session` не нуждается.

## Solution

### Section 1 — Backend: `CurrentUserOrBot` + чистка мёртвого кода

Новая зависимость в `src/hr_breaker/api/deps.py`:

```python
async def get_current_user_or_bot(
    authorization: Annotated[str | None, Header()] = None,
    x_bot_api_key: Annotated[str | None, Header()] = None,
    x_telegram_user_id: Annotated[str | None, Header()] = None,
    supabase: SupabaseServiceDep = ...,
) -> str:
    settings = get_settings()
    # Bot path — checked first
    if x_bot_api_key and x_telegram_user_id:
        if x_bot_api_key != settings.bot_api_key:
            raise HTTPException(401, "Invalid bot API key")
        profile = supabase.get_profile_by_telegram_id(int(x_telegram_user_id))
        if not profile:
            raise HTTPException(404, "Telegram user not linked")
        return profile["id"]
    # User path
    return await get_current_user(authorization, supabase)

CurrentUserOrBot = Annotated[str, Depends(get_current_user_or_bot)]
```

Заменяем `CurrentUser` на `CurrentUserOrBot` только на эндпоинтах, нужных боту:

- `GET /api/cvs`, `POST /api/cvs`
- `POST /api/optimize`, `GET /api/optimize`, `GET /api/optimize/{id}`, `GET /api/optimize/{id}/pdf`
- `GET /api/users/me`, `PATCH /api/users/me`

Остальное (`/coach/*`, `/editor/*`, `/subscription/*`, webhooks) остаётся на `CurrentUser`.

**Чистка `routes/telegram.py`:** удаляем `TelegramSessionRequest`, `_validate_init_data` и эндпоинт `GET /api/auth/telegram/me` — последний дублирует `GET /api/users/me` с bot-заголовками.

**`telegram_bot/bot/services/api_client.py` — правка путей:**

| Было | Стало |
|---|---|
| `POST /api/optimize/start` | `POST /api/optimize` |
| `GET /api/optimize/{id}/status` | `GET /api/optimize/{id}` |
| `POST /api/cvs/upload` | `POST /api/cvs` |
| `PATCH /api/users/profile` | `PATCH /api/users/me` |

`get_user()` тоже мигрирует: вместо `GET /api/auth/telegram/me` теперь `GET /api/users/me` с теми же bot-заголовками.

### Section 2 — Bot middleware на callbacks + типизированные ошибки

В `bot/main.py`:

```python
auth_mw = AuthMiddleware()
dp.message.middleware(auth_mw)
dp.callback_query.middleware(auth_mw)
```

В `bot/middlewares/auth.py`:

```python
from aiogram.types import CallbackQuery, Message, TelegramObject

if isinstance(event, (Message, CallbackQuery)) and event.from_user:
    user = await client.get_user(event.from_user.id)
```

Новая иерархия исключений в `api_client.py`:

```python
class APIError(Exception): ...
class QuotaExceededError(APIError): ...      # HTTP 402
class JobUnavailableError(APIError): ...     # HTTP 422 от /optimize при scrape fail
class BackendError(APIError): ...            # 5xx или сетевые
```

Каждый метод оборачивает `httpx.HTTPStatusError`:

```python
except httpx.HTTPStatusError as e:
    if e.response.status_code == 402: raise QuotaExceededError(...)
    if e.response.status_code in (422, 502): raise JobUnavailableError(...)
    raise BackendError(f"{e.response.status_code}: {e.response.text}")
```

В `optimize.py` ловим типы по отдельности:

| Ошибка | Сообщение |
|---|---|
| `QuotaExceededError` | "Запросы закончились. Пополните на сайте: {url}" + кнопка Mini App на `/pricing` |
| `JobUnavailableError` | "Не удалось открыть ссылку. Вставьте текст вакансии" |
| `TimeoutError` (5 мин) | "Занимает дольше обычного. Результат придёт в /history когда будет готов" |
| `BackendError` / `Exception` | "❌ Временная ошибка. Попробуйте через минуту" + `logger.exception(...)` |

### Section 3 — OAuth-линковка через redirect-state

Передаём `tg_id` в `redirectTo` URL Supabase OAuth — это надёжнее localStorage, который не шарится между in-app webview и внешним браузером на iOS.

В `signin/page.tsx`:

```typescript
const tgId = isTelegramMiniApp() ? getTelegramUserId() : null;
const redirectTo = tgId
  ? `${window.location.origin}/signin?tg=${tgId}`
  : `${window.location.origin}/signin`;
await signInWithGoogle({ redirectTo });
```

В `useAuth.signInWithGoogle` принимаем параметр и пробрасываем в `supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo } })`.

После аутентификации читаем по приоритету:

```typescript
const fromMiniApp = getTelegramUserId();
const fromUrl = Number(new URLSearchParams(location.search).get("tg")) || null;
const fromStorage = Number(localStorage.getItem(PENDING_TG_ID_KEY)) || null;
const tgId = fromMiniApp ?? fromUrl ?? fromStorage;

if (tgId) {
  await linkTelegramId(tgId);
  localStorage.removeItem(PENDING_TG_ID_KEY);
  window.history.replaceState({}, "", "/signin");
  getTelegramWebApp()?.close();
}
router.push("/optimize");
```

**Поток:**
1. Mini App → /signin → `redirectTo=/signin?tg=123` + write localStorage as backup.
2. Google OAuth → внешний браузер → возврат на `/signin?tg=123`.
3. Supabase отрабатывает code exchange → `isAuthenticated = true`.
4. `tgId` берётся из URL → `linkTelegramId` → бэкенд правит "Sign in" сообщение через `pop_pending_signin_message`.
5. В Mini App webview — `WebApp.close()`; во внешнем браузере — redirect на `/optimize`, пользователь возвращается в Telegram руками. Бот к этому моменту уже знает его.

### Section 4 — `/help`, галочка `/settings`, fallback на короткий текст

`/help` хэндлер в `handlers/start.py`:

```python
@router.message(Command("help"))
async def help_cmd(message: Message, **kwargs):
    await message.answer(
        "<b>HR-Breaker</b>\n\n"
        "📎 <b>Send a job URL or description</b> — I'll optimize your default resume\n"
        "📄 <b>Send a resume file</b> (PDF/DOCX/TXT) — saved as your CV\n\n"
        "<b>Commands</b>\n"
        "/start — sign in / welcome\n"
        "/settings — choose default resume\n"
        "/history — last 5 optimizations\n"
        "/help — this message"
    )
```

`/settings` галочка — без правок бэкенда, сравниваем с `backend_user["default_cv_id"]`:

```python
default_cv_id = backend_user.get("default_cv_id")
buttons = [
    [InlineKeyboardButton(
        text=f"{'✅ ' if cv['id'] == default_cv_id else ''}{cv['filename']}",
        callback_data=f"set_default_cv:{cv['id']}",
    )]
    for cv in cvs
]
```

Callback `set_default_cv` — перерисовывает список (галочка едет на новый пункт), не удаляет сообщение:

```python
async def set_default_cv(callback, api_client, backend_user, **kwargs):
    cv_id = callback.data.split(":", 1)[1]
    await api_client.set_default_cv(callback.from_user.id, cv_id)
    await callback.answer("Default resume updated ✅")
    cvs = await api_client.get_cvs(callback.from_user.id)
    buttons = [...]  # та же логика, default = cv_id
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
```

Fallback на короткий текст в `optimize.py` после job-хэндлера:

```python
@router.message(F.text & ~F.text.startswith("/"))
async def fallback_text(message: Message, **kwargs):
    await message.answer(
        "Send me a <b>job URL</b> or paste the full job description "
        "(at least 100 characters).\n\nNeed help? /help"
    )
```

Порядок роутеров в `main.py` критичен: `start.router` раньше `optimize.router`, чтобы fallback не перехватил команды.

### Section 5 — Webhook startup

```python
if bot_settings.webhook_url:
    await bot.set_webhook(
        url=f"{bot_settings.webhook_url}/webhook",
        secret_token=bot_settings.webhook_secret or None,
        drop_pending_updates=True,
    )
    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp, bot=bot,
        secret_token=bot_settings.webhook_secret or None,
    ).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()
    await asyncio.Event().wait()
else:
    await dp.start_polling(bot, drop_pending_updates=True)
```

## Testing

Бот — это I/O-склейка, автотесты дают низкий ROI. Используем ручной smoke-чеклист:

1. `curl -H "X-Bot-Api-Key: ..." -H "X-Telegram-User-Id: 123" http://localhost:8000/api/cvs` → 404 (если не привязан) или список CVs.
2. Polling: `/start` новому → кнопка signin; залинкованному → welcome.
3. Mini App OAuth → возврат на `/signin?tg=...` → "Sign in" в чате превращается в "✅ You're signed in!".
4. URL вакансии → ⏳ → PDF + кнопка Coach.
5. URL мусорной вакансии → "Не удалось открыть ссылку".
6. `/settings` → список CV → клик → галочка переезжает.
7. `/history` → 5 рунов → клик → PDF.
8. Короткое "hi" → fallback с подсказкой.

## Scope mapping

| Issue | Section |
|---|---|
| P0 #1 (paths) | 1 |
| P0 #2 (auth) | 1 |
| P0 #3 (callback middleware) | 2 |
| P0 #4 (webhook) | 5 |
| P1 #5 (OAuth state) | 3 |
| P1 #6 (settings checkmark) | 4 |
| P1 #7 (/help) | 4 |
| P1 #8 (typed errors) | 2 |
| P2 #9 (fallback) | 4 |
| P2 #10 (stale signin) | closed by section 3 |
