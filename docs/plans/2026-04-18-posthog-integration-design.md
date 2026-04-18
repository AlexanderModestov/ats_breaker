# PostHog Integration — Design

**Date:** 2026-04-18
**Branch:** `feature/add_pothog`
**Goal:** Add PostHog to HR-Breaker frontend for user monitoring and traffic analysis.

## Decisions Summary

| # | Decision | Choice |
|---|---|---|
| 1 | Tracking scope | Frontend pageviews + key custom events (funnel). No backend events. |
| 2 | Hosting | PostHog Cloud EU (`eu.i.posthog.com`) |
| 3 | Session replay | Disabled |
| 4 | Identification | Anonymous until signin, then `identify(supabase_user_id)` |
| 5 | Events | Defined list (see Section 3) |
| 6 | Consent | Cookieless (`persistence: 'memory'`) until signin; cookie-based after (user accepted ToS) |

## Architecture

Stack: `posthog-js` on the Next.js 16 App Router frontend. FastAPI backend untouched.

### New files

```
frontend/
├── src/
│   ├── lib/
│   │   └── posthog.ts              # singleton init + re-export
│   ├── components/
│   │   └── PostHogProvider.tsx     # client component; init + auth-state listener
│   └── hooks/
│       └── useAnalytics.ts          # thin wrapper: useAnalytics().track(...)
└── .env.local                       # + NEXT_PUBLIC_POSTHOG_KEY, NEXT_PUBLIC_POSTHOG_HOST
```

### Modified files

- `app/providers.tsx` — add `<PostHogProvider>` to the provider chain.
- `app/(auth)/signin/page.tsx` — fire `signin_started` / `signin_failed`.
- Components for resume upload / job input / optimize / download / pricing / pdf-history — fire their respective events.

### Dependencies

- `posthog-js` (~50KB gzipped)

## Section 2 — Initialization and Consent

`lib/posthog.ts` exposes a singleton init:

```ts
import posthog from 'posthog-js'

let initialized = false

export function initPostHog() {
  if (initialized || typeof window === 'undefined') return
  if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return  // silently off in dev without a key

  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST, // https://eu.i.posthog.com
    persistence: 'memory',          // cookieless by default
    capture_pageview: true,
    capture_pageleave: true,
    autocapture: true,
    disable_session_recording: true,
  })
  initialized = true
}

export { posthog }
```

`components/PostHogProvider.tsx` is a client component that:

1. Calls `initPostHog()` on mount.
2. Subscribes to Supabase `onAuthStateChange`:
   - On `SIGNED_IN`: switch persistence to `localStorage+cookie`, then call `posthog.identify(user.id, { email, auth_provider, created_at })`. The switch preserves the current `distinct_id`, so anonymous events in the same session link back to the user.
   - On `SIGNED_OUT`: `posthog.reset()`, switch persistence back to `'memory'`.
3. Listens to `usePathname()` + `useSearchParams()` and calls `posthog.capture('$pageview')` on client-side navigation (autocapture does not reliably detect Next.js App Router transitions).

### Environment variables

```
NEXT_PUBLIC_POSTHOG_KEY=phc_xxx
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
```

Not secret (exposed to the browser by design), but dev and prod use separate PostHog projects.

## Section 3 — Event Catalogue

Thin wrapper hook:

```ts
export function useAnalytics() {
  return {
    track: (event: string, props?: Record<string, unknown>) =>
      posthog.capture(event, props),
  }
}
```

| Event | File | When | Properties |
|---|---|---|---|
| `signin_started` | `signin/page.tsx` | Click on signin button, before Supabase call | `method: 'email' \| 'telegram'` |
| `signin_completed` | `PostHogProvider` | In `onAuthStateChange` on `SIGNED_IN`, right after `identify()` | — |
| `signin_failed` | `signin/page.tsx` | catch block | `method`, `error` |
| `resume_uploaded` | Upload component | onChange file input | `format`, `size_kb` |
| `job_provided` | Job input form | onSubmit | `input_type: 'url' \| 'text'` |
| `optimization_started` | "Optimize" button | Before backend fetch | — |
| `optimization_completed` | Response handler | On success | `iterations`, `duration_sec` |
| `optimization_failed` | catch block | On failure | `error_type`, `stage` |
| `pdf_downloaded` | Download button | onClick | — |
| `pricing_viewed` | `pricing/page.tsx` | `useEffect(() => track(...), [])` | — |
| `pdf_history_viewed` | PDF history page | Same pattern | — |

