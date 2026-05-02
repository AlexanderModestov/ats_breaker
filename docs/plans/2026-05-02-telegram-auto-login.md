# Telegram Mini App Auto-Login Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mini App opens (`/coach`, `/optimize`, any `(protected)` page) auto-authenticate via signed `Telegram.WebApp.initData` when `telegram_id` is already linked — no Google OAuth on subsequent opens.

**Architecture:** New backend endpoint `POST /api/auth/telegram/exchange` validates HMAC-signed initData, looks up the linked Supabase user, and returns a magic-link `token_hash`. New frontend hook `useTelegramAutoLogin` posts initData on mount and calls `verifyOtp` to set the Supabase session. ProtectedLayout gates its `/signin` redirect on the auto-login attempt.

**Tech Stack:** FastAPI + Supabase Admin API (Python `gotrue`), Next.js 14 + Supabase JS client, Aiogram (unchanged).

**Reference design:** `docs/plans/2026-05-02-telegram-auto-login-design.md`.

---

## Task 1: Add `generate_magiclink` to SupabaseService

**Files:**
- Modify: `src/hr_breaker/services/supabase.py` (add method near `link_telegram`)
- Test: `tests/test_supabase_magiclink.py` (new)

**Step 1: Verify the admin API is reachable**

Run a one-off Python check (project venv):
```bash
python -c "from supabase import create_client; import os; c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY']); print(type(c.auth.admin.generate_link))"
```
Expected: `<class 'method'>` (or similar). If `AttributeError`, the installed `supabase`/`gotrue` is too old — bump it before continuing.

**Step 2: Write the failing test**

Create `tests/test_supabase_magiclink.py`:

```python
"""Tests for SupabaseService.generate_magiclink."""

from unittest.mock import MagicMock, patch

import pytest

from hr_breaker.services.supabase import SupabaseError, SupabaseService


@pytest.fixture
def service():
    with patch("hr_breaker.services.supabase.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        svc = SupabaseService()
    return svc


def test_generate_magiclink_returns_token_hash(service):
    response = MagicMock()
    response.properties.hashed_token = "abc123"
    service._client.auth.admin.generate_link = MagicMock(return_value=response)

    token = service.generate_magiclink("user@example.com")

    assert token == "abc123"
    service._client.auth.admin.generate_link.assert_called_once_with(
        {"type": "magiclink", "email": "user@example.com"}
    )


def test_generate_magiclink_raises_on_admin_failure(service):
    service._client.auth.admin.generate_link = MagicMock(
        side_effect=Exception("admin call failed")
    )

    with pytest.raises(SupabaseError):
        service.generate_magiclink("user@example.com")
```

**Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_supabase_magiclink.py -v`
Expected: FAIL — `AttributeError: 'SupabaseService' object has no attribute 'generate_magiclink'`.

**Step 4: Implement the method**

Append to `src/hr_breaker/services/supabase.py` near `link_telegram` (around line 553):

```python
def generate_magiclink(self, email: str) -> str:
    """Generate a Supabase magic-link token_hash for the given email.

    The frontend exchanges this hash via ``supabase.auth.verifyOtp`` to set
    a real Supabase session. Used for trusted server-side login (e.g. after
    validating Telegram WebApp initData).
    """
    try:
        response = self._client.auth.admin.generate_link(
            {"type": "magiclink", "email": email}
        )
        return response.properties.hashed_token
    except Exception as e:
        logger.error(f"Failed to generate magic link: {e}")
        raise SupabaseError(f"Failed to generate magic link: {e}") from e
```

**Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_supabase_magiclink.py -v`
Expected: PASS (2 passed).

**Step 6: Commit**

```bash
git add src/hr_breaker/services/supabase.py tests/test_supabase_magiclink.py
git commit -m "feat(supabase): add generate_magiclink helper for Telegram auto-login"
```

---

## Task 2: Add Telegram initData HMAC validator

**Files:**
- Create: `src/hr_breaker/api/auth_telegram.py`
- Test: `tests/test_telegram_initdata.py` (new)

A pure helper module — no FastAPI, easy to unit-test.

**Step 1: Write the failing test**

Create `tests/test_telegram_initdata.py`:

