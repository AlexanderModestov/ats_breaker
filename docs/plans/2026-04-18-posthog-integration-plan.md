# PostHog Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PostHog (EU Cloud) to the Next.js frontend to track pageviews and a defined set of custom funnel events; identify users after Supabase signin; stay cookieless until signin.

**Architecture:** Client-only integration via `posthog-js`. A `PostHogProvider` component initializes the SDK, subscribes to Supabase `onAuthStateChange`, calls `identify()` on `SIGNED_IN`, `reset()` on `SIGNED_OUT`, and emits `$pageview` on Next.js App Router navigations. A thin `useAnalytics` hook fires custom events from feature components.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, `@supabase/supabase-js`, `posthog-js` (new).

**Design reference:** `docs/plans/2026-04-18-posthog-integration-design.md` — do not deviate without explicit approval.

---

## Testing Strategy (Read First)

The frontend has no unit test runner configured (no Jest / Vitest in `frontend/package.json`). Do **not** introduce one for this task — it is out of scope.

Automated gates per task:
- `npm run lint` — ESLint
- `npm run build` — runs `next build`, which type-checks the entire project. This is our type-check gate.

Runtime gate (at the end, after all code tasks): a manual verification checklist in **Task 14**. The executor runs the dev server, walks the funnel, and confirms events in PostHog **Live Events**. Do not mark the feature complete until this passes.

Commit after every task. Short commits are cheap; bisecting a 500-line commit is not.

---

## Task 1: Install posthog-js

**Files:**
- Modify: `frontend/package.json` (via npm)
- Modify: `frontend/package-lock.json` (auto-updated)

**Step 1: Install the package**

Run from `frontend/`:

```bash
cd frontend && npm install posthog-js
```

Expected: one new dependency added, no peer-dep warnings that mention React or Next.

**Step 2: Verify build still works**

```bash
cd frontend && npm run build
```

Expected: PASS. No type errors.

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add posthog-js dependency"
```

---

## Task 2: Add env var documentation

**Files:**
- Modify: `frontend/.env.example` (create if it does not exist — check first with `ls frontend/.env.example`)

**Step 1: Check if `.env.example` exists**

```bash
ls frontend/.env.example 2>&1 || echo "NOT PRESENT"
```

If present, read it first. If not, create it as below with only the two new vars (other teams add theirs separately).

**Step 2: Add or append PostHog vars**

Append (or create with) these two lines to `frontend/.env.example`:

```
# PostHog (client-side). Leave NEXT_PUBLIC_POSTHOG_KEY empty to disable locally.
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
```

Do **not** edit `frontend/.env.local` (gitignored — user manages that).

**Step 3: Commit**

```bash
git add frontend/.env.example
git commit -m "docs: document PostHog env vars in .env.example"
```

---

## Task 3: Create `lib/posthog.ts` — SDK singleton

**Files:**
- Create: `frontend/src/lib/posthog.ts`

**Step 1: Write the module**

```ts
// frontend/src/lib/posthog.ts
"use client";

import posthog from "posthog-js";

let initialized = false;

export function initPostHog(): void {
  if (initialized) return;
  if (typeof window === "undefined") return;

  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  const host = process.env.NEXT_PUBLIC_POSTHOG_HOST;
  if (!key) return; // silently disabled when no key (e.g. local dev without a key)

  posthog.init(key, {
    api_host: host,
    persistence: "memory", // cookieless until signin — see PostHogProvider
    capture_pageview: false, // we emit $pageview manually for App Router navigation
    capture_pageleave: true,
    autocapture: true,
    disable_session_recording: true,
    loaded: (ph) => {
      if (process.env.NODE_ENV === "development") {
        ph.debug();
      }
    },
  });

  initialized = true;
}

export function isPostHogEnabled(): boolean {
  return initialized;
}

