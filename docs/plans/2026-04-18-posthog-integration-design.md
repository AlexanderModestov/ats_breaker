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
