# Telegram Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Telegram bot that lets users optimize resumes by sending job URLs/text, with a Mini App button that opens the Coach — all authenticated via Telegram ID linked to existing Google accounts.

**Architecture:** Separate Python service (aiogram 3.x) talks to existing FastAPI via HTTP using `X-Telegram-User-Id` header. Mini App is the existing Next.js app — after Google OAuth it auto-links `telegram_id` from `window.Telegram.WebApp.initData`.

**Tech Stack:** aiogram 3.x, httpx (already in project), @twa-dev/sdk (frontend), Supabase admin API for session management.

---

### Task 1: DB Migration — add telegram_id to profiles

**Files:**
- Create: `supabase/migrations/009_telegram_id.sql`

**Step 1: Write the migration**

```sql
-- Add telegram_id to profiles for Telegram bot linking
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS telegram_id BIGINT UNIQUE;

CREATE INDEX IF NOT EXISTS idx_profiles_telegram_id ON profiles(telegram_id);
```

**Step 2: Apply migration locally**

```bash
supabase db push
```

Expected: migration applied, `profiles` table has `telegram_id` column.

**Step 3: Commit**

```bash
git add supabase/migrations/009_telegram_id.sql
git commit -m "feat(db): add telegram_id to profiles"
```

---

### Task 2: Backend — Supabase service extensions

**Files:**
- Modify: `src/hr_breaker/services/supabase.py`

**Step 1: Add helper methods at the end of `SupabaseService` class**

After the existing methods, add:

```python
def get_profile_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
    """Get user profile by Telegram ID."""
    try:
        result = (
            self._client.table("profiles")
            .select("*")
            .eq("telegram_id", telegram_id)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        return None

def link_telegram(self, user_id: str, telegram_id: int) -> None:
    """Link a Telegram ID to a user profile."""
    try:
        self._client.table("profiles").update(
            {"telegram_id": telegram_id}
        ).eq("id", user_id).execute()
    except Exception as e:
        raise SupabaseError(f"Failed to link Telegram: {e}") from e

def get_default_cv(self, user_id: str) -> dict[str, Any] | None:
    """Get the user's default CV (most recently uploaded)."""
    try:
        result = (
            self._client.table("cvs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        profile = self.get_profile(user_id)
        if profile and profile.get("default_cv_id"):
            cv = (
                self._client.table("cvs")
                .select("*")
                .eq("id", profile["default_cv_id"])
                .single()
                .execute()
            )
            return cv.data if cv.data else result.data[0]
        return result.data[0]
    except Exception:
        return None

def get_recent_runs(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Get recent optimization runs for a user."""
    try:
        result = (
            self._client.table("optimization_runs")
            .select("id, job_title, job_company, status, created_at")
            .eq("user_id", user_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []
```

**Step 2: Commit**

```bash
git add src/hr_breaker/services/supabase.py
git commit -m "feat(supabase): add telegram helper methods"
```

---

### Task 3: Backend — Telegram auth routes

**Files:**
- Create: `src/hr_breaker/api/routes/telegram.py`
- Modify: `src/hr_breaker/api/routes/__init__.py`
- Modify: `src/hr_breaker/api/main.py`
- Modify: `src/hr_breaker/config.py`

**Step 1: Add `bot_api_key` and `telegram_bot_token` to Settings**

In `src/hr_breaker/config.py`, add to the `Settings` class:

```python
# Telegram bot settings
bot_api_key: str = ""
telegram_bot_token: str = ""
```

In `get_settings()`, add:

```python
bot_api_key=os.getenv("BOT_API_KEY", ""),
telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
```

**Step 2: Create `src/hr_breaker/api/routes/telegram.py`**