export { posthog };
```

**Step 2: Type-check**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 3: Commit**

```bash
git add frontend/src/lib/posthog.ts
git commit -m "feat(analytics): add posthog SDK singleton"
```

---

## Task 4: Create `hooks/useAnalytics.ts`

**Files:**
- Create: `frontend/src/hooks/useAnalytics.ts`

**Step 1: Write the hook**

```ts
// frontend/src/hooks/useAnalytics.ts
"use client";

import { posthog } from "@/lib/posthog";

export type AnalyticsEvent =
  | "signin_started"
  | "signin_completed"
  | "signin_failed"
  | "resume_uploaded"
  | "job_provided"
  | "optimization_started"
  | "optimization_completed"
  | "optimization_failed"
  | "pdf_downloaded"
  | "pricing_viewed"
  | "pdf_history_viewed";

export function useAnalytics() {
  return {
    track: (event: AnalyticsEvent, props?: Record<string, unknown>) => {
      try {
        posthog.capture(event, props);
      } catch {
        // PostHog may be uninitialized (no key in env); swallow — never break UX.
      }
    },
  };
}
```

**Rationale for the try/catch:** `posthog.capture()` before `posthog.init()` throws. We want analytics to be a no-op when disabled, not a crash source.

**Step 2: Type-check**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 3: Commit**

```bash
git add frontend/src/hooks/useAnalytics.ts
git commit -m "feat(analytics): add useAnalytics hook with typed events"
```

---

## Task 5: Create `PostHogProvider` component

**Files:**
- Create: `frontend/src/components/PostHogProvider.tsx`

**Context reminder:** `useAuth` already owns one `onAuthStateChange` subscription. A second independent subscription in this provider is fine — Supabase supports multiple listeners, and colocating identify/reset logic here keeps PostHog concerns out of `useAuth`.

**Step 1: Write the provider**

```tsx
// frontend/src/components/PostHogProvider.tsx
"use client";

import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { getSupabaseClient } from "@/lib/supabase";
import { initPostHog, posthog } from "@/lib/posthog";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Init + Supabase auth subscription (one-shot on mount).
  useEffect(() => {
    initPostHog();
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return;

    const supabase = getSupabaseClient();

    // Pick up an existing session at load time (e.g. refresh while logged in).
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        identifyUser(session.user.id, session.user.email, session.user.created_at);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session?.user) {
        identifyUser(session.user.id, session.user.email, session.user.created_at);
        posthog.capture("signin_completed");
      } else if (event === "SIGNED_OUT") {
        posthog.reset();
        posthog.set_config({ persistence: "memory" });
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  // Emit $pageview on client-side navigation.
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY || !pathname) return;
    const qs = searchParams?.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    posthog.capture("$pageview", { $current_url: url });
  }, [pathname, searchParams]);

  return <>{children}</>;
}

function identifyUser(
  userId: string,
  email: string | undefined,
  createdAt: string | undefined
) {
  // Switch to persistent storage now that the user has a logged-in session
  // (ToS accepted → consent covers analytics cookies).
  posthog.set_config({ persistence: "localStorage+cookie" });
  posthog.identify(userId, {
    email,
    created_at: createdAt,
    auth_provider: "google",
  });
}
```

**Notes:**
- `auth_provider: "google"` is hardcoded because `useAuth` currently only exposes `signInWithGoogle`. When a second provider is added, thread it through properly — do not guess from email domain.
- `signin_completed` lives **inside** the `SIGNED_IN` branch so it fires exactly once per login, not on session hydration at mount.
- We ignore `TOKEN_REFRESHED`, `USER_UPDATED`, and other events — only care about transitions.

**Step 2: Type-check**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 3: Commit**

```bash
git add frontend/src/components/PostHogProvider.tsx
git commit -m "feat(analytics): add PostHogProvider with auth lifecycle"
```

---

## Task 6: Wire `PostHogProvider` into the app

**Files:**
- Modify: `frontend/src/app/providers.tsx`

**Step 1: Read current content**

Verify the file matches the snapshot from the plan context (see design doc). If it has drifted, adapt.

**Step 2: Wrap children with `<PostHogProvider>`**

Replace the body of `providers.tsx` with:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, Suspense } from "react";
import { PostHogProvider } from "@/components/PostHogProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={null}>
        <PostHogProvider>{children}</PostHogProvider>
      </Suspense>
    </QueryClientProvider>
  );
}
```

