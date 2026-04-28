# iOS Telegram OAuth Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Google sign-in work for iOS Telegram users by routing OAuth through Safari instead of WKWebView.

**Architecture:** Detect `Telegram.WebApp.platform === 'ios'` in `/signin`. On iOS-only, fetch Supabase OAuth URL with `skipBrowserRedirect: true`, open it via `Telegram.WebApp.openLink` (forces external Safari), close the WebApp. After Google callback lands in Safari, link the Telegram ID and deep-link back to the bot via `tg://resolve?domain=<bot>`. Android/desktop/web paths stay unchanged.

**Tech Stack:** Next.js 14 App Router, Supabase JS client (`@supabase/supabase-js`), Telegram WebApp SDK (`window.Telegram.WebApp`), TypeScript.

**Verification approach:** Frontend has no test runner; adding one for a 3-file fix violates YAGNI. Static verification: `npm run lint` + `npm run build` (Next.js typechecks during build). Behavioral verification: manual matrix on iOS/Android/web.

**Design doc:** `docs/plans/2026-04-28-ios-oauth-fix-design.md`

---

### Task 1: Add `isTelegramIOS` helper

**Files:**
- Modify: `frontend/src/lib/telegram.ts`

**Step 1: Read current file to confirm shape**

Run: `Read frontend/src/lib/telegram.ts`
Expected: file with `isTelegramMiniApp` and `getTelegramUserId` exports.

**Step 2: Append the helper**

Add at the end of the file:

```ts
export function isTelegramIOS(): boolean {
  if (typeof window === "undefined") return false;
  const wa = (window as unknown as { Telegram?: { WebApp?: { platform?: string } } }).Telegram?.WebApp;
  return wa?.platform === "ios";
}
```

Rationale for typed access: file already touches `window.Telegram` — match whatever pattern is there. If existing code uses `(window as any)`, mirror that for consistency. Pick after reading the file.

**Step 3: Verify lint**

Run: `cd frontend && npm run lint -- --max-warnings 0`
Expected: passes (or same warnings as baseline; no new ones).

**Step 4: Commit**

```bash
git add frontend/src/lib/telegram.ts
git commit -m "feat(frontend): add isTelegramIOS platform helper"
```

---

### Task 2: Branch the sign-in click handler for iOS

**Files:**
- Modify: `frontend/src/app/(auth)/signin/page.tsx` (the `onClick` handler of the Google button, lines ~194–211)

**Step 1: Read the current handler**

Run: `Read frontend/src/app/(auth)/signin/page.tsx`
Confirm imports include `getTelegramUserId`, `isTelegramMiniApp` from `@/lib/telegram`. Add `isTelegramIOS` to that import.

Confirm `getSupabaseClient` is **not yet imported** in this file. Add import: `import { getSupabaseClient } from "@/lib/supabase";` (verify path matches the one used in `useAuth.ts`).

**Step 2: Replace the onClick body**

Find the `onClick` handler in the Google button. Replace its body with:

```ts
const tgId = isTelegramMiniApp() ? getTelegramUserId() : null;
if (tgId) localStorage.setItem(PENDING_TG_ID_KEY, String(tgId));

const redirectTo = tgId
  ? `${window.location.origin}/signin?tg=${tgId}`
  : `${window.location.origin}/signin`;

track("signin_started", { method: "google" });

if (isTelegramMiniApp() && isTelegramIOS()) {
  // iOS Telegram WebApp uses WKWebView, which Google blocks for OAuth
  // (Error 403: disallowed_useragent). Open the auth URL in Safari instead.
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo, skipBrowserRedirect: true },
  });
  if (error || !data?.url) {
    track("signin_failed", {
      method: "google",
      error: error?.message ?? "no_url",
    });
    return;
  }
  const wa = (window as any).Telegram?.WebApp;
  wa?.openLink(data.url, { try_instant_view: false });
  wa?.close();
  return;
}

try {
  await signInWithGoogle(redirectTo);
} catch (err) {
  track("signin_failed", {
    method: "google",
    error: err instanceof Error ? err.message : String(err),
  });
}
```

**Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds, no new TS errors.

**Step 4: Commit**

