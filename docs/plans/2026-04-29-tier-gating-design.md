# Tier Gating & Multi-Plan Paywall Design

## Overview

Replace the single-tier paywall (€20/mo Pro + lifetime trial) with a three-tier model that already lives on the marketing landing page:

| Tier | Price | Optimizations | Coach / Cover Letter / Gap Analysis |
|------|-------|---------------|--------------------------------------|
| Free | €0 | 3 / rolling 7 days | ❌ |
| Job Hunter | €19 / month | unlimited | ❌ |
| Offer Mode | €29 / month | unlimited | ✅ |

Greenfield — no existing paying subscribers, no migration of users required.

Two paywall surfaces, not one:
- **`<UpgradeOverlay>`** — soft-gate over feature-locked pages (coach today; cover letter / gap analysis later). Page is rendered, content is blurred, an upgrade card sits on top.
- **`<QuotaBanner>`** — inline banner on `/optimize` for Free users approaching or hitting the weekly limit.

The old `/blocked` page is removed. The old addon-pack model is removed.

## Data Model — Supabase `profiles`

### Schema changes

```sql
ALTER TABLE profiles
  ADD COLUMN subscription_tier text DEFAULT 'free'
    CHECK (subscription_tier IN ('free','job_hunter','offer_mode')),
  ADD COLUMN weekly_reset_at timestamptz DEFAULT (now() + interval '7 days');

-- Normalize legacy status values
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'trial';

-- Drop unused columns
ALTER TABLE profiles
  DROP COLUMN request_count,
  DROP COLUMN addon_credits;
```

### Field semantics

| Field | Values | Meaning |
|---|---|---|
| `subscription_tier` | `free` / `job_hunter` / `offer_mode` | Single source of truth for tier. Updated by Stripe webhook. |
| `subscription_status` | `none` / `active` / `cancelled` | Stripe subscription state. `cancelled` = will not renew, but still inside paid period. |
| `subscription_id` | text \| null | Stripe subscription id (null for Free). |
| `current_period_end` | timestamptz \| null | Stripe billing-period end. Drives effective-tier logic for cancelled subs. |
| `period_request_count` | int | Optimizations used in current weekly window. Only relevant for Free. |
| `weekly_reset_at` | timestamptz | When the Free weekly window flips. Lazy-reset on each access check. |

### Initialization

On signup (Supabase auth trigger or post-signup API call):

```sql
INSERT INTO profiles (id, email, subscription_tier, subscription_status,
                      weekly_reset_at, period_request_count)
VALUES ($1, $2, 'free', 'none', now() + interval '7 days', 0);
```

### Effective-tier logic (downgrade & cancellation)

A user who pays for Offer Mode and cancels mid-cycle keeps Offer Mode access until `current_period_end`. Encapsulate this:

```python
def effective_tier(profile) -> str:
    if profile["subscription_status"] == "cancelled" \
       and profile["current_period_end"] \
       and now() < profile["current_period_end"]:
        return profile["subscription_tier"]  # paid through period
    if profile["subscription_status"] == "active":
        return profile["subscription_tier"]
    return "free"
```

The webhook flips `subscription_status` to `cancelled` immediately on cancel intent and resets `subscription_tier` to `free` only when `customer.subscription.deleted` fires (after period end).

## Backend — Access Control

### Feature matrix (`src/hr_breaker/services/tiers.py`)

```python
from enum import Enum

class Feature(str, Enum):
    OPTIMIZE = "optimize"
    COACH = "coach"
    COVER_LETTER = "cover_letter"
    GAP_ANALYSIS = "gap_analysis"

TIER_RANK = {"free": 0, "job_hunter": 1, "offer_mode": 2}

FEATURE_MIN_TIER: dict[Feature, str] = {
    Feature.OPTIMIZE: "free",         # gated by quota, not tier
    Feature.COACH: "offer_mode",
    Feature.COVER_LETTER: "offer_mode",
    Feature.GAP_ANALYSIS: "offer_mode",
}

FREE_WEEKLY_LIMIT = 3
```

This is the single source of truth on the backend. Adding a new gated feature = one line here + decorator on the route.

### Two access checks, not one

`check_feature_access(feature, profile)` — tier gate. Returns `AccessResult(allowed=False, reason="feature_locked", required_tier="offer_mode")` when user's effective tier is below the feature's minimum.

`check_quota(profile)` — quota gate, only meaningful for Free. Lazy-resets the weekly window before reading the counter:

```python
def maybe_reset_weekly_window(profile) -> dict:
    if now() >= profile["weekly_reset_at"]:
        return {
            **profile,
            "period_request_count": 0,
            "weekly_reset_at": now() + timedelta(days=7),
        }
    return profile
```

No cron. No background job. The reset happens on the next call from that user.

### FastAPI integration