**Why `<Suspense>`:** `useSearchParams()` inside `PostHogProvider` forces any caller into a Suspense boundary when used during static rendering. Wrapping here keeps Next.js happy without leaking a loading UI (fallback is `null` — the rest of the tree still renders).

**Step 3: Build and verify**

```bash
cd frontend && npm run build
```

Expected: PASS. No warnings about missing Suspense boundaries.

**Step 4: Commit**

```bash
git add frontend/src/app/providers.tsx
git commit -m "feat(analytics): mount PostHogProvider in app providers"
```

---

## Task 7: Fire `signin_started` / `signin_failed` in signin page

**Files:**
- Modify: `frontend/src/app/(auth)/signin/page.tsx`

**Step 1: Read the file** to find the Google button `onClick` (currently around the `<Button ... onClick={...}>` in the rendered form).

**Step 2: Import the hook**

Add alongside existing imports:

```tsx
import { useAnalytics } from "@/hooks/useAnalytics";
```

**Step 3: Use the hook in the component**

Inside `LoginPage()`, after the existing hook calls:

```tsx
const { track } = useAnalytics();
```

**Step 4: Wrap `signInWithGoogle()` with tracking**

Replace the existing button `onClick` with one that tracks start and failure:

```tsx
onClick={async () => {
  if (isTelegramMiniApp()) {
    const tgId = getTelegramUserId();
    if (tgId) localStorage.setItem(PENDING_TG_ID_KEY, String(tgId));
  }
  track("signin_started", { method: "google" });
  try {
    await signInWithGoogle();
  } catch (err) {
    track("signin_failed", {
      method: "google",
      error: err instanceof Error ? err.message : String(err),
    });
  }
}}
```

**Why `async`:** existing code fires-and-forgets `signInWithGoogle()`. We need a try/catch around it for `signin_failed`. `signin_completed` is fired inside `PostHogProvider` — do **not** duplicate it here.

**Step 5: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/app/\(auth\)/signin/page.tsx
git commit -m "feat(analytics): track signin started and failed events"
```

---

## Task 8: Fire `resume_uploaded`

**Files:**
- Modify: exact file TBD — locate first.

**Step 1: Find the upload handler**

Run:

```bash
cd frontend && grep -rln "type=\"file\"\|accept=.*pdf\|onChange.*files" src/
```

Likely candidates: `src/app/(protected)/cvs/page.tsx`, `src/components/CVCard.tsx`, or `src/components/CVDropdown.tsx`. Open the hit(s) and find the one that handles actual file input `onChange`.

**Step 2: Add tracking**

In the component that contains the `<input type="file">` onChange handler:

```tsx
import { useAnalytics } from "@/hooks/useAnalytics";

