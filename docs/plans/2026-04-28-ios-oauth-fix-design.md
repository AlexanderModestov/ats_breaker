# iOS Telegram WebApp — Google OAuth Fix

**Date:** 2026-04-28
**Scope:** Surgical fix for `Error 403: disallowed_useragent` when iOS Telegram users sign in via Google.

## Problem

Google OAuth blocks WKWebView (iOS Telegram WebApp) with `Error 403: disallowed_useragent`. Android Telegram uses a different WebView that Google permits, so the bug is iOS-only.

Current flow (broken on iOS):

1. Bot sends `WebAppInfo` button → opens `/signin` inside Telegram WebApp.
2. User taps **Continue with Google**.
3. `supabase.auth.signInWithOAuth({ provider: 'google', redirectTo })` does `window.location = accounts.google.com/...` inside WKWebView.
4. Google rejects the user-agent. Dead end.

## Decision: iOS-only branch

Fix applies only when `Telegram.WebApp.platform === 'ios'` AND running inside Telegram Mini App. All other platforms (Android WebApp, desktop Telegram, web browser) keep the current code path unchanged. Rationale: Android UX stays smooth (everything in-Telegram); iOS gets a Safari hop because Google forces it.

Alternative considered and rejected: unify all platforms via external browser. Simpler code, but degrades Android UX where the current in-WebApp flow works fine. Per CLAUDE.md "Surgical changes" — touch only what's broken.

## Architecture

**Branch point:** `onClick` handler of the Google button in `frontend/src/app/(auth)/signin/page.tsx`.

**Detection:** new helper `isTelegramIOS()` in `frontend/src/lib/telegram.ts` returning `Telegram.WebApp.platform === 'ios'`. Combined with existing `isTelegramMiniApp()`.

**iOS branch:** call `supabase.auth.signInWithOAuth` with `skipBrowserRedirect: true` to get the OAuth URL without auto-navigation, then `Telegram.WebApp.openLink(url)` to open Safari, then `Telegram.WebApp.close()` to drop the user back into the bot chat while OAuth happens externally.

**Callback in Safari:** Google redirects to `${origin}/signin?tg=${tgId}` in Safari (no Telegram context). The existing `useEffect` runs `linkTelegramId(tgId)` — works because it's a normal authenticated fetch. Then `Telegram.WebApp.close()` is a no-op in Safari, so we replace it with `tg://resolve?domain=<bot_username>` deep link to return the user to Telegram.

**Discriminating callback context:** `isPostOAuth` (URL has `?tg=…`) is already computed. Add `isTelegramMiniApp()` check:
- `true` → Android-style in-WebApp callback → `WebApp.close()` (current behavior).
- `false` → Safari-style post-iOS-OAuth callback → deep link to bot.

## Implementation

### 1. New helper

`frontend/src/lib/telegram.ts`:

```ts
export function isTelegramIOS(): boolean {
  if (typeof window === "undefined") return false;
  const wa = (window as any).Telegram?.WebApp;
  return wa?.platform === "ios";
}
```

### 2. Click handler in `signin/page.tsx`

```ts
const tgId = isTelegramMiniApp() ? getTelegramUserId() : null;
if (tgId) localStorage.setItem(PENDING_TG_ID_KEY, String(tgId));
const redirectTo = tgId
  ? `${window.location.origin}/signin?tg=${tgId}`
  : `${window.location.origin}/signin`;

track("signin_started", { method: "google" });

if (isTelegramMiniApp() && isTelegramIOS()) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo, skipBrowserRedirect: true },
  });
  if (error || !data?.url) {
    track("signin_failed", { method: "google", error: error?.message ?? "no_url" });
    return;
  }
  (window as any).Telegram?.WebApp?.openLink(data.url, { try_instant_view: false });
  (window as any).Telegram?.WebApp?.close();
  return;
}

// Existing path for Android WebApp / desktop / web.
try {
  await signInWithGoogle(redirectTo);
} catch (err) {
  track("signin_failed", {
    method: "google",
    error: err instanceof Error ? err.message : String(err),
  });
}
```

`useAuth.signInWithGoogle` is **not** modified. The iOS branch bypasses the hook because it needs `skipBrowserRedirect: true` to grab the URL. Adding a flag to the hook for one call site is unnecessary indirection.

### 3. Callback `useEffect` in `signin/page.tsx`

Replace the existing `if (isPostOAuth) { Telegram.WebApp.close() }` with:

```ts
if (isPostOAuth) {
  if (isTelegramMiniApp()) {
    (window as any).Telegram?.WebApp?.close();
  } else {
    const botUsername = process.env.NEXT_PUBLIC_TG_BOT_USERNAME;
    if (botUsername) {
      window.location.href = `tg://resolve?domain=${botUsername}`;
      setTimeout(() => {
        window.location.href = `https://t.me/${botUsername}`;
      }, 1500);
    }
  }
}
```

Keep this inside the existing `linkTelegramId(tgId).then(...)` so linking completes before navigation.

### 4. Env var

Add `NEXT_PUBLIC_TG_BOT_USERNAME` (without `@`) to:

- `frontend/.env.example`
- Vercel project env vars

If unset: Safari callback shows `/signin` then redirects to `/optimize` (user is signed in). Not ideal but non-breaking.

## Test matrix

| Scenario | Expected |
|----------|----------|
| iOS Telegram → sign in | Safari opens Google OAuth → callback in Safari → linkTelegramId → `tg://` deep link returns to bot |
| Android Telegram → sign in | Unchanged — OAuth inside WebApp, callback in WebApp, `WebApp.close()` |
| Web browser (no Telegram) | Unchanged — OAuth in same tab, redirect to `/optimize` |
| Desktop Telegram | Goes through non-iOS branch as today; if WKWebView-like issue surfaces, address separately |

## Edge cases

- **User closes Safari before callback:** Logged into Supabase (Safari cookie), `tg_id` not linked. On next bot `/start`, sign-in button shows again; `useLinkTelegram` picks up `pending_tg_id` from Safari localStorage at next visit. Already handled by existing code.
- **`tg://` deep link doesn't fire** (rare on iOS): 1.5s timeout fallback to `https://t.me/<bot>`.
- **`NEXT_PUBLIC_TG_BOT_USERNAME` missing:** No deep link, but auth still completes. Acceptable degradation.

## Files touched

- `frontend/src/lib/telegram.ts` — add `isTelegramIOS()`
- `frontend/src/app/(auth)/signin/page.tsx` — branch in onClick + callback useEffect
- `frontend/.env.example` — add `NEXT_PUBLIC_TG_BOT_USERNAME`

No backend changes. No bot changes.
