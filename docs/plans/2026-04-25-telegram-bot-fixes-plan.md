# Telegram Bot Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all P0/P1/P2 bugs in the Telegram bot integration so the optimize-by-URL flow and Mini App linking actually work end-to-end.

**Architecture:** The bot-aware auth (variant A from the design) is already implemented inside `get_current_user` via the `_resolve_bot_user` helper — so the design's "create CurrentUserOrBot" step is already done in spirit. Remaining work is bot-side path corrections, callback middleware fix, typed errors, OAuth state propagation, and minor UX.

**Tech Stack:** FastAPI (Python), aiogram 3.x (Python), Next.js 14 (TypeScript), Supabase, httpx.

**Working directory:** `.worktrees/telegram-bot-fixes` (created from dev). Branch: `feature/telegram-bot-fixes`. All paths below are relative to the worktree root.

---

### Task 0: Setup worktree dependencies

The worktree shares `.git` but has no `.venv` or `node_modules`.

**Step 1: Bootstrap backend Python**

Run:
```bash
uv sync
```

Expected: `.venv/` created, all dependencies installed without errors.

**Step 2: Bootstrap bot Python**

Run:
```bash
cd telegram_bot && uv sync && cd ..
```

Expected: `telegram_bot/.venv/` created.

**Step 3: Bootstrap frontend**

Run:
```bash
cd frontend && npm install && cd ..
```

Expected: `frontend/node_modules/` populated.

**Step 4: Verify backend tests pass on baseline**

Run:
```bash
source .venv/bin/activate && uv run pytest tests/test_access_control.py -v
```

Expected: all tests pass. This baseline validates that the bot-auth dependency in `get_current_user` works correctly before we touch anything.

If any test fails — **stop**, report failures, do not proceed.

**Step 5: No commit** (no source changes).

---

### Task 1: Bot — Fix API paths in `api_client.py`

This is the single largest unblocker. Without this, every bot→backend call 404s.

**Files:**
- Modify: `telegram_bot/bot/services/api_client.py`

**Step 1: Update `start_optimization` path**

In `telegram_bot/bot/services/api_client.py`, change:

```python
# Was:
f"{self._base_url}/api/optimize/start",
# Becomes:
f"{self._base_url}/api/optimize",
```

**Step 2: Update `get_optimization_status` path**

Change:
```python
# Was:
f"{self._base_url}/api/optimize/{run_id}/status",
# Becomes:
f"{self._base_url}/api/optimize/{run_id}",
```

**Step 3: Update `upload_cv` path**

Change:
```python
# Was:
f"{self._base_url}/api/cvs/upload",
# Becomes:
f"{self._base_url}/api/cvs",
```

**Step 4: Update `set_default_cv` path**

Change:
```python
# Was:
f"{self._base_url}/api/users/profile",
# Becomes:
f"{self._base_url}/api/users/me",
```

**Step 5: Verify response shape for `start_optimization`**

The handler reads `run["run_id"]` after `start_optimization`. Check the actual backend response in `src/hr_breaker/api/routes/optimize.py` near line 235 — `OptimizationStartResponse` likely has the field as `run_id`. If it's named differently (e.g. `id`), update the consumer in `telegram_bot/bot/handlers/optimize.py` accordingly. Note the actual field name.

**Step 6: Verify status response shape**

`get_optimization_status` consumers read `status["status"]`, `status.get("error")`, `status.get("job_company")`, `status.get("job_title")`. Verify in `OptimizationStatus` model (line ~312 of optimize.py) that these field names match. Note any drift.

**Step 7: Commit**

```bash
git add telegram_bot/bot/services/api_client.py
git commit -m "fix(bot): correct backend API paths in api_client"
```

---

### Task 2: Bot — Migrate `get_user` to `/api/users/me`

The bot currently calls `GET /api/auth/telegram/me`, which is a redundant duplicate of `GET /api/users/me` (the latter already supports bot auth via the bot headers). We're removing the duplicate in Task 3, so the bot must migrate first.

**Files:**
- Modify: `telegram_bot/bot/services/api_client.py`

**Step 1: Update `get_user` method**

Change the URL:
```python
# Was:
f"{self._base_url}/api/auth/telegram/me",
# Becomes:
f"{self._base_url}/api/users/me",
```

**Step 2: Verify response shape**

`AuthMiddleware` and handlers read `backend_user["default_cv_id"]`, `backend_user["id"]`. Check `src/hr_breaker/api/routes/users.py:29` — the `UserProfile` response model. Confirm both fields exist. If `id` is missing (some endpoints return only profile fields), check what the consumers actually need.