```python
from fastapi import Depends, HTTPException

def require_feature(feature: Feature):
    def _dep(user = Depends(get_user)):
        result = check_feature_access(feature, user.profile)
        if not result.allowed:
            raise HTTPException(402, detail=result.to_dict())
        return user
    return _dep

@router.post("/coach/sessions")
async def create_coach_session(user = Depends(require_feature(Feature.COACH))):
    ...

@router.post("/optimize")
async def optimize(user = Depends(require_feature(Feature.OPTIMIZE)), ...):
    quota = check_quota(user.profile)
    if not quota.allowed:
        raise HTTPException(402, detail=quota.to_dict())
    # ... do work
    consume_request(user)  # noop for non-free tiers
```

`HTTP 402 Payment Required` lets the frontend distinguish "you can't do this — pay" from generic 403.

All `coach/*` and (later) `cover_letter/*`, `gap_analysis/*` routes get the decorator.

## Stripe Setup

### Dashboard configuration (one-time)

1. **Product**: `HR-Breaker Subscription`
2. **Prices** under that product:
   - `price_xxx_jh` — €19/month, recurring, `metadata.tier = "job_hunter"`
   - `price_yyy_om` — €29/month, recurring, `metadata.tier = "offer_mode"`
3. **Archive** the old €20/mo Pro price.

Env vars:
```
STRIPE_PRICE_JOB_HUNTER=price_xxx_jh
STRIPE_PRICE_OFFER_MODE=price_yyy_om
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_SECRET_KEY=sk_...
```

### Tier resolver — only place that maps Stripe → domain

```python
def tier_from_subscription(subscription) -> str:
    item = subscription["items"]["data"][0]
    return item["price"]["metadata"].get("tier", "free")
```

No hardcoded `if price_id == ...:` in the codebase. Adding a future tier = new price in Stripe + matrix update; webhook code unchanged.

### Webhook handlers

| Event | Action |
|---|---|
| `checkout.session.completed` | Read tier via `tier_from_subscription`. Set `subscription_tier`, `subscription_status='active'`, `subscription_id`, `current_period_end`. |
| `customer.subscription.updated` | Re-read tier (handles upgrade/downgrade). Sync `current_period_end`. If `cancel_at_period_end=true` → `status='cancelled'`. Tier stays until period end. |
| `customer.subscription.deleted` | `tier='free'`, `status='none'`, clear `subscription_id` and `current_period_end`. Reset weekly window: `period_request_count=0`, `weekly_reset_at=now()+7d`. |
| `invoice.payment_failed` | Log only. Stripe retries for ~3 weeks. Eventual `subscription.deleted` handles the final state. |

### Endpoints

```python
@router.post("/api/checkout")
async def checkout(tier: Literal["job_hunter","offer_mode"], user = Depends(get_user)):
    price_id = TIER_TO_PRICE_ID[tier]
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user.email,
        success_url=f"{FRONTEND_URL}/dashboard?upgraded={tier}",
        cancel_url=f"{FRONTEND_URL}/pricing",
        client_reference_id=user.id,
    )
    return {"url": session.url}

@router.post("/api/billing-portal")
async def billing_portal(user = Depends(get_user)):
    session = stripe.billing_portal.Session.create(
        customer=user.profile["stripe_customer_id"],
        return_url=f"{FRONTEND_URL}/dashboard",
    )
    return {"url": session.url}
```

Stripe's Billing Portal handles upgrade / downgrade / cancellation natively — no custom UI needed.

`GET /api/subscription` returns `{tier, status, remaining, weekly_reset_at, current_period_end}` — a single endpoint feeding all frontend gating.

**Removed**: `/api/checkout/subscription`, `/api/checkout/addon`. Both replaced by the universal `/api/checkout`.

## Frontend

### Mirror of feature matrix (`frontend/src/lib/tiers.ts`)

```ts
export type Tier = "free" | "job_hunter" | "offer_mode";
export const TIER_RANK: Record<Tier, number> = {
  free: 0, job_hunter: 1, offer_mode: 2,
};
export const FEATURE_MIN_TIER = {
  optimize: "free",
  coach: "offer_mode",
  cover_letter: "offer_mode",
  gap_analysis: "offer_mode",
} as const;

export function hasAccess(currentTier: Tier, feature: keyof typeof FEATURE_MIN_TIER): boolean {
  return TIER_RANK[currentTier] >= TIER_RANK[FEATURE_MIN_TIER[feature]];
}
```

The matrix is duplicated, not fetched. Backend remains the security boundary — the frontend matrix exists only for UX. If they drift, the user sees the page, hits the API, gets 402, and we render the same overlay anyway.

### Hooks

- Extend `useSubscription()` to return `{ tier, status, remaining, weeklyResetAt, currentPeriodEnd }` from `/api/subscription`.
- Add `useFeatureAccess(feature)` → `{ allowed, requiredTier, currentTier }`.