// inside component:
const { track } = useAnalytics();
```

Inside the `onChange` handler (after getting the selected `File`):

```tsx
const file = e.target.files?.[0];
if (!file) return;
track("resume_uploaded", {
  format: file.name.split(".").pop()?.toLowerCase() ?? "unknown",
  size_kb: Math.round(file.size / 1024),
});
// ... existing upload logic
```

**Rationale:** track the user's *intent to upload* (the file selection) rather than success. Failed uploads are still useful signal and we already have `optimization_started/failed` later in the funnel.

**Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 4: Commit**

```bash
git add frontend/src/<modified-file>
git commit -m "feat(analytics): track resume_uploaded on file selection"
```

---

## Task 9: Fire `job_provided`

**Files:**
- Modify: `frontend/src/components/JobInput.tsx`

**Step 1: Read the file** to understand the submit flow — is it a form `onSubmit`, or a button + parent callback?

**Step 2: Add tracking**

Add the hook at the top of the component, then fire `job_provided` when the job is submitted (whichever event takes the user from "entering a job" to "job committed for optimization").

Property shape:

```ts
track("job_provided", {
  input_type: isUrl(value) ? "url" : "text",
});
```

Where `isUrl` is a simple check — reuse whatever the component already does, or inline:

```ts
const isUrl = (s: string) => /^https?:\/\//i.test(s.trim());
```

If the component already distinguishes URL vs text in its state, reuse that — do **not** duplicate detection logic.

**Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 4: Commit**

```bash
git add frontend/src/components/JobInput.tsx
git commit -m "feat(analytics): track job_provided on job submission"
```

---

## Task 10: Fire `optimization_started` / `_completed` / `_failed`

**Files:**
- Modify: `frontend/src/hooks/useOptimization.ts`

**Step 1: Import the hook's primitives**

At the top of the file, add:

```ts
import { posthog } from "@/lib/posthog";
```

We use `posthog` directly (not `useAnalytics`) because two of the three events happen in `useCallback` / `useEffect` outside React component bodies.

**Step 2: `optimization_started` in `useStartOptimization`**

Replace the existing body with:

```ts
export function useStartOptimization() {
  const startedAtRef = useRef<number>(0);
  return useMutation({
    mutationFn: (request: OptimizeRequest) => {
      startedAtRef.current = Date.now();
      try {
        posthog.capture("optimization_started");
      } catch { /* noop when disabled */ }
      return startOptimization(request);
    },
  });
}
```

Add `useRef` to the existing `react` import if not already there. Do **not** leak `startedAtRef` outside the hook — it is used only to measure duration when we get the status transition below. Actually wait: this ref lives in `useStartOptimization` but the completion signal comes from `useOptimizationStatus`. They are separate hooks, so the ref won't be visible there.

Simpler, correct approach: remove the ref from here. Measure duration in `useOptimizationStatus` based on the first time we see a non-terminal status (that is when polling starts) vs. when we see a terminal one.

Replace the Step 2 snippet above with this simpler version:

```ts
export function useStartOptimization() {
  return useMutation({
    mutationFn: (request: OptimizeRequest) => {
      try {
        posthog.capture("optimization_started");
      } catch { /* noop when disabled */ }
      return startOptimization(request);
    },
  });
}
```

**Step 3: `optimization_completed` / `_failed` in `useOptimizationStatus`**

This hook polls until `status.status === "complete"` or `"failed"`. We must fire the terminal event **exactly once per runId**, on the transition.

Modify the hook:

```ts
export function useOptimizationStatus(runId: string | null) {
  const [status, setStatus] = useState<OptimizationStatus | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const startedAtRef = useRef<number>(0);
  const terminalFiredRef = useRef<boolean>(false);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    if (!runId) return;
    try {
      const data = await getOptimizationStatus(runId);
      setStatus(data);
      setError(null);

      if (!terminalFiredRef.current && (data.status === "complete" || data.status === "failed")) {
        terminalFiredRef.current = true;
        const durationSec = startedAtRef.current
          ? Math.round((Date.now() - startedAtRef.current) / 1000)
          : undefined;
        try {
          if (data.status === "complete") {
            posthog.capture("optimization_completed", {
              iterations: (data as unknown as { iterations?: number }).iterations,
              duration_sec: durationSec,
            });
          } else {
            posthog.capture("optimization_failed", {
              stage: (data as unknown as { stage?: string }).stage,
              error_type: (data as unknown as { error?: string }).error,
            });
          }
        } catch { /* noop */ }
        stopPolling();
      } else if (data.status === "complete" || data.status === "failed") {
        // Already fired; just make sure we stop.
        stopPolling();
      }
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Failed to fetch status"));
      stopPolling();
    }
  }, [runId, stopPolling]);

  useEffect(() => {
    if (!runId) {
      setStatus(null);
      setError(null);
      setLoading(false);
      terminalFiredRef.current = false;
      startedAtRef.current = 0;
      return;
    }

    setLoading(true);
    terminalFiredRef.current = false;
    startedAtRef.current = Date.now();
    fetchStatus().then(() => setLoading(false));
    intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL);

    return () => stopPolling();
  }, [runId, fetchStatus, stopPolling]);

  return { status, error, loading, refetch: fetchStatus };
}
```

**Important about `iterations`, `stage`, `error`:** these are not part of the declared `OptimizationStatus` type visible here. Check `frontend/src/types` (grep for `OptimizationStatus`) and use properly typed fields. If any of these fields do not exist on the server response today, **drop them from the event properties** — do not invent them. Document what is sent in the commit message.

**Step 4: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/hooks/useOptimization.ts
git commit -m "feat(analytics): track optimization started/completed/failed"
```