```bash
git add frontend/src/app/\(auth\)/signin/page.tsx
git commit -m "feat(signin): route Google OAuth through Safari on iOS Telegram"
```

---

### Task 3: Deep-link back to bot from Safari callback

**Files:**
- Modify: `frontend/src/app/(auth)/signin/page.tsx` (the `useEffect` callback block, the `if (isPostOAuth)` branch around lines 64–66)

**Step 1: Read current callback logic**

Confirm the `linkTelegramId(tgId).then(...)` chain exists with `if (isPostOAuth) { Telegram.WebApp.close(); }` inside.

**Step 2: Replace the close() call with branch**

Inside `.then()`, replace:

```ts
if (isPostOAuth) {
  (window as any).Telegram?.WebApp?.close();
}
```

with:

```ts
if (isPostOAuth) {
  if (isTelegramMiniApp()) {
    // Android WebApp callback: OAuth completed inside Telegram, just close.
    (window as any).Telegram?.WebApp?.close();
  } else {
    // Safari callback after iOS OAuth hop: deep-link back to the bot.
    const botUsername = process.env.NEXT_PUBLIC_TG_BOT_USERNAME;
    if (botUsername) {
      window.location.href = `tg://resolve?domain=${botUsername}`;
      // Fallback if tg:// doesn't resolve (e.g. Telegram not installed).
      setTimeout(() => {
        window.location.href = `https://t.me/${botUsername}`;
      }, 1500);
    }
  }
}
```

**Step 3: Add env var to example**

Modify `frontend/.env.example` — append:

```
# Telegram bot username (without @) used to deep-link back from Safari after iOS OAuth.
NEXT_PUBLIC_TG_BOT_USERNAME=
```

**Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

**Step 5: Commit**

```bash
git add frontend/src/app/\(auth\)/signin/page.tsx frontend/.env.example
git commit -m "feat(signin): deep-link back to Telegram bot after Safari OAuth callback"
```

---

### Task 4: Configure env var in Vercel

**Files:** none (external action)

**Step 1:** Set `NEXT_PUBLIC_TG_BOT_USERNAME` in Vercel project env vars (Production + Preview). Value = bot username **without `@`**, e.g. `hr_breaker_bot`.

**Step 2:** Confirm value matches the actual deployed bot — the bot whose `t.me/<username>` link returns the user to the correct chat.

**Note:** This is a manual step; Claude cannot do it. Skip if user has already done it.

---

### Task 5: Manual verification matrix

**Files:** none

After deploying preview build, run through this matrix and record results.

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| 1 | iOS Telegram → sign in | Open bot in iOS Telegram → tap Sign in → tap Continue with Google | Safari opens with Google login. After login, lands on `/signin?tg=…` in Safari, then redirects to Telegram via `tg://`. Bot now greets as authenticated user on next `/start`. |
| 2 | Android Telegram → sign in | Same on Android | OAuth happens inside WebApp, completes, WebApp closes, bot greets authenticated user. **No regression.** |
| 3 | Web browser sign-in (no Telegram) | Open `/signin` in desktop browser → Continue with Google | OAuth in same tab, redirect to `/optimize`. **No regression.** |
| 4 | iOS Safari direct (no Telegram) | Open `/signin` URL in Safari (not from Telegram) → Continue with Google | OAuth in same tab, redirect to `/optimize`. No `tg://` redirect (no `?tg=…`). |
| 5 | iOS user closes Safari mid-OAuth | Tap sign in → in Safari, close before completing | On next `/start`, bot still shows sign-in button. `useLinkTelegram` picks up `pending_tg_id` on next successful login. |

**Step 1:** Run scenarios 1–5 against the preview deployment.
**Step 2:** Document outcomes (pass/fail + screenshots if useful) in the PR description.

---

### Task 6: Open PR

**Step 1:** Push branch:

```bash
git push -u origin feature/ios-oauth-fix
```

**Step 2:** Open PR with:
- Title: `Fix Google OAuth for iOS Telegram users`
- Body: link to `docs/plans/2026-04-28-ios-oauth-fix-design.md`, paste matrix results from Task 5
- Note: requires `NEXT_PUBLIC_TG_BOT_USERNAME` env var in Vercel before merge