### `<UpgradeOverlay>`

```tsx
<UpgradeOverlay feature="coach">
  <CoachContent />
</UpgradeOverlay>
```

Behavior:
- If `hasAccess(tier, feature)` → render children as-is.
- Else → render children with `pointer-events-none blur-sm select-none` + a centered `<UpgradeCard requiredTier="offer_mode" />` modal-like overlay. The card shows tier name, price, headline benefit ("AI coach for interview prep"), and a primary CTA that calls `useCheckout(requiredTier)` to start Stripe Checkout.

Used immediately on `app/(protected)/coach/page.tsx`. Reused later for cover letter / gap analysis.

### `<QuotaBanner>`

Inline at the top of `app/(protected)/optimize/page.tsx`. Reads `remaining` and `weeklyResetAt` from `useSubscription()`:

| State | Render |
|---|---|
| Tier ≠ free, or remaining > 1 | `null` |
| Tier = free, remaining = 1 | Yellow banner: "Last optimization this week" |
| Tier = free, remaining = 0 | Red banner: "Used 3/3. Resets in N days. Upgrade to Job Hunter for unlimited →" + disable Optimize button |

If `/api/optimize` returns 402 with `reason=quota_exhausted`, force the banner to "remaining=0" state in client cache.

### Pricing page rewrite

`app/pricing/page.tsx` — replace the single Pro card with a 3-card layout. Reuse `_components/PricingSection.tsx` styling but make CTAs auth-aware:

| Current tier | Card | CTA |
|---|---|---|
| Anonymous | any | "Sign up" → `/signin?redirect=/pricing` |
| Free | Free | "Current plan" (disabled) |
| Free | Job Hunter / Offer Mode | "Subscribe" → `/api/checkout` |
| Job Hunter | Job Hunter | "Current plan" (disabled) |
| Job Hunter | Offer Mode | "Upgrade" → Billing Portal (proration applies) |
| Offer Mode | Offer Mode | "Manage subscription" → Billing Portal |
| Offer Mode | Job Hunter | "Downgrade" → Billing Portal |

### Navbar

The "Coach" link stays visible to all tiers. Soft-gate strategy = users discover the feature, click in, see the overlay, convert. No lock icon, no "Pro" badge.

### Removed

- `app/(protected)/blocked/` — entire route deleted.
- Addon checkout button & flow.
- Single-tier `/pricing` markup.

## Implementation Order

Two PRs, deployable independently:

**PR 1 — Backend + DB**
1. Run Supabase migration.
2. Create Stripe Product + Prices, archive old Pro price, set env vars.
3. Add `services/tiers.py`, rewrite `services/access_control.py`.
4. Add `require_feature` dependency, wrap `coach/*` routes.
5. Rewrite `webhooks.py` handlers.
6. Universalize `/api/checkout`, add `/api/billing-portal`, extend `/api/subscription`.
7. Delete `/api/checkout/addon`.

After PR 1: coach API returns 402 to non-Offer-Mode users. Frontend still shows old paywall — acceptable interim state.

**PR 2 — Frontend**
1. `lib/tiers.ts` matrix.
2. Extend `useSubscription`, add `useFeatureAccess`.
3. `<UpgradeOverlay>` and `<QuotaBanner>` components.
4. Wrap `coach/page.tsx` in `<UpgradeOverlay>`.
5. Add `<QuotaBanner>` to `optimize/page.tsx`, handle 402.
6. Rewrite `/pricing` with three tiers + auth-aware CTAs.
7. Delete `app/(protected)/blocked/`.

## QA Scenarios

- [ ] Fresh signup → tier = `free`, weekly window starts now+7d.
- [ ] Free user runs 3 optimizations → 4th call returns 402, banner shows "Resets in 7 days".
- [ ] Free user clicks Coach → overlay rendered, content blurred, CTA opens Offer Mode checkout.
- [ ] After Offer Mode checkout completes → tier = `offer_mode`, coach loads without overlay.
- [ ] Job Hunter clicks Coach → overlay (Job Hunter < Offer Mode); upgrade triggers Stripe proration.
- [ ] Cancel via Billing Portal → `status=cancelled`, tier preserved until `current_period_end`; coach still works.
- [ ] After `subscription.deleted` webhook → tier flips to `free`, weekly window resets.
- [ ] Free user past `weekly_reset_at` → next access check lazily resets `period_request_count` to 0.

## Out of Scope

- Annual billing.
- Team / organization accounts.
- Add-on credit packs (removed entirely).
- Pro-rated refunds beyond what Stripe Billing Portal provides.
- A/B testing of paywall copy.
- Email notifications when approaching weekly limit.
- Server-driven feature matrix (`/api/features`).