---

## Task 11: Fire `pdf_downloaded`

**Files:**
- Modify: `frontend/src/hooks/useOptimization.ts` (inside `useDownloadPDF`)

**Step 1: Add capture in `useDownloadPDF`**

Inside the `download` callback, after the file successfully reaches `a.click()` but before the `finally` cleanup:

```ts
try {
  posthog.capture("pdf_downloaded");
} catch { /* noop */ }
```

Place it right after `a.click();` so we track the moment the browser download is triggered. If `downloadOptimizationPDF` throws, we skip it — an error means no PDF landed on disk.

**Step 2: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 3: Commit**

```bash
git add frontend/src/hooks/useOptimization.ts
git commit -m "feat(analytics): track pdf_downloaded"
```

---

## Task 12: Fire `pricing_viewed` and `pdf_history_viewed`

**Files:**
- Modify: `frontend/src/app/pricing/page.tsx`
- Modify: `frontend/src/app/(protected)/history/page.tsx`

**Step 1: Check if each page is already a client component**

Read the first line of each file. If it is not `"use client";`, do **not** add the directive just for analytics — instead, create a tiny inline child component (below) and mount it there. Server-component pages cannot use hooks.

**Step 2a: For client pages**

Add at the top of the component:

```tsx
import { useEffect } from "react";
import { useAnalytics } from "@/hooks/useAnalytics";

// inside the component, ONCE:
const { track } = useAnalytics();
useEffect(() => {
  track("pricing_viewed"); // or "pdf_history_viewed"
}, [track]);
```

**Step 2b: For server pages**

Create `frontend/src/components/PageViewTracker.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useAnalytics, type AnalyticsEvent } from "@/hooks/useAnalytics";

export function PageViewTracker({ event }: { event: AnalyticsEvent }) {
  const { track } = useAnalytics();
  useEffect(() => {
    track(event);
  }, [event, track]);
  return null;
}
```

Then in each server page:

```tsx
import { PageViewTracker } from "@/components/PageViewTracker";
// ...
return (
  <>
    <PageViewTracker event="pricing_viewed" />
    {/* existing page content */}
  </>
);
```

**Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 4: Commit**

```bash
git add frontend/src/app/pricing/page.tsx frontend/src/app/\(protected\)/history/page.tsx frontend/src/components/PageViewTracker.tsx
git commit -m "feat(analytics): track pricing_viewed and pdf_history_viewed"
```

(Omit `PageViewTracker.tsx` from the commit if it was not needed.)

---

## Task 13: Lint pass

**Files:** none — validation only.

**Step 1: Run lint**

```bash
cd frontend && npm run lint
```

Expected: PASS. Fix any new warnings or errors introduced by the tasks above. Do **not** alter unrelated pre-existing warnings — leave those for their owners.

**Step 2: Commit any lint fixes**

If fixes were required:

```bash
git add -A frontend/src/
git commit -m "chore(analytics): lint fixes"
```

If none were required, skip the commit.

---

## Task 14: Manual verification checklist

**Files:** none — runtime verification.

**Prerequisites:**
1. A PostHog EU Cloud account with a "dev" project — note the project key.
2. `.env.local` in `frontend/` contains:
   ```
   NEXT_PUBLIC_POSTHOG_KEY=phc_<your-dev-key>
   NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
   ```
   Plus existing Supabase vars.

**Step 1: Start the dev server**

```bash
cd frontend && npm run dev
```

Expected: server starts on `http://localhost:3000` with no runtime errors.

**Step 2: Open PostHog "Live Events"**

In PostHog UI, dev project → **Activity** → **Live**. Leave it open while you walk the funnel. Events appear with ~5s latency.

**Step 3: Walk the full funnel (fresh incognito window)**

For each action, confirm the corresponding event appears in Live:

1. Open `/` → expect `$pageview` with `pathname=/`.
2. Navigate to `/signin` → expect a new `$pageview`.
3. Click "Continue with Google" → expect `signin_started` with `{ method: "google" }`.
4. Complete Google OAuth → expect `signin_completed` (no props needed) AND a `$identify` event linking the previous `distinct_id` to the Supabase `user.id`. Confirm in **Persons** that a person exists with `email` and `auth_provider: "google"`.
5. Upload a resume → expect `resume_uploaded` with `{ format, size_kb }`.
6. Provide a job posting → expect `job_provided` with `{ input_type: "url" | "text" }`.
7. Start optimization → expect `optimization_started`. Wait for it to finish → expect `optimization_completed` with `{ duration_sec, iterations? }` OR `optimization_failed` if it fails.
8. Download the PDF → expect `pdf_downloaded`.
9. Visit `/pricing` → expect `pricing_viewed`.
10. Visit `/history` (the PDF history page) → expect `pdf_history_viewed`.
11. Sign out → confirm in **Live** that subsequent pageviews use a fresh anonymous `distinct_id` and cookies for `ph_*` are cleared.

**Step 4: Cookie sanity check**

- Before signin: DevTools → Application → Cookies → `localhost:3000`. Should show **no** `ph_*` cookies.
- After signin: should show `ph_<key>_posthog` cookie.
- After signout: cookie cleared.

**Step 5: If any step fails**

Do **not** patch blindly. Check browser console for posthog debug logs (enabled in dev). Most likely causes:
- `NEXT_PUBLIC_POSTHOG_KEY` is missing (events silently dropped — by design).
- Ad blocker blocking `eu.i.posthog.com` — disable for localhost.
- `autocapture` noise masking the custom event in Live — filter by event name.

Fix the underlying cause, not the test.

**Step 6: Mark the feature complete**

Only when every item in Step 3 + Step 4 passes. If you skip a step, say so explicitly; do not claim completion.

**Step 7: Commit nothing here** — this task is verification only. No code changes.

---

## Task 15: Update the design document with any deviations

**Files:**
- Modify: `docs/plans/2026-04-18-posthog-integration-design.md` (only if needed)

If any task above deviated from the design (e.g. different file path for resume upload, missing `OptimizationStatus` fields, different event properties), append a `## Deviations from Plan` section at the end of the design doc documenting:

- What changed
- Why
- What the production behavior now is

Commit:

```bash
git add docs/plans/2026-04-18-posthog-integration-design.md
git commit -m "docs: record deviations from PostHog design"
```

If no deviations, skip this task.

---

## Out of Scope — Do Not Implement

Every item below was explicitly deferred in the design. Do not be "helpful" and add them:

- Session replay
- Feature flags / A/B tests
- Backend events from FastAPI
- Custom cookie banner UI
- PostHog groups (company/tenant analytics)
- Reverse proxy for PostHog via Next.js rewrites

If you think one of these is needed mid-implementation, stop and ask — do not add it silently.
