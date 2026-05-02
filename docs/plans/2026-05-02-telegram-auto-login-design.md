# Telegram Mini App Auto-Login Design

**Date:** 2026-05-02
**Status:** Approved, ready for implementation

## Problem

When a user opens the `/coach` Mini App from the Telegram bot, they are forced through Google OAuth again, even though their `telegram_id` is already linked to a Supabase account in `profiles.telegram_id`.

Root cause: the Mini App's frontend (`(protected)` layout) authenticates only via Supabase session in `localStorage`. Telegram WebView (especially on iOS) does not reliably persist `localStorage` across openings, so `useAuth()` sees no session and `ProtectedLayout` redirects to `/signin`, triggering a fresh OAuth.

## Goal

After the user has linked their Telegram + Google account once (existing `/start` → `/signin` flow), every subsequent Mini App open authenticates silently via the trusted `Telegram.WebApp.initData` payload — no Google OAuth.

## Non-goals

- Changing first-time registration flow.
- Changing how the bot itself authenticates against the backend.
- Changing how web-only (browser) users sign in.
- Adding rate-limiting, caching, or custom JWTs (YAGNI).

## Architecture

### Flow — already-linked user

```
1. User taps "Open Coach" inline button in bot
2. Mini App opens at /coach
3. ProtectedLayout renders:
   - useAuth() → loading=true → session=null (localStorage empty)
   - useTelegramAutoLogin() detects: in MiniApp, has initData, no session
   - POST /api/auth/telegram/exchange { init_data }
   - Backend validates HMAC against bot_token → telegram_id
   - Looks up profiles.telegram_id → user_id, email
   - Calls supabase.auth.admin.generateLink({type:'magiclink', email})
   - Returns { token_hash, email }
4. Frontend: supabase.auth.verifyOtp({ token_hash, type: 'magiclink', email })
   → Supabase writes session to localStorage
5. useAuth's onAuthStateChange fires → isAuthenticated=true
6. ProtectedLayout renders /coach normally
```

### Flow — telegram_id NOT linked (fallback)

- Exchange endpoint returns 404
- `useTelegramAutoLogin` silently completes, sets a session-storage "tried" flag
- `useAuth` stays unauthenticated → existing `ProtectedLayout` redirect to `/signin`
- Existing Google OAuth + `linkTelegramId` runs as today

### What does NOT change

- Bot handlers (`/start`, `/coach`, `/optimize`, `/help`).
- `/signin` page.
- `useAuth`, `useLinkTelegram`.
- Backend bot auth scheme (`X-Bot-Api-Key` + `X-Telegram-User-Id`).
- Web-only browser sign-in.

## Backend

### Endpoint

`POST /api/auth/telegram/exchange`

**Request:**
```json
{ "init_data": "<raw Telegram.WebApp.initData query string>" }
```

**Response (200):**
```json
{ "token_hash": "...", "email": "user@example.com" }
```

**Errors:**
- `401 Invalid Telegram signature` — HMAC mismatch
- `401 initData expired` — `auth_date` older than 1 hour
- `404 Telegram user not linked` — no profile with this `telegram_id`
- `409 Profile has no email` — linked profile lacks email
- `500` — Supabase admin error

### HMAC validation (per Telegram WebApp spec)

```python
parsed = parse_qs(init_data)
received_hash = parsed.pop("hash")
data_check_string = "\n".join(
    f"{k}={v[0]}" for k, v in sorted(parsed.items())
)
secret_key = hmac.new(b"WebAppData", bot_token.encode(), sha256).digest()
expected = hmac.new(secret_key, data_check_string.encode(), sha256).hexdigest()
hmac.compare_digest(expected, received_hash)
```

Use `compare_digest` for timing-safe comparison.

### Replay protection

`auth_date` (Unix timestamp from initData) must be within the last 3600 seconds, else 401.

### Implementation locations

- `src/hr_breaker/api/routes/telegram.py` — new endpoint, HMAC helper.
- `src/hr_breaker/services/supabase.py` — add `generate_magiclink(email) -> str` using existing service-role admin client.
- `tests/test_telegram_exchange.py` — new test file.

## Frontend

### New hook: `useTelegramAutoLogin`

File: `frontend/src/hooks/useTelegramAutoLogin.ts`

Behavior:
1. Bail if not in Telegram Mini App (`isTelegramMiniApp()` false).
2. Bail if `useAuth().session` exists.
3. Bail if `sessionStorage.getItem("tg_auto_login_tried") === "1"` (loop guard).
4. Read `Telegram.WebApp.initData`. Bail if empty.
5. POST to `/api/auth/telegram/exchange`.
6. On success → `supabase.auth.verifyOtp({ token_hash, type: 'magiclink', email })`. Set `tried` flag on completion either way.
7. On any error → set `tried` flag, swallow. `ProtectedLayout` will redirect to `/signin`.

Returns `{ attempting: boolean }` — true while the network round-trip is in flight.

### `ProtectedLayout` changes

`frontend/src/app/(protected)/layout.tsx`:

```tsx
const { isAuthenticated, loading } = useAuth();
const { attempting } = useTelegramAutoLogin();
useLinkTelegram();

useEffect(() => {
  if (!loading && !isAuthenticated && !attempting) {
    router.push("/signin");
  }
}, [isAuthenticated, loading, attempting, router]);

if (loading || attempting) {
  return <LoadingSpinner />;  // existing spinner block
}
```

### API client

`frontend/src/lib/api.ts` — add:

```ts
export async function exchangeTelegramInitData(
  initData: string
): Promise<{ token_hash: string; email: string }>
```

### What does NOT change on the frontend

- `useAuth` — Supabase session works the same after `verifyOtp` as after OAuth.
- `useLinkTelegram` — still needed for first-time post-OAuth linking.
- All other `(protected)` pages inherit the new behavior via the layout.

## Edge cases

| Case | Behavior |
|------|----------|
| Profile has no email | 409 → fallback to `/signin` |
| Supabase user deleted but profile remains | `generateLink` fails → 500 → fallback |
| `auth_date` > 1h old | 401 → fallback |
| Already authenticated (web user) | Hook bails early, no exchange |
| iOS WebView drops localStorage on every open | Each open does one silent exchange — acceptable |
| Exchange fails repeatedly | `tried` flag prevents loop |

## Security

- `compare_digest` for HMAC equality.
- `bot_token` never sent to frontend.
- `token_hash` is short-lived (Supabase default ~1h).
- `init_data` sent only in HTTPS POST body, never in URL.
- Endpoint is unauthenticated by design — HMAC IS the auth.

## Tests

**Backend** (`tests/test_telegram_exchange.py`):
- valid HMAC → 200 + token_hash
- invalid hash → 401
- expired `auth_date` → 401
- unlinked `telegram_id` → 404
- profile without email → 409

**Frontend:**
- Manual smoke: open `/coach` from bot twice — second open must NOT show Google OAuth.
- Verify on Android and iOS Telegram clients.

## Implementation order

1. `SupabaseService.generate_magiclink()`.
2. `POST /api/auth/telegram/exchange` + HMAC helper.
3. Backend tests.
4. `lib/api.ts::exchangeTelegramInitData`.
5. `useTelegramAutoLogin` hook.
6. `ProtectedLayout` integration + spinner gate.
7. Manual smoke on both platforms.

## YAGNI — explicitly not in scope

- Caching token_hash server-side.
- Rate-limiting the exchange endpoint.
- Custom (non-Supabase) JWT.
- Re-authentication on session expiry mid-use (Supabase auto-refresh handles it).