PostHog auto-attaches: `distinct_id`, `session_id`, `$current_url`, `$referrer`, `$browser`, `$os`, `$device_type`, UTM parameters.

## Section 4 — Environments, Testing, Rollout

### Two PostHog projects

- `hr-breaker-dev` — localhost and Vercel preview deployments
- `hr-breaker-prod` — production domain only

Keys:
- Local: `.env.local` (already gitignored) → dev key
- Vercel: Environment Variables UI — Production = prod key, Preview/Development = dev key

### Dev-mode safety

`initPostHog()` is a no-op when `NEXT_PUBLIC_POSTHOG_KEY` is empty. A developer without a key in `.env.local` sends nothing.

Enable `posthog.debug()` when `NODE_ENV === 'development'`.

### Testing

1. Run locally with the dev key. Walk the full path: signin → upload → optimize → download.
2. In the dev PostHog project: **Live events** shows events in real time (~5 sec lag).
3. **Persons** shows a person with the Supabase `user.id` and email in properties.
4. Verify the anonymous `distinct_id` is aliased after `identify` (check `$anon_distinct_id` in first post-identify events).

### Rollout

1. Create two projects in PostHog EU Cloud, collect keys.
2. Implement, test locally with dev key.
3. Add prod key to Vercel, deploy.
4. Verify in production via incognito: walk the funnel, confirm events land in the prod project.
5. In PostHog, create a **Funnel** insight: `signin_completed → resume_uploaded → optimization_completed → pdf_downloaded`. This is the primary dashboard.

## Out of Scope (Deliberately)

- Session replay
- Feature flags / A/B tests
- Backend events from FastAPI
- Custom cookie banner (cookieless-until-signin removes the immediate need)
- Data exports / warehousing

Each becomes a separate task when there is concrete demand.

## Deviations from Plan (recorded 2026-04-18)

### 1. `job_provided` fires from `/optimize` page, not `JobInput` component

**Plan said:** instrument `frontend/src/components/JobInput.tsx` on submit.

**What shipped:** instrumented `frontend/src/app/(protected)/optimize/page.tsx` inside `handleOptimize`.

**Why:** `JobInput` is a controlled input — it has no submit event of its own; the parent owns the "Start Optimization" button. Firing on the parent's submit handler captures the actual commitment moment without adding a new callback prop to `JobInput`.

**Behavior:** `job_provided` fires once per optimize click, immediately before `optimization_started`. Properties: `{ input_type: "url" | "text" }`.

### 2. `optimization_failed` property names use available `OptimizationStatus` fields

**Plan said:** `{ error_type, stage }`.

**What shipped:** `error_type = OptimizationStatus.error` (the server error string), `stage = OptimizationStatus.current_step`.

**Why:** the `OptimizationStatus` type has `error: string | null` and `current_step: string | null`, not dedicated `error_type` / `stage` fields. Re-mapped to keep the agreed property names stable at the analytics layer.

### 3. `npm run lint` is broken project-wide (not introduced by this work)

**Plan said:** Task 13 runs `npm run lint`.

**What shipped:** Task 13 skipped. `next lint` was removed in Next 16; the `"lint": "next lint"` script in `frontend/package.json` now fails with `Invalid project directory provided: .../frontend/lint`. There is no `eslint.config.js` or legacy `.eslintrc.*` in `frontend/`, so a direct `npx eslint` invocation also fails.

**Why it does not block shipping:** `next build` type-checks the entire project on every commit and has passed cleanly after each task. That is the only working automated gate today.

**Follow-up (out of scope here):** a separate task should restore frontend linting — either by adopting `eslint.config.mjs` (ESLint 9 flat config, which ships with Next 16 scaffolds) or by removing the now-broken `lint` script.