```python
"""Telegram bot authentication routes."""

import hashlib
import hmac
import json
import time
from typing import Annotated
from urllib.parse import parse_qsl, unquote

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUser, SupabaseServiceDep
from hr_breaker.config import get_settings, logger

router = APIRouter()


def _validate_init_data(init_data: str) -> dict:
    """
    Validate Telegram Mini App initData signature.
    Returns parsed user dict if valid, raises HTTPException if invalid.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    params = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in initData")

    # Check auth_date not too old (10 minutes)
    auth_date = int(params.get("auth_date", 0))
    if time.time() - auth_date > 600:
        raise HTTPException(status_code=401, detail="initData expired")

    # Build data-check-string
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    # Compute secret key: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256
    ).digest()

    # Compute expected hash
    expected_hash = hmac.new(
        secret_key, data_check.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    user_json = params.get("user", "{}")
    return json.loads(user_json)


class LinkTelegramRequest(BaseModel):
    telegram_id: int


class TelegramSessionRequest(BaseModel):
    init_data: str


@router.post("/link")
async def link_telegram(
    body: LinkTelegramRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Link a Telegram ID to the currently authenticated user."""
    supabase.link_telegram(user_id, body.telegram_id)
    return {"ok": True}


@router.get("/me")
async def get_me_by_telegram(
    x_telegram_user_id: Annotated[str | None, Header()] = None,
    x_bot_api_key: Annotated[str | None, Header()] = None,
    supabase: SupabaseServiceDep = Depends(),
):
    """Get user profile by Telegram ID (bot use only)."""
    settings = get_settings()
    if not x_bot_api_key or x_bot_api_key != settings.bot_api_key:
        raise HTTPException(status_code=401, detail="Invalid bot API key")
    if not x_telegram_user_id:
        raise HTTPException(status_code=400, detail="Missing X-Telegram-User-Id")

    profile = supabase.get_profile_by_telegram_id(int(x_telegram_user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile
```

**Step 3: Register router in `src/hr_breaker/api/routes/__init__.py`**

Add to the imports and `__all__`:

```python
from hr_breaker.api.routes.telegram import router as telegram_router
```

Add `telegram_router` to `__all__`.

**Step 4: Register in `src/hr_breaker/api/main.py`**

```python
from hr_breaker.api.routes import telegram_router
# ...
app.include_router(telegram_router, prefix="/api/auth/telegram", tags=["telegram"])
```

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/telegram.py src/hr_breaker/api/routes/__init__.py src/hr_breaker/api/main.py src/hr_breaker/config.py
git commit -m "feat(api): add Telegram auth routes"
```

---

### Task 4: Bot — project setup

**Files:**
- Create: `telegram_bot/pyproject.toml`
- Create: `telegram_bot/bot/config.py`
- Create: `telegram_bot/bot/main.py`
- Create: `telegram_bot/bot/__init__.py`
- Create: `telegram_bot/bot/services/__init__.py`
- Create: `telegram_bot/bot/services/api_client.py`
- Create: `telegram_bot/bot/handlers/__init__.py`
- Create: `telegram_bot/bot/middlewares/__init__.py`
- Create: `telegram_bot/bot/middlewares/auth.py`

**Step 1: Create `telegram_bot/pyproject.toml`**

```toml
[project]
name = "hr-breaker-bot"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "aiogram>=3.17",
    "httpx>=0.27",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0",
]

[project.scripts]
hr-breaker-bot = "bot.main:main"
```

**Step 2: Create `telegram_bot/bot/config.py`**

```python
"""Bot configuration."""

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class BotSettings(BaseSettings):
    bot_token: str = ""
    bot_api_key: str = ""
    api_url: str = "http://localhost:8000"
    web_app_url: str = "https://app.hrbreaker.com"
    webhook_url: str = ""
    webhook_secret: str = ""

    model_config = {"env_prefix": ""}

    @classmethod
    def from_env(cls) -> "BotSettings":
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            bot_api_key=os.getenv("BOT_API_KEY", ""),
            api_url=os.getenv("API_URL", "http://localhost:8000"),
            web_app_url=os.getenv("WEB_APP_URL", "https://app.hrbreaker.com"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        )


_settings: BotSettings | None = None


def get_bot_settings() -> BotSettings:
    global _settings
    if _settings is None:
        _settings = BotSettings.from_env()
    return _settings
```

**Step 3: Create `telegram_bot/bot/services/api_client.py`**

```python
"""HTTP client for FastAPI backend."""

import httpx
from bot.config import get_bot_settings


