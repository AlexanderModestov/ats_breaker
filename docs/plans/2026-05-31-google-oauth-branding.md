# Google OAuth Branding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the raw Supabase project ID in the Google "Sign in" screen with proper HR-Breaker branding, and optionally eliminate the Supabase subdomain from the "to continue to" URL entirely.

**Architecture:** Two independent tracks. Track A (no code changes) updates the Google OAuth consent screen in Google Cloud Console — this changes the displayed app name and logo but leaves the redirect domain as `snwqxshoyqmubxyxmsbz.supabase.co`. Track B (code change) adds a Next.js API proxy route that handles the OAuth callback on your own Vercel domain so Google shows `hrbreaker.com` (or whatever your production domain is) instead.

**Tech Stack:** Google Cloud Console, Supabase Dashboard, Next.js 16 (App Router), Supabase JS client (`@supabase/supabase-js`), Vercel

---

## Track A — Google Consent Screen Branding (no code, ~15 min)

This track makes the consent screen show "HR-Breaker" with a logo instead of a bare Supabase URL. The "to continue to snwqxshoyqmubxyxmsbz.supabase.co" line will still appear, but the app name and logo make the screen look legitimate.

---

### Task 1: Locate the Google Cloud project linked to your Supabase OAuth

**Files:** none (Google Cloud Console only)

**Step 1: Find the project**

