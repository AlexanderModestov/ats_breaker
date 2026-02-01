# Paywall Design

## Overview

Freemium model with trial limits, paid subscriptions via Stripe, and admin overrides.

## Pricing Model

| Tier | Price | Requests | Reset |
|------|-------|----------|-------|
| Trial | Free | 3 total | Never |
| Subscription | €20/month | 50/month | Billing cycle anniversary |
| Add-on pack | €5 one-time | +10 | Never expires |

- Admin override users (via env var) get unlimited access
- After trial exhausted, user must subscribe to continue
- Subscribers who exhaust quota can buy add-on packs
- Cancelled subscriptions retain access until paid period ends

## Data Model

Add columns to `profiles` table:

```sql
ALTER TABLE profiles ADD COLUMN request_count integer DEFAULT 0;
ALTER TABLE profiles ADD COLUMN subscription_status text DEFAULT 'trial';
ALTER TABLE profiles ADD COLUMN subscription_id text;
ALTER TABLE profiles ADD COLUMN current_period_end timestamp;
ALTER TABLE profiles ADD COLUMN period_request_count integer DEFAULT 0;
ALTER TABLE profiles ADD COLUMN addon_credits integer DEFAULT 0;
```

**Column definitions:**
- `request_count` - Lifetime requests used (for trial tracking)
- `subscription_status` - One of: `trial`, `active`, `cancelled`, `expired`
- `subscription_id` - Stripe subscription ID
- `current_period_end` - When current billing cycle ends
- `period_request_count` - Requests used this billing period
- `addon_credits` - Purchased add-on requests remaining

## Stripe Integration

### Products to create in Stripe Dashboard

1. **HR-Breaker Pro** - €20/month recurring subscription
2. **Request Pack** - €5 one-time payment for +10 requests

### Environment Variables

```
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_SUBSCRIPTION=price_...
STRIPE_PRICE_ID_ADDON=price_...
UNLIMITED_USERS=admin@example.com,vip@example.com
```

### Webhook Events to Handle

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Activate subscription or add credits |
| `invoice.paid` | Reset `period_request_count` to 0, update `current_period_end` |
| `customer.subscription.updated` | Sync status changes |
| `customer.subscription.deleted` | Set status to `expired` |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/checkout/subscription` | POST | Create Stripe checkout session for subscription |
| `/api/checkout/addon` | POST | Create Stripe checkout session for add-on pack |
| `/api/webhooks/stripe` | POST | Handle Stripe webhook events |
| `/api/subscription` | GET | Get current user's subscription status and remaining requests |

## Access Control Logic

### Request Checking (before each optimization)

```python
def check_access(user) -> AccessResult:
    # 1. Admin override - unlimited access
    if user.email in UNLIMITED_USERS:
        return AccessResult(allowed=True, unlimited=True)

    # 2. Active subscriber
    if user.subscription_status == 'active' and now < user.current_period_end:
        remaining = 50 - user.period_request_count + user.addon_credits
        if remaining > 0:
            return AccessResult(allowed=True, remaining=remaining)
        else:
            return AccessResult(allowed=False, reason='quota_exhausted', can_buy_addon=True)

    # 3. Trial user
    if user.request_count < 3:
        return AccessResult(allowed=True, remaining=3 - user.request_count, is_trial=True)

    # 4. Trial exhausted, no subscription
    return AccessResult(allowed=False, reason='trial_exhausted', can_subscribe=True)
```

### Request Consumption (after successful optimization)

```python
def consume_request(user):
    if user.email in UNLIMITED_USERS:
        return  # don't count

    if user.subscription_status == 'active':
        if user.period_request_count < 50:
            user.period_request_count += 1
        else:
            user.addon_credits -= 1  # consume from add-on pack
    else:
        user.request_count += 1  # trial counter
```

## Frontend UI

### New Pages

#### `/pricing` - Subscription Page

Simple single-card layout:
- "HR-Breaker Pro - €20/month"
- "50 optimizations per month" bullet point
- "Subscribe" button → redirects to Stripe Checkout
- Accessible to logged-out users (redirects to login first)

#### `/blocked` - Access Denied Page

Two variants based on context:

**Trial exhausted:**
- "You've used your 3 free trials"
- "Subscribe to continue optimizing your resumes"
- Subscribe button

**Quota exhausted (subscribers):**
- "You've used all 50 requests this month"
- "Buy more requests or wait until [renewal date]"
- Buy add-on button + renewal date display

### Modifications to Existing Pages

#### `/optimize`

Before starting optimization:
1. Call access check
2. If blocked → redirect to `/blocked`
3. If ≤3 requests remaining → show warning banner: "You have X requests left"

#### Navigation/Header

- Trial users: no indicator (keep clean)
- Subscribers running low (≤3 left): subtle "3 requests left" badge
- Normal state: no visual clutter

### Stripe Checkout Flow

1. User clicks "Subscribe" or "Buy add-on"
2. Frontend calls `POST /api/checkout/subscription` or `/api/checkout/addon`
3. Backend creates Stripe checkout session, returns checkout URL
4. Frontend redirects to Stripe-hosted checkout page
5. After payment, Stripe redirects to `/dashboard?success=subscription` or `?success=addon`
6. Webhook updates database in background

## Edge Cases & Error Handling

### Webhook Delay

User pays but webhook hasn't arrived yet:
- After Stripe redirect, poll `/api/subscription` for a few seconds
- Show "Activating your subscription..." loading state
- Fallback message: "Payment received, access activating shortly"

### Payment Failure Mid-Subscription

- On `invoice.payment_failed` → don't immediately block (Stripe retries for ~3 weeks)
- Only set `expired` after receiving `customer.subscription.deleted`

### Invalid Add-on Purchase Attempt

- Add-on button only visible to active subscribers
- Backend validates `subscription_status == 'active'` before creating add-on checkout
- Return 403 if non-subscriber attempts to buy add-on

### Concurrent Optimization Race Condition

User has 1 request left, starts 2 optimizations simultaneously:
- Use database transaction with row lock when consuming request
- Second request gets blocked with "quota_exhausted" response

### Admin User Removed from Env

When unlimited user is removed from `UNLIMITED_USERS`:
- On next server restart, they become a normal user
- Their `request_count` may be high from previous usage
- Treated as trial exhausted → prompted to subscribe

## Implementation Checklist

### Backend
- [ ] Add columns to `profiles` table (Supabase migration)
- [ ] Add Stripe config to `config.py`
- [ ] Create `/api/checkout/subscription` endpoint
- [ ] Create `/api/checkout/addon` endpoint
- [ ] Create `/api/webhooks/stripe` endpoint
- [ ] Create `/api/subscription` endpoint
- [ ] Implement `check_access()` function
- [ ] Implement `consume_request()` function
- [ ] Add access check to `/api/optimize` endpoint
- [ ] Call `consume_request()` after successful optimization

### Frontend
- [ ] Create `/pricing` page
- [ ] Create `/blocked` page
- [ ] Add access check redirect to `/optimize`
- [ ] Add low-request warning banner
- [ ] Add success handling for checkout redirects
- [ ] Add subscription status to user context/state

### Stripe Setup
- [ ] Create "HR-Breaker Pro" subscription product (€20/month)
- [ ] Create "Request Pack" one-time product (€5)
- [ ] Configure webhook endpoint in Stripe Dashboard
- [ ] Add environment variables to deployment

## Out of Scope

- Multiple subscription tiers
- Annual billing option
- Team/organization accounts
- Usage analytics dashboard
- Refund handling (manual via Stripe Dashboard)