class APIClient:
    def __init__(self):
        settings = get_bot_settings()
        self._base_url = settings.api_url
        self._headers = {
            "X-Bot-Api-Key": settings.bot_api_key,
        }

    def _user_headers(self, telegram_id: int) -> dict:
        return {**self._headers, "X-Telegram-User-Id": str(telegram_id)}

    async def get_user(self, telegram_id: int) -> dict | None:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/auth/telegram/me",
                headers=self._user_headers(telegram_id),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    async def get_cvs(self, telegram_id: int) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/cvs",
                headers=self._user_headers(telegram_id),
            )
            r.raise_for_status()
            return r.json()

    async def upload_cv(self, telegram_id: int, filename: str, content: bytes) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/api/cvs/upload",
                headers=self._user_headers(telegram_id),
                files={"file": (filename, content)},
            )
            r.raise_for_status()
            return r.json()

    async def start_optimization(
        self, telegram_id: int, cv_id: str, job_input: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/api/optimize/start",
                headers=self._user_headers(telegram_id),
                json={"cv_id": cv_id, "job_input": job_input},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

    async def get_optimization_status(
        self, telegram_id: int, run_id: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/optimize/{run_id}/status",
                headers=self._user_headers(telegram_id),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def get_optimization_pdf(
        self, telegram_id: int, run_id: str
    ) -> bytes:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/optimize/{run_id}/pdf",
                headers=self._user_headers(telegram_id),
                timeout=30,
            )
            r.raise_for_status()
            return r.content

    async def get_recent_runs(self, telegram_id: int) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/api/optimize?limit=5",
                headers=self._user_headers(telegram_id),
            )
            r.raise_for_status()
            return r.json().get("runs", [])

    async def set_default_cv(self, telegram_id: int, cv_id: str) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{self._base_url}/api/users/profile",
                headers=self._user_headers(telegram_id),
                json={"default_cv_id": cv_id},
            )
            r.raise_for_status()
```

**Step 4: Create `telegram_bot/bot/middlewares/auth.py`**

```python
"""Auth middleware: checks if telegram_id is linked to an account."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

from bot.services.api_client import APIClient


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        client = APIClient()
        user = None
        if isinstance(event, Message) and event.from_user:
            user = await client.get_user(event.from_user.id)
        data["api_client"] = client
        data["backend_user"] = user
        return await handler(event, data)
```

**Step 5: Create `telegram_bot/bot/main.py`**

```python
"""Bot entry point."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import get_bot_settings
from bot.handlers import start, optimize, settings, history
from bot.middlewares.auth import AuthMiddleware

logging.basicConfig(level=logging.INFO)