```python
"""Tests for Telegram WebApp initData validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from hr_breaker.api.auth_telegram import (
    InitDataError,
    parse_and_validate_init_data,
)

BOT_TOKEN = "test-bot-token-1234567890"


def _sign(params: dict) -> str:
    """Build a Telegram-signed initData query string for tests."""
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    h = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode({**params, "hash": h})


def test_valid_init_data_returns_telegram_id():
    user = json.dumps({"id": 12345, "first_name": "Test"})
    init_data = _sign({"auth_date": str(int(time.time())), "user": user})

    result = parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)

    assert result.telegram_id == 12345


def test_invalid_hash_raises():
    user = json.dumps({"id": 12345})
    init_data = _sign({"auth_date": str(int(time.time())), "user": user})
    tampered = init_data.replace("12345", "99999")

    with pytest.raises(InitDataError, match="signature"):
        parse_and_validate_init_data(tampered, BOT_TOKEN, max_age_seconds=3600)


def test_expired_init_data_raises():
    user = json.dumps({"id": 12345})
    old_ts = str(int(time.time()) - 7200)  # 2h ago
    init_data = _sign({"auth_date": old_ts, "user": user})

    with pytest.raises(InitDataError, match="expired"):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)


def test_missing_hash_raises():
    init_data = urlencode({"auth_date": str(int(time.time())), "user": "{}"})

    with pytest.raises(InitDataError, match="hash"):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)


def test_missing_user_raises():
    init_data = _sign({"auth_date": str(int(time.time()))})

    with pytest.raises(InitDataError, match="user"):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=3600)
```

**Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_telegram_initdata.py -v`
Expected: FAIL — `ModuleNotFoundError: hr_breaker.api.auth_telegram`.

**Step 3: Implement the validator**

Create `src/hr_breaker/api/auth_telegram.py`:

```python
"""Telegram WebApp initData validation per the official spec.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """Raised when initData is malformed, expired, or has an invalid signature."""


@dataclass
class ValidatedInitData:
    telegram_id: int


def parse_and_validate_init_data(
    init_data: str, bot_token: str, max_age_seconds: int
) -> ValidatedInitData:
    """Parse a Telegram WebApp initData query string and verify its HMAC.

    Raises ``InitDataError`` for any failure mode. On success returns the
    extracted Telegram user id.
    """
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("Missing hash")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    expected = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("Invalid Telegram signature")

    auth_date_str = pairs.get("auth_date")
    if not auth_date_str:
        raise InitDataError("Missing auth_date")
    try:
        auth_date = int(auth_date_str)
    except ValueError as e:
        raise InitDataError("Invalid auth_date") from e

    if int(time.time()) - auth_date > max_age_seconds:
        raise InitDataError("initData expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataError("Missing user field")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise InitDataError("Malformed user field") from e

    telegram_id = user.get("id")
    if not isinstance(telegram_id, int):
        raise InitDataError("Missing user.id")

    return ValidatedInitData(telegram_id=telegram_id)
```

**Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_telegram_initdata.py -v`
Expected: PASS (5 passed).

**Step 5: Commit**

```bash
git add src/hr_breaker/api/auth_telegram.py tests/test_telegram_initdata.py
git commit -m "feat(api): add Telegram WebApp initData validator"
```

---

## Task 3: Add `POST /api/auth/telegram/exchange` endpoint

**Files:**
- Modify: `src/hr_breaker/api/routes/telegram.py`
- Test: `tests/test_telegram_exchange.py` (new)

**Step 1: Write the failing test**

Create `tests/test_telegram_exchange.py`:

```python
"""Tests for POST /api/auth/telegram/exchange."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.main import app
from hr_breaker.api.deps import get_supabase_service

BOT_TOKEN = "test-bot-token-1234567890"


def _sign(params: dict, token: str = BOT_TOKEN) -> str:
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    with patch("hr_breaker.api.routes.telegram.get_settings") as mock_settings:
        mock_settings.return_value.telegram_bot_token = BOT_TOKEN
        yield TestClient(app)
    app.dependency_overrides.clear()


def _valid_init_data(telegram_id: int = 12345) -> str:
    return _sign({
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": telegram_id, "first_name": "T"}),
    })


def test_exchange_success_returns_token_hash(client, fake_supabase):
    fake_supabase.get_profile_by_telegram_id.return_value = {
        "id": "user-uuid",
        "email": "user@example.com",
    }
    fake_supabase.generate_magiclink.return_value = "tok_abc"

    r = client.post(
        "/api/auth/telegram/exchange",
        json={"init_data": _valid_init_data()},
    )

    assert r.status_code == 200
    assert r.json() == {"token_hash": "tok_abc", "email": "user@example.com"}
    fake_supabase.generate_magiclink.assert_called_once_with("user@example.com")


def test_exchange_invalid_signature_returns_401(client):
    bad = _sign({"auth_date": str(int(time.time())), "user": "{}"}, token="WRONG")
    r = client.post("/api/auth/telegram/exchange", json={"init_data": bad})
    assert r.status_code == 401


def test_exchange_expired_returns_401(client):
    expired = _sign({
        "auth_date": str(int(time.time()) - 7200),
        "user": json.dumps({"id": 1}),
    })
    r = client.post("/api/auth/telegram/exchange", json={"init_data": expired})
    assert r.status_code == 401