**Step 3: Commit**

```bash
git add telegram_bot/bot/services/api_client.py
git commit -m "fix(bot): use /api/users/me instead of deprecated /api/auth/telegram/me"
```

---

### Task 3: Backend — Remove dead code from `routes/telegram.py`

**Files:**
- Modify: `src/hr_breaker/api/routes/telegram.py`

**Step 1: Remove dead code**

Delete from `src/hr_breaker/api/routes/telegram.py`:

- The class `TelegramSessionRequest` (around line 69)
- The function `_validate_init_data` (around lines 26–62)
- The endpoint `@router.get("/me")` and its handler `get_me_by_telegram` (around lines 145–162)

Also remove now-unused imports: `hashlib`, `hmac`, `json`, `time`, `parse_qsl`, `unquote`.

**Step 2: Run backend tests**

Run:
```bash
source .venv/bin/activate && uv run pytest tests/ -v
```

Expected: all tests pass. If any test referenced `/api/auth/telegram/me` or the dead helpers, it would fail — investigate.

**Step 3: Manually exercise `/api/users/me` with bot headers**

Start backend:
```bash
source .venv/bin/activate && uv run uvicorn hr_breaker.api.main:app --port 8000
```

In another shell, with a real `BOT_API_KEY` and a known linked `telegram_id`:
```bash
curl -i -H "X-Bot-Api-Key: $BOT_API_KEY" -H "X-Telegram-User-Id: <linked_id>" http://localhost:8000/api/users/me
```

Expected: 200 with the user profile JSON. If 404 — telegram_id is not actually linked in DB; pick a real one. If 401 — `BOT_API_KEY` is wrong or empty.

**Step 4: Commit**

```bash
git add src/hr_breaker/api/routes/telegram.py
git commit -m "chore(api): remove dead telegram session/init_data code and redundant /me endpoint"
```

---

### Task 4: Bot — Add typed exceptions to `api_client.py`

**Files:**
- Modify: `telegram_bot/bot/services/api_client.py`

**Step 1: Add exception classes at the top of the file**

After imports, before the `APIClient` class:

```python
class APIError(Exception):
    """Base class for backend API errors."""


class QuotaExceededError(APIError):
    """User has run out of optimization quota (HTTP 402)."""


class JobUnavailableError(APIError):
    """Job posting could not be retrieved or parsed (HTTP 422)."""


class BackendError(APIError):
    """Generic backend or network failure (5xx, network errors)."""
```

**Step 2: Wrap `start_optimization` errors**

Replace the body of `start_optimization` with:

```python
async def start_optimization(
    self, telegram_id: int, cv_id: str, job_input: str
) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/api/optimize",
                headers=self._user_headers(telegram_id),
                json={"cv_id": cv_id, "job_input": job_input},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402:
            raise QuotaExceededError(e.response.text) from e
        if e.response.status_code in (422, 502):
            raise JobUnavailableError(e.response.text) from e
        raise BackendError(f"{e.response.status_code}: {e.response.text}") from e
    except httpx.RequestError as e:
        raise BackendError(f"Network error: {e}") from e
```

**Step 3: Wrap remaining methods**

Apply the same pattern to: `get_user`, `get_cvs`, `upload_cv`, `get_optimization_status`, `get_optimization_pdf`, `get_recent_runs`, `set_default_cv`. For these, only `BackendError` mapping is needed (no 402/422 branches) — except keep `get_user`'s existing 404 → return `None` behavior:

```python
async def get_user(self, telegram_id: int) -> dict | None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/users/me",
                headers=self._user_headers(telegram_id),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise BackendError(f"{e.response.status_code}: {e.response.text}") from e
    except httpx.RequestError as e:
        raise BackendError(f"Network error: {e}") from e
```

`register_signin_message` already swallows exceptions silently — leave it as is, just import `logger` and replace `pass` with `logger.warning(...)` for visibility.

**Step 4: Add module-level logger**

At the top of the file:
```python
import logging
logger = logging.getLogger(__name__)
```

**Step 5: Commit**

```bash
git add telegram_bot/bot/services/api_client.py
git commit -m "feat(bot): add typed exceptions and structured logging to api_client"
```

---

### Task 5: Bot — Apply middleware to callbacks and handle `CallbackQuery`

**Files:**
- Modify: `telegram_bot/bot/middlewares/auth.py`
- Modify: `telegram_bot/bot/main.py`

**Step 1: Update `auth.py` to handle `CallbackQuery`**

Replace the body of `__call__`:

```python
from aiogram.types import CallbackQuery, Message, TelegramObject

class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        client = APIClient()
        user = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user = await client.get_user(event.from_user.id)
        data["api_client"] = client
        data["backend_user"] = user
        return await handler(event, data)
```

**Step 2: Attach middleware to callback queries in `main.py`**

In `telegram_bot/bot/main.py`, replace:

```python
dp.message.middleware(AuthMiddleware())
```

with:

```python
auth_mw = AuthMiddleware()
dp.message.middleware(auth_mw)
dp.callback_query.middleware(auth_mw)
```

**Step 3: Commit**

```bash
git add telegram_bot/bot/middlewares/auth.py telegram_bot/bot/main.py
git commit -m "fix(bot): apply auth middleware to callback queries"
```

---

### Task 6: Bot — Use typed exceptions in `optimize.py`

**Files:**
- Modify: `telegram_bot/bot/handlers/optimize.py`

**Step 1: Add imports**

At the top of `telegram_bot/bot/handlers/optimize.py`:

```python
import logging
from bot.services.api_client import (
    APIClient,
    QuotaExceededError,
    JobUnavailableError,
    BackendError,
)

logger = logging.getLogger(__name__)
```

**Step 2: Replace the bare `except` in `handle_job_input`**

Replace the `try`/`except` block (the one that wraps `start_optimization` through `answer_document`) with:

```python
try:
    run = await api_client.start_optimization(telegram_id, cv_id, job_input)
    run_id = run["run_id"]

    result = await poll_until_done(api_client, telegram_id, run_id)

    pdf_bytes = await api_client.get_optimization_pdf(telegram_id, run_id)

    company = result.get("job_company", "company")
    title = result.get("job_title", "role")
    filename = f"{company}_{title}.pdf".replace(" ", "_")

    await status_msg.delete()
    await message.answer_document(
        BufferedInputFile(pdf_bytes, filename=filename),
        caption=f"✅ Resume optimized for <b>{title}</b> at <b>{company}</b>",
        reply_markup=_coach_keyboard(run_id, settings.web_app_url),
    )
except QuotaExceededError:
    await status_msg.edit_text(
        f"💳 You're out of optimization credits.\n\n"
        f"Top up at {settings.web_app_url}/pricing"
    )
except JobUnavailableError:
    await status_msg.edit_text(
        "❌ Couldn't read the job posting.\n"
        "Try pasting the job description as text instead of a URL."
    )
except TimeoutError:
    await status_msg.edit_text(
        "⏱ This is taking longer than usual. "
        "Use /history to download when ready."
    )
except (BackendError, Exception) as e:
    logger.exception("Optimization failed for telegram_id=%s", telegram_id)
    await status_msg.edit_text(
        "❌ Something went wrong on our side. Please try again in a minute."
    )
```

**Step 3: Replace bare `except` in `handle_document`**

The existing `upload_cv` call has no try/except. Add one:

```python
try:
    await api_client.upload_cv(
        message.from_user.id, doc.file_name or "resume.pdf", file_bytes.read()
    )
    await message.answer(
        "✅ Resume saved! Now send me a job URL or job description to optimize it."
    )
except BackendError:
    logger.exception("CV upload failed")
    await message.answer("❌ Couldn't save your resume. Please try again.")
```

**Step 4: Commit**

```bash
git add telegram_bot/bot/handlers/optimize.py
git commit -m "feat(bot): typed error handling and logging in optimize flow"
```

---

### Task 7: Bot — Add `/help` handler

**Files:**
- Modify: `telegram_bot/bot/handlers/start.py`

**Step 1: Add `/help` handler**

Append to `telegram_bot/bot/handlers/start.py`:

```python
from aiogram.filters import Command

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

**Step 2: Commit**

```bash
git add telegram_bot/bot/handlers/start.py
git commit -m "feat(bot): add /help command"
```

---

### Task 8: Bot — `/settings` checkmark fix and re-render on click

**Files:**
- Modify: `telegram_bot/bot/handlers/settings.py`

**Step 1: Replace the file**

Replace the entire content of `telegram_bot/bot/handlers/settings.py` with:

```python
"""Settings handler — /settings to choose default CV."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.api_client import APIClient

router = Router()


def _build_cv_keyboard(cvs: list[dict], default_cv_id: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅ ' if cv['id'] == default_cv_id else ''}{cv['filename']}",
                callback_data=f"set_default_cv:{cv['id']}",
            )]
            for cv in cvs
        ]
    )


@router.message(Command("settings"))
async def settings_cmd(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    if not backend_user:
        await message.answer("Sign in first with /start.")
        return

    cvs = await api_client.get_cvs(message.from_user.id)
    if not cvs:
        await message.answer("You have no resumes uploaded yet. Send a file to add one.")
        return

    default_cv_id = backend_user.get("default_cv_id")
    await message.answer(
        "Choose your default resume:",
        reply_markup=_build_cv_keyboard(cvs, default_cv_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("set_default_cv:"))
async def set_default_cv(
    callback: CallbackQuery,
    api_client: APIClient,
    **kwargs,
):
    cv_id = callback.data.split(":", 1)[1]
    await api_client.set_default_cv(callback.from_user.id, cv_id)
    await callback.answer("Default resume updated ✅")

    # Re-render with the new checkmark
    cvs = await api_client.get_cvs(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=_build_cv_keyboard(cvs, cv_id),
    )
```

**Step 2: Commit**

```bash
git add telegram_bot/bot/handlers/settings.py
git commit -m "fix(bot): show ✅ on default CV in /settings and rerender on switch"
```

---

### Task 9: Bot — Fallback handler for short text

**Files:**
- Modify: `telegram_bot/bot/handlers/optimize.py`

**Step 1: Append a fallback handler at the end of `optimize.py`**

```python
@router.message(F.text & ~F.text.startswith("/"))
async def fallback_text(message: Message, **kwargs):
    await message.answer(
        "Send me a <b>job URL</b> or paste the full job description "
        "(at least 100 characters).\n\nNeed help? /help"
    )
```

**Step 2: Verify router order in `main.py`**

In `telegram_bot/bot/main.py`, confirm the include order:

```python
dp.include_router(start.router)     # /start, /help
dp.include_router(settings.router)  # /settings
dp.include_router(history.router)   # /history
dp.include_router(optimize.router)  # job URL handler + fallback (LAST)
```

`optimize.router` must come last, otherwise its fallback `F.text & ~F.text.startswith("/")` would absorb messages before `start`/`settings`/`history` get a chance — though the `Command(...)` filters in those routers run before `F.text`, the router order is still important for clarity. Make the order explicit.

**Step 3: Commit**

```bash
git add telegram_bot/bot/handlers/optimize.py telegram_bot/bot/main.py
git commit -m "feat(bot): fallback prompt for non-job text messages"
```

---

### Task 10: Bot — Fix webhook startup in `main.py`

**Files:**
- Modify: `telegram_bot/bot/main.py`

**Step 1: Replace the webhook block**

Replace the existing `if bot_settings.webhook_url:` branch with:

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

**Step 2: Smoke test polling mode**

```bash
cd telegram_bot && uv run python -m bot.main
```

Expected: bot starts, no errors, logs `Run polling for bot @<your_bot>`.

`Ctrl+C` to stop.

**Step 3: Commit**

```bash
git add telegram_bot/bot/main.py
git commit -m "fix(bot): properly set up aiohttp runner for webhook mode"
```

---

### Task 11: Frontend — Update `signInWithGoogle` to accept `redirectTo`

**Files:**
- Modify: `frontend/src/hooks/useAuth.ts`

**Step 1: Read current implementation**

Open `frontend/src/hooks/useAuth.ts:48` and see the current `signInWithGoogle`. It probably calls `supabase.auth.signInWithOAuth({ provider: "google" })` with no options.

**Step 2: Add optional `redirectTo` parameter**

Change the signature:

```typescript
const signInWithGoogle = useCallback(async (redirectTo?: string) => {
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: redirectTo ? { redirectTo } : undefined,
  });
  if (error) throw error;
}, []);
```

(Adapt to whatever the actual current implementation looks like — preserve any existing behavior, only add the optional `redirectTo` parameter forwarded to `options`.)

**Step 3: Run frontend type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no type errors.

**Step 4: Commit**

```bash
git add frontend/src/hooks/useAuth.ts
git commit -m "feat(auth): allow custom redirectTo in signInWithGoogle"
```

---

### Task 12: Frontend — Pass `tg` in OAuth state and read fallbacks on return

**Files:**
- Modify: `frontend/src/app/(auth)/signin/page.tsx`

**Step 1: Update OAuth initiation**

Find the `onClick` handler around line 173. Replace it with:

```typescript
onClick={async () => {
  const tgId = isTelegramMiniApp() ? getTelegramUserId() : null;
  if (tgId) localStorage.setItem(PENDING_TG_ID_KEY, String(tgId));

  const redirectTo = tgId
    ? `${window.location.origin}/signin?tg=${tgId}`
    : `${window.location.origin}/signin`;

  track("signin_started", { method: "google" });
  try {
    await signInWithGoogle(redirectTo);
  } catch (err) {
    track("signin_failed", {
      method: "google",
      error: err instanceof Error ? err.message : String(err),
    });
  }
}}
```

**Step 2: Update post-auth `useEffect` with fallback resolution**

Replace the existing `useEffect` body with:

```typescript
useEffect(() => {
  if (loading || !isAuthenticated) return;

  const fromMiniApp = getTelegramUserId();
  const fromUrl = (() => {
    const v = new URLSearchParams(window.location.search).get("tg");
    return v ? Number(v) : null;
  })();
  const fromStorage = (() => {
    const v = localStorage.getItem(PENDING_TG_ID_KEY);
    return v ? Number(v) : null;
  })();
  const tgId = fromMiniApp ?? fromUrl ?? fromStorage;

  if (tgId && Number.isFinite(tgId)) {
    linkTelegramId(tgId)
      .then(() => {
        localStorage.removeItem(PENDING_TG_ID_KEY);
        window.history.replaceState({}, "", "/signin");
        (window as any).Telegram?.WebApp?.close();
      })
      .catch(() => {
        // Non-fatal: user is logged in even if linking failed
      });
  }
  router.push("/optimize");
}, [isAuthenticated, loading, router]);
```

**Step 3: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

**Step 4: Commit**

```bash
git add frontend/src/app/\(auth\)/signin/page.tsx
git commit -m "feat(auth): preserve telegram_id across OAuth via redirect state with localStorage fallback"
```

---

### Task 13: Smoke test (manual)

This is the only verification that catches integration bugs. Run through the full flow.

**Step 1: Start backend**

```bash
source .venv/bin/activate && uv run uvicorn hr_breaker.api.main:app --port 8000
```

**Step 2: Start frontend**

```bash
cd frontend && npm run dev
```

(Note: Telegram Mini App requires HTTPS. For real Mini App testing you need ngrok or a deployed staging URL. For local web-only sanity checks, `localhost:3000` is fine.)

**Step 3: Start bot in polling mode**

In a third shell:
```bash
cd telegram_bot && uv run python -m bot.main
```

**Step 4: Run the manual checklist**

- [ ] `curl -i -H "X-Bot-Api-Key: $BOT_API_KEY" -H "X-Telegram-User-Id: <linked_id>" http://localhost:8000/api/users/me` → 200 with profile
- [ ] `/start` to bot as new user → "Sign in" button appears
- [ ] Open Mini App (or just `/signin?tg=<your_id>` in browser) → Google OAuth → returns to `/signin?tg=<id>` → DB row in `profiles` has `telegram_id` set → bot's "Sign in" message edits to "✅ You're signed in!"
- [ ] `/start` again → "Welcome back" message
- [ ] Send a real job URL → ⏳ "Optimizing your resume…" → PDF arrives + Coach button
- [ ] Send a deliberately broken URL like `https://example.com/notajob` → "Couldn't read the job posting" message
- [ ] Send `hi` (short text, no URL) → fallback prompt
- [ ] Send a PDF file → "Resume saved!"
- [ ] `/settings` → CV list with ✅ on the current default → click another → ✅ moves
- [ ] `/history` → last 5 runs → click one → PDF downloads
- [ ] `/help` → command list

**Step 5: Final commit**

If anything was tweaked during smoke test, commit it. Otherwise no-op.

```bash
git status
# If clean:
echo "Nothing to commit"
# If dirty:
git add . && git commit -m "fix: smoke test adjustments"
```

---

## Notes for the implementer

- **Don't try to be clever.** Each task above is a specific, mechanical change. If you find yourself wanting to refactor more broadly — stop and resist. Bigger refactors aren't in scope here.
- **Run the existing test suite after Tasks 3 and 4** — those touch backend code that has tests (`test_access_control.py`, `test_editor_api.py`, etc.).
- **Mini App OAuth on iOS** is the most fragile path. If Task 12 doesn't work end-to-end on a real device, the `?tg=` URL approach should still work; localStorage fallback is just extra insurance.
- **`frontend/src/lib/api.ts`** is referenced in design — `linkTelegramId` should already exist (it's used in current signin/page.tsx). Verify on Task 12 step 1.
- **Webhook mode** is not exercised by the smoke test (Step 3 uses polling). For prod cutover, deploy the bot to a host with public HTTPS and set `WEBHOOK_URL` + `WEBHOOK_SECRET` env vars; Telegram will then push updates to `<WEBHOOK_URL>/webhook`.