async def main():
    bot_settings = get_bot_settings()
    bot = Bot(
        token=bot_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.message.middleware(AuthMiddleware())
    dp.include_router(start.router)
    dp.include_router(optimize.router)
    dp.include_router(settings.router)
    dp.include_router(history.router)

    if bot_settings.webhook_url:
        app = web.Application()
        handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        await web.TCPSite(
            web.AppRunner(app), host="0.0.0.0", port=8080
        ).start()
        await asyncio.Event().wait()
    else:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 6: Commit**

```bash
git add telegram_bot/
git commit -m "feat(bot): add project skeleton, config, api client, auth middleware"
```

---

### Task 5: Bot — /start handler

**Files:**
- Create: `telegram_bot/bot/handlers/start.py`

**Step 1: Create `telegram_bot/bot/handlers/start.py`**

```python
"""Start handler — entry point and auth flow."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.config import get_bot_settings

router = Router()


@router.message(CommandStart())
async def start(message: Message, backend_user: dict | None, **kwargs):
    settings = get_bot_settings()

    if backend_user:
        await message.answer(
            f"👋 Welcome back! Send me a job URL or paste a job description "
            f"and I'll optimize your resume.\n\n"
            f"Use /help to see all commands."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔑 Sign in / Register",
                    web_app=WebAppInfo(url=f"{settings.web_app_url}/signin"),
                )
            ]
        ]
    )
    await message.answer(
        "👋 Welcome to HR-Breaker!\n\n"
        "To get started, sign in with your Google account:",
        reply_markup=keyboard,
    )
```

**Step 2: Create `telegram_bot/bot/handlers/__init__.py`**

```python
from bot.handlers import start, optimize, settings, history

__all__ = ["start", "optimize", "settings", "history"]
```

**Step 3: Commit**

```bash
git add telegram_bot/bot/handlers/start.py telegram_bot/bot/handlers/__init__.py
git commit -m "feat(bot): add /start handler with auth Mini App button"
```

---

### Task 6: Bot — optimization handler

**Files:**
- Create: `telegram_bot/bot/handlers/optimize.py`
- Create: `telegram_bot/bot/services/polling.py`

**Step 1: Create `telegram_bot/bot/services/polling.py`**

```python
"""Async polling for optimization status."""

import asyncio
from bot.services.api_client import APIClient


async def poll_until_done(
    client: APIClient, telegram_id: int, run_id: str, timeout: int = 300
) -> dict:
    """Poll optimization status every 4 seconds until done or timeout."""
    elapsed = 0
    while elapsed < timeout:
        status = await client.get_optimization_status(telegram_id, run_id)
        if status["status"] == "completed":
            return status
        if status["status"] == "failed":
            raise RuntimeError(status.get("error", "Optimization failed"))
        await asyncio.sleep(4)
        elapsed += 4
    raise TimeoutError("Optimization timed out")
```

**Step 2: Create `telegram_bot/bot/handlers/optimize.py`**

```python
"""Optimization flow handler."""

import re

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from bot.config import get_bot_settings
from bot.services.api_client import APIClient
from bot.services.polling import poll_until_done

router = Router()

URL_RE = re.compile(r"https?://\S+")
MIN_JOB_TEXT_LEN = 100


def _looks_like_job(text: str) -> bool:
    return bool(URL_RE.search(text)) or len(text) >= MIN_JOB_TEXT_LEN


def _unlinked_keyboard(web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔑 Sign in",
                web_app=WebAppInfo(url=f"{web_app_url}/signin"),
            )]
        ]
    )


def _coach_keyboard(run_id: str, web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎓 Open Coach",
                web_app=WebAppInfo(url=f"{web_app_url}/coach?runId={run_id}"),
            )]
        ]
    )


@router.message(F.text & F.func(_looks_like_job))
async def handle_job_input(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    settings = get_bot_settings()

    if not backend_user:
        await message.answer(
            "Please sign in first to use HR-Breaker:",
            reply_markup=_unlinked_keyboard(settings.web_app_url),
        )
        return

    telegram_id = message.from_user.id
    job_input = message.text

    # Get default CV
    cvs = await api_client.get_cvs(telegram_id)
    if not cvs:
        await message.answer(
            "📎 You don't have a resume on file yet.\n"
            "Please send your resume as a file (PDF, DOCX, or TXT)."
        )
        return

    cv_id = cvs[0]["id"]  # default to first (most recent)
    for cv in cvs:
        if cv.get("is_default"):
            cv_id = cv["id"]
            break

    status_msg = await message.answer("⏳ Optimizing your resume...")

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
    except TimeoutError:
        await status_msg.edit_text(
            "⏱ This is taking longer than usual. "
            "Use /history to download when ready."
        )
    except Exception as e:
        await status_msg.edit_text(
            "❌ Couldn't optimize your resume for this job.\n"
            "Try pasting the job description as text if you sent a URL."
        )


@router.message(F.document)
async def handle_document(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    settings = get_bot_settings()

    if not backend_user:
        await message.answer(
            "Please sign in first:",
            reply_markup=_unlinked_keyboard(settings.web_app_url),
        )
        return

    doc: Document = message.document
    allowed = {"application/pdf", "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

    if doc.mime_type not in allowed:
        await message.answer(
            "❌ Unsupported file type. Please send PDF, DOCX, or TXT (max 10 MB)."
        )
        return

    if doc.file_size > 10 * 1024 * 1024:
        await message.answer("❌ File is too large. Maximum size is 10 MB.")
        return

    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)

    await api_client.upload_cv(
        message.from_user.id, doc.file_name or "resume.pdf", file_bytes.read()
    )
    await message.answer(
        "✅ Resume saved! Now send me a job URL or job description to optimize it."
    )
```

**Step 3: Commit**

```bash
git add telegram_bot/bot/handlers/optimize.py telegram_bot/bot/services/polling.py telegram_bot/bot/services/__init__.py
git commit -m "feat(bot): add optimization handler with CV upload and polling"
```

---

### Task 7: Bot — /settings and /history handlers

**Files:**
- Create: `telegram_bot/bot/handlers/settings.py`
- Create: `telegram_bot/bot/handlers/history.py`

**Step 1: Create `telegram_bot/bot/handlers/settings.py`**

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

    buttons = [
        [InlineKeyboardButton(
            text=f"{'✅ ' if cv.get('is_default') else ''}{cv['filename']}",
            callback_data=f"set_default_cv:{cv['id']}",
        )]
        for cv in cvs
    ]
    await message.answer(
        "Choose your default resume:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
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
    await callback.message.delete()
```

**Step 2: Create `telegram_bot/bot/handlers/history.py`**

```python
"""History handler — /history shows recent optimization runs."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.api_client import APIClient

router = Router()


@router.message(Command("history"))
async def history_cmd(
    message: Message,
    backend_user: dict | None,
    api_client: APIClient,
    **kwargs,
):
    if not backend_user:
        await message.answer("Sign in first with /start.")
        return

    runs = await api_client.get_recent_runs(message.from_user.id)
    if not runs:
        await message.answer("No optimization runs yet. Send a job URL to get started.")
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"📄 {r.get('job_company', '?')} — {r.get('job_title', '?')}",
            callback_data=f"dl_pdf:{r['id']}",
        )]
        for r in runs
    ]
    await message.answer(
        "Your recent resumes:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("dl_pdf:"))
async def download_pdf(
    callback: CallbackQuery,
    api_client: APIClient,
    **kwargs,
):
    run_id = callback.data.split(":", 1)[1]
    await callback.answer("Downloading...")
    try:
        pdf_bytes = await api_client.get_optimization_pdf(callback.from_user.id, run_id)
        await callback.message.answer_document(
            BufferedInputFile(pdf_bytes, filename=f"resume_{run_id[:8]}.pdf"),
        )
    except Exception:
        await callback.message.answer("❌ Couldn't fetch the PDF. Try again later.")
```

**Step 3: Commit**

```bash
git add telegram_bot/bot/handlers/settings.py telegram_bot/bot/handlers/history.py
git commit -m "feat(bot): add /settings and /history handlers"
```

---

### Task 8: Frontend — Mini App SDK + auto-link after OAuth

**Files:**
- Modify: `frontend/package.json` (add `@twa-dev/sdk`)
- Create: `frontend/src/lib/telegram.ts`
- Modify: `frontend/src/app/(auth)/signin/page.tsx`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Install Telegram Web App SDK**

```bash
cd frontend && npm install @twa-dev/sdk
```

**Step 2: Create `frontend/src/lib/telegram.ts`**

```typescript
/**
 * Telegram Mini App helpers.
 * Safe to import on web — returns null when not in Telegram.
 */

export function getTelegramWebApp() {
  if (typeof window === "undefined") return null;
  return (window as any).Telegram?.WebApp ?? null;
}

export function getTelegramUserId(): number | null {
  const twa = getTelegramWebApp();
  if (!twa) return null;
  try {
    const user = JSON.parse(twa.initDataUnsafe?.user ?? "null");
    return user?.id ?? null;
  } catch {
    return null;
  }
}

export function isTelegramMiniApp(): boolean {
  return getTelegramWebApp() !== null;
}
```

**Step 3: Add `linkTelegram` to `frontend/src/lib/api.ts`**

Add this function:

```typescript
export async function linkTelegramId(telegramId: number): Promise<void> {
  await apiFetch("/api/auth/telegram/link", {
    method: "POST",
    body: JSON.stringify({ telegram_id: telegramId }),
  });
}
```

**Step 4: Modify `frontend/src/app/(auth)/signin/page.tsx`**

After successful OAuth callback (after `supabase.auth.getSession()` returns a user), add Telegram auto-link:

Find the place where auth session is confirmed (likely in a `useEffect` watching auth state), and add:

```typescript
import { getTelegramUserId } from "@/lib/telegram";
import { linkTelegramId } from "@/lib/api";

// After successful login:
const telegramId = getTelegramUserId();
if (telegramId) {
  try {
    await linkTelegramId(telegramId);
    // Close Mini App — user is now linked
    (window as any).Telegram?.WebApp?.close();
  } catch {
    // Non-fatal: user is logged in, linking failed silently
  }
}
```

**Step 5: Add Telegram Web App script to `frontend/src/app/layout.tsx`**

In the `<head>` section, add the Telegram script so it loads in Mini App context:

```tsx
<Script
  src="https://telegram.org/js/telegram-web-app.js"
  strategy="beforeInteractive"
/>
```

Import `Script` from `"next/script"`.

**Step 6: Commit**

```bash
cd frontend && git add package.json package-lock.json src/lib/telegram.ts src/lib/api.ts src/app/layout.tsx src/app/\(auth\)/signin/page.tsx
git commit -m "feat(frontend): add Telegram Mini App SDK and auto-link after OAuth"
```

---

### Task 9: Smoke test

**Step 1: Start backend**

```bash
source .venv/bin/activate && uv run uvicorn hr_breaker.api.main:app --port 8000
```

Verify: `GET http://localhost:8000/api/health` → `{"status": "ok"}`

**Step 2: Start bot in polling mode (local)**

```bash
cd telegram_bot && uv run python -m bot.main
```

Expected: bot starts polling with no errors.

**Step 3: Manual checklist**

- [ ] Send `/start` to bot as new user → sign-in button appears
- [ ] Open Mini App → Google OAuth → telegram_id saved (check Supabase `profiles`)
- [ ] Send `/start` again → welcome back message
- [ ] Send a job URL → optimization runs → PDF delivered + Coach button
- [ ] Click Coach button → `/coach?runId=...` opens
- [ ] Send a CV file → "Resume saved"
- [ ] `/settings` → CV list with inline buttons
- [ ] `/history` → recent runs with download buttons

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: Telegram bot + Mini App integration complete"
```