1. Open Supabase Dashboard → your project → Authentication → Providers → Google
2. Copy the **Client ID** value (looks like `123456789-abc123.apps.googleusercontent.com`)
3. Go to [console.cloud.google.com](https://console.cloud.google.com)
4. In the top project picker, click it and search — or go to **APIs & Services → Credentials**
5. Find the OAuth 2.0 Client ID matching the value you copied from Supabase
6. Note which **project** it belongs to (shown in the top bar)

**Step 2: Verify you have the right project**

In Google Cloud Console → APIs & Services → Credentials, confirm the redirect URI for this OAuth client contains `snwqxshoyqmubxyxmsbz.supabase.co/auth/v1/callback`.

---

### Task 2: Update the OAuth Consent Screen

**Files:** none (Google Cloud Console only)

**Step 1: Open the consent screen editor**

Google Cloud Console → APIs & Services → OAuth consent screen

**Step 2: Fill in app branding fields**

| Field | Value |
|---|---|
| App name | `HR-Breaker` |
| User support email | `aleksandrmodestov@gmail.com` |
| App logo | Upload a 120×120 px PNG of your logo |
| App homepage | `https://<your-vercel-production-url>` |
| Privacy policy | `https://<your-vercel-production-url>/privacy` (create stub if missing) |
| Terms of service | `https://<your-vercel-production-url>/terms` (create stub if missing) |

**Step 3: Add authorized domain**

Under "Authorized domains", add your production Vercel domain (e.g., `hrbreaker.vercel.app` or your custom domain). Do **not** remove `supabase.co`.

**Step 4: Save and publish**

Click **Save and Continue** through all screens. If app is in "Testing" mode, change to **In Production** under the Publishing Status section (required so all Google accounts can sign in, not just test users).

**Expected result:** The Google sign-in dialog will now show "HR-Breaker" in bold with your logo, instead of a bare Supabase identifier.

---

### Task 3: Verify branding live

**Step 1:** Open your app's sign-in page in an incognito window.

**Step 2:** Click "Sign in with Google".

**Step 3:** Confirm the consent screen shows:
- App name: **HR-Breaker**
- Your logo (if uploaded)
- "to continue to snwqxshoyqmubxyxmsbz.supabase.co" (this line remains — see Track B to remove it)

---

## Track B — OAuth Proxy via Next.js (removes Supabase subdomain from "to continue to")

This track routes the OAuth callback through your own Vercel domain so Google shows your domain, not Supabase's. It adds two API routes and a small client-side redirect.

**How it works:**
1. User clicks "Sign in with Google"
2. Supabase generates an OAuth URL pointing to Google, with a redirect back to **your Vercel domain** (`/api/auth/callback`)
3. Google shows "to continue to yourapp.vercel.app" ✓
4. After Google auth, your `/api/auth/callback` route calls `supabase.auth.exchangeCodeForSession(code)` and redirects to the app

---

### Task 4: Add the OAuth callback API route

**Files:**
- Create: `frontend/src/app/api/auth/callback/route.ts`

**Step 1: Create the file**

```typescript
// frontend/src/app/api/auth/callback/route.ts
import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const next = requestUrl.searchParams.get("next") ?? "/";

  if (!code) {
    return NextResponse.redirect(new URL("/signin?error=missing_code", requestUrl.origin));
  }

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(
      new URL(`/signin?error=${encodeURIComponent(error.message)}`, requestUrl.origin)
    );
  }

  return NextResponse.redirect(new URL(next, requestUrl.origin));
}
```

**Step 2: No test needed for this route** — it will be verified end-to-end in Task 6.

---

### Task 5: Update the `signInWithGoogle` call to use PKCE + your callback URL

**Files:**
- Modify: `frontend/src/hooks/useAuth.ts` (the `signInWithGoogle` function)

**Step 1: Read the current implementation**

Open `frontend/src/hooks/useAuth.ts` and find the `signInWithGoogle` function. It currently calls:

```typescript
supabase.auth.signInWithOAuth({ provider: "google" })
```

**Step 2: Update the call**

Replace that call with:

```typescript
supabase.auth.signInWithOAuth({
  provider: "google",
  options: {
    redirectTo: `${window.location.origin}/api/auth/callback`,
  },
})
```

This tells Supabase to send Google's callback to your domain instead of the Supabase subdomain.

**Step 3: Register the new redirect URI in Supabase**

Supabase Dashboard → Authentication → URL Configuration → Redirect URLs → Add:

```
https://<your-vercel-domain>/api/auth/callback
http://localhost:3000/api/auth/callback
```

**Step 4: Register the new redirect URI in Google Cloud Console**

Google Cloud Console → APIs & Services → Credentials → your OAuth Client ID → Authorized redirect URIs → Add:

```
https://<your-vercel-domain>/api/auth/callback
http://localhost:3000/api/auth/callback
```

Keep the existing `https://snwqxshoyqmubxyxmsbz.supabase.co/auth/v1/callback` entry — removing it would break any existing sessions mid-flight.

**Step 5: Commit**

```bash
git add frontend/src/app/api/auth/callback/route.ts frontend/src/hooks/useAuth.ts
git commit -m "feat: route google oauth callback through own domain"
```

---

### Task 6: End-to-end verification

**Step 1:** Run the dev server locally:

```bash
cd frontend && npm run dev
```

**Step 2:** Open `http://localhost:3000/signin` in incognito.

**Step 3:** Click "Sign in with Google".

**Expected:** Google consent screen now shows "to continue to localhost" (dev) or your Vercel domain (prod).

**Step 4:** Complete sign-in. Confirm you land on the dashboard and `supabase.auth.getUser()` returns the signed-in user.

**Step 5:** Deploy to Vercel and repeat with production URL.

```bash
git push origin dev
```

**Step 6:** On production, confirm consent screen shows "to continue to `<your-vercel-domain>`" instead of the Supabase subdomain.

---

## Optional: Privacy Policy and Terms stubs

If you don't have `/privacy` or `/terms` pages yet (required by Google for production OAuth apps):

**Files:**
- Create: `frontend/src/app/privacy/page.tsx`
- Create: `frontend/src/app/terms/page.tsx`

Minimal stubs — just enough to satisfy Google's requirement:

```tsx
// frontend/src/app/privacy/page.tsx
export default function PrivacyPage() {
  return (
    <main style={{ maxWidth: 640, margin: "80px auto", padding: "0 24px" }}>
      <h1>Privacy Policy</h1>
      <p>HR-Breaker processes your resume data solely to generate optimized resumes. We do not sell or share your data with third parties.</p>
      <p>For questions, contact aleksandrmodestov@gmail.com</p>
    </main>
  );
}
```

```tsx
// frontend/src/app/terms/page.tsx
export default function TermsPage() {
  return (
    <main style={{ maxWidth: 640, margin: "80px auto", padding: "0 24px" }}>
      <h1>Terms of Service</h1>
      <p>By using HR-Breaker, you agree to use the service for lawful purposes only. The service is provided as-is without warranty.</p>
    </main>
  );
}
```

---

## Summary

| Track | Effort | Result |
|---|---|---|
| A — Consent screen branding | 15 min, no code | Shows "HR-Breaker" name + logo; Supabase URL still in "to continue to" |
| B — OAuth proxy route | 30 min, 2 files | Shows your own domain in "to continue to"; fully removes Supabase ID |
| Optional stubs | 10 min, 2 files | Satisfies Google's production OAuth requirements |

Start with Track A (immediate win, no risk). Do Track B if you want the URL gone entirely.