def test_exchange_unlinked_returns_404(client, fake_supabase):
    fake_supabase.get_profile_by_telegram_id.return_value = None
    r = client.post(
        "/api/auth/telegram/exchange",
        json={"init_data": _valid_init_data()},
    )
    assert r.status_code == 404


def test_exchange_no_email_returns_409(client, fake_supabase):
    fake_supabase.get_profile_by_telegram_id.return_value = {
        "id": "user-uuid",
        "email": None,
    }
    r = client.post(
        "/api/auth/telegram/exchange",
        json={"init_data": _valid_init_data()},
    )
    assert r.status_code == 409
```

**Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_telegram_exchange.py -v`
Expected: FAIL — endpoint returns 404 (route doesn't exist yet).

**Step 3: Implement the endpoint**

Edit `src/hr_breaker/api/routes/telegram.py`. Add imports at top:

```python
from hr_breaker.api.auth_telegram import (
    InitDataError,
    parse_and_validate_init_data,
)
```

Add a new request model alongside `LinkTelegramRequest`:

```python
class ExchangeRequest(BaseModel):
    init_data: str


INIT_DATA_MAX_AGE_SECONDS = 3600
```

Add the endpoint at the end of the file:

```python
@router.post("/exchange")
async def exchange_init_data(
    body: ExchangeRequest,
    supabase: SupabaseServiceDep,
):
    """Exchange a signed Telegram WebApp initData payload for a Supabase
    magic-link token_hash. Used by the Mini App to silently re-authenticate
    a previously-linked user without re-running Google OAuth.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(500, "Server is missing telegram_bot_token")

    try:
        validated = parse_and_validate_init_data(
            body.init_data,
            settings.telegram_bot_token,
            max_age_seconds=INIT_DATA_MAX_AGE_SECONDS,
        )
    except InitDataError as e:
        raise HTTPException(401, str(e)) from e

    profile = supabase.get_profile_by_telegram_id(validated.telegram_id)
    if not profile:
        raise HTTPException(404, "Telegram user not linked")

    email = profile.get("email")
    if not email:
        raise HTTPException(409, "Profile has no email")

    token_hash = supabase.generate_magiclink(email)
    return {"token_hash": token_hash, "email": email}
```

**Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_telegram_exchange.py -v`
Expected: PASS (5 passed).

**Step 5: Run the full backend test suite to ensure nothing regressed**

Run: `pytest tests/ -x`
Expected: all green. If anything fails, investigate before continuing.

**Step 6: Commit**

```bash
git add src/hr_breaker/api/routes/telegram.py tests/test_telegram_exchange.py
git commit -m "feat(api): POST /api/auth/telegram/exchange for Mini App auto-login"
```

---

## Task 4: Add `exchangeTelegramInitData` to frontend api client

**Files:**
- Modify: `frontend/src/lib/api.ts`

This is a tiny addition. No frontend tests in this repo — verified manually in Task 6.

**Step 1: Add the function**

Insert after `linkTelegramId` in `frontend/src/lib/api.ts` (around line 321):

```ts
export async function exchangeTelegramInitData(
  initData: string
): Promise<{ token_hash: string; email: string }> {
  const response = await fetch(`${API_BASE}/auth/telegram/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: initData }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof body?.detail === "string" ? body.detail : `Exchange failed: ${response.status}`,
      response.status,
      body?.detail,
    );
  }
  return response.json();
}
```

Note: this call is **unauthenticated** (no Supabase JWT). HMAC inside `init_data` IS the auth, so do not use `fetchWithAuth`.

**Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): add exchangeTelegramInitData API client"
```

---

## Task 5: Add `useTelegramAutoLogin` hook + ProtectedLayout integration

**Files:**
- Create: `frontend/src/hooks/useTelegramAutoLogin.ts`
- Modify: `frontend/src/app/(protected)/layout.tsx`

**Step 1: Create the hook**

Create `frontend/src/hooks/useTelegramAutoLogin.ts`:

```ts
"use client";

import { useEffect, useState } from "react";
import { getSupabaseClient } from "@/lib/supabase";
import { isTelegramMiniApp, getTelegramWebApp } from "@/lib/telegram";
import { exchangeTelegramInitData } from "@/lib/api";
import { useAuth } from "./useAuth";

const TRIED_KEY = "tg_auto_login_tried";

/**
 * In a Telegram Mini App, if the user is not signed in but their telegram_id
 * is already linked to a Supabase account, exchange the signed initData for a
 * magic-link token_hash and complete sign-in via verifyOtp. Silent fallback to
 * regular /signin (Google OAuth) on any failure or for unlinked users.
 */
export function useTelegramAutoLogin(): { attempting: boolean } {
  const { isAuthenticated, loading } = useAuth();
  const [attempting, setAttempting] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    if (!isTelegramMiniApp()) return false;
    if (sessionStorage.getItem(TRIED_KEY) === "1") return false;
    return true;
  });

  useEffect(() => {
    if (loading) return;
    if (isAuthenticated) {
      setAttempting(false);
      return;
    }
    if (!isTelegramMiniApp()) {
      setAttempting(false);
      return;
    }
    if (sessionStorage.getItem(TRIED_KEY) === "1") {
      setAttempting(false);
      return;
    }

    const initData = getTelegramWebApp()?.initData;
    if (!initData) {
      sessionStorage.setItem(TRIED_KEY, "1");
      setAttempting(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const { token_hash, email } = await exchangeTelegramInitData(initData);
        const supabase = getSupabaseClient();
        await supabase.auth.verifyOtp({
          token_hash,
          type: "magiclink",
          email,
        });
        // useAuth's onAuthStateChange will pick up the new session.
      } catch {
        // Silent fallback: ProtectedLayout will redirect to /signin.
      } finally {
        if (!cancelled) {
          sessionStorage.setItem(TRIED_KEY, "1");
          setAttempting(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loading, isAuthenticated]);

  return { attempting };
}
```

**Step 2: Update ProtectedLayout**

Edit `frontend/src/app/(protected)/layout.tsx`. Replace the whole body:

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useLinkTelegram } from "@/hooks/useLinkTelegram";
import { useTelegramAutoLogin } from "@/hooks/useTelegramAutoLogin";
import { Navbar } from "@/components/Navbar";
import { motion } from "framer-motion";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, loading } = useAuth();
  const { attempting } = useTelegramAutoLogin();

  useLinkTelegram();

  useEffect(() => {
    if (!loading && !attempting && !isAuthenticated) {
      router.push("/signin");
    }
  }, [isAuthenticated, loading, attempting, router]);

  if (loading || attempting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center gap-4"
        >
          <div className="relative">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
          </div>
          <p className="text-sm text-muted-foreground">Loading...</p>
        </motion.div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <motion.main
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8"
      >
        {children}
      </motion.main>
    </div>
  );
}
```

The single substantive change: `attempting` is part of the loading gate AND the redirect guard. The spinner JSX is duplicated for both paths but matches the existing one — keeps the diff minimal.

**Step 3: Verify type-check + build**

Run:
```bash
cd frontend
npx tsc --noEmit
npx next build
```
Expected: no type errors, build succeeds.

**Step 4: Commit**

```bash
git add frontend/src/hooks/useTelegramAutoLogin.ts frontend/src/app/(protected)/layout.tsx
git commit -m "feat(frontend): auto-login Mini App via Telegram initData"
```

---

## Task 6: Manual smoke test on real Telegram clients

**Files:** none — observation only.

**Setup:** make sure `dev` is deployed (or run frontend + backend locally with `web_app_url` pointing at a tunnel).

**Step 1: First-time linked-user path (Android)**

1. Make sure your test Telegram account is already linked (run `/start`, sign in with Google once if not).
2. Force a fresh state: clear the WebApp's localStorage by tapping the bot's menu → "Reload".
3. In the bot, run `/coach`.
4. Tap "Open Coach".

Expected: Coach UI appears within ~1 second. **No Google OAuth screen.** Network panel (or backend logs) shows `POST /api/auth/telegram/exchange → 200`.

**Step 2: First-time linked-user path (iOS)**

Repeat Step 1 on an iOS Telegram client (this is the platform that actually motivated the change — its WebView drops localStorage between opens).

Expected: same — coach loads silently after one round-trip. No Safari hop, no Google.

**Step 3: Unlinked user fallback**

1. Use a second Telegram account that has never linked. Skip `/start`.
2. Get the bot to send a `/coach` link to it (or open the WebApp via the bot menu).

Expected: redirect to `/signin`, Google OAuth flow appears (existing behavior). After OAuth completes, `linkTelegramId` runs and second open should be silent.

**Step 4: Web (non-Telegram) path unchanged**

1. Open `app.example.com/coach` in a normal browser, signed out.

Expected: redirect to `/signin`, OAuth flow as before. `useTelegramAutoLogin` should bail out on `isTelegramMiniApp()`.

**Step 5: Capture findings**

If any step fails, file the failure mode (network response, console error, screenshot) before fixing — do NOT silently patch and move on.

**Step 6: Final commit (only if there are no fixups)**

If steps 1–4 all pass without code changes, no commit needed. Otherwise commit fixes with a clear message.

---

## Done criteria

- All backend tests pass (`pytest tests/ -x`).
- Frontend type-checks and builds (`npx tsc --noEmit && npx next build`).
- Manual smoke (Task 6) passes on Android + iOS + browser.
- No changes to bot code, `/signin` page, `useAuth`, or web-only OAuth flow.

## Out of scope (already noted in design)

- Caching token_hash server-side.
- Rate-limiting `/exchange`.
- Custom non-Supabase JWTs.
- Backfilling email for legacy profiles.
