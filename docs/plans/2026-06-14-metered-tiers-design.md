# Metered Tiers & Transparent Pricing Limits — Design

## Overview

Replace the current "unlimited paid tiers + renewable Free" model with **metered limits on every tier**, and surface those limits transparently on the pricing page.

| Tier | Price | Optimizations | Coach chats | Messages / chat | Reset |
|------|-------|---------------|-------------|-----------------|-------|
| Free | €0 | 3 | 1 | 15 | never (lifetime) |
| Job Hunter | €19 / month | 20 | 1 | 15 | each billing month |
| Offer Mode | €29 / month | 40 | 10 | 20 | each billing month |

Two structural shifts from today:

1. **Free becomes one-time.** Today a Free user gets 3 optimizations per rolling 7 days (renewable). Now it is 3 total, forever.
2. **Paid tiers are no longer unlimited.** Both Job Hunter and Offer Mode are unlimited today; now they have monthly caps (20 / 40 optimizations).

**Reset is billing-driven.** When Stripe signals the start of a new paid month, both counters (optimizations + coach chats) reset to 0. Free has no such event, so its counters never reset — that *is* the lifetime behaviour. One mechanism, the only difference is whether a reset event arrives.

**Anti-abuse.** On downgrade to Free, counters are **not** reset. Otherwise "subscribe → cancel → 3 free again" gives infinite Free. The current `subscription.deleted` handler resets the weekly window — that behaviour is removed.

The concept of "unlimited" disappears entirely from the code. Every tier has a concrete cap.

## Data Model — `profiles`

| Column | Today | After |
|--------|-------|-------|
| `period_request_count` | optimizations counter (Free only) | optimizations counter for **all tiers** |
| `coach_threads_created_total` | lifetime chat counter | rename → `coach_chats_used` (chats in current period) |
| `weekly_reset_at` | Free weekly window | **dropped** — reset is billing-driven, no lazy window |

The trick: both `period_request_count` and `coach_chats_used` reset on the same event (start of a new billing month). Free never receives that event, so both grow monotonically → lifetime. One column serves both behaviours; the only difference is whether a reset fires.

The per-chat message cap (15/15/20) is **not** stored — it is computed live from the count of `UserPromptPart` in `coach_messages`, with the ceiling looked up from the tier config.

**Atomicity.** Optimizations are currently consumed via read-then-write in Python (TOCTOU race — concurrent requests can slip past the cap). This was harmless when only Free was metered. Now that paid tiers are metered too, introduce a generic Postgres RPC `consume_quota(p_user_id, p_column, p_limit)` — an atomic `UPDATE ... SET col = col + 1 WHERE col < limit RETURNING`. Also delete the dead `consume_request` function from migration 006 (it references the long-dropped `addon_credits` / `request_count` columns).

Migration `018_metered_tiers.sql`: rename column, drop `weekly_reset_at`, add the `consume_quota` RPC.

## Backend — Access Control

Collapse the scattered constants (`FREE_WEEKLY_LIMIT`, `FREE_COACH_THREADS`, `FREE_COACH_TURNS`) and the `coach_is_unlimited` branch into a single source of truth in `tiers.py`:

```python
TIER_LIMITS = {
    "free":       {"optimizations": 3,  "coach_chats": 1,  "coach_msgs": 15},
    "job_hunter": {"optimizations": 20, "coach_chats": 1,  "coach_msgs": 15},
    "offer_mode": {"optimizations": 40, "coach_chats": 10, "coach_msgs": 20},
}
```

**Removed:** `coach_is_unlimited`, `maybe_reset_weekly_window`, the `FREE_*` constants, the `AccessResult.unlimited` field, and the coach tier-gate (coach is already open to all tiers; quota gates it, not tier).

**Three checks**, all reading the limit via `TIER_LIMITS[effective_tier(profile)]`:

1. `check_optimization_quota(profile)` → `used = period_request_count`, `limit = ...["optimizations"]`. Returns `remaining` and `renewal_date` (= `current_period_end` for paid; `None` for Free).
2. `check_coach_chat_quota(profile)` → `used = coach_chats_used`, `limit = ...["coach_chats"]`. Gates new-chat creation.
3. `check_coach_turn_limit(history, profile)` → counts user turns in the thread, `limit = ...["coach_msgs"]`. Same mechanic as today, limit from config.

`_is_unlimited(email)` (admin allowlist from settings) stays — it is an emergency bypass for the team, not part of the tier model.

Consumption uses the atomic RPC: `consume_quota(user_id, "period_request_count", limit)` for optimizations and `consume_quota(user_id, "coach_chats_used", limit)` on chat creation.

## Webhooks — Billing-Driven Reset

Add the "new paid month" handler. Stripe sends this as `invoice.paid` with `billing_reason = "subscription_cycle"`:

```python
elif event.type == "invoice.paid":
    invoice = event.data.object
    if invoice.billing_reason == "subscription_cycle":
        user_id = ...  # from subscription.metadata
        supabase.update_profile(user_id, {
            "period_request_count": 0,
            "coach_chats_used": 0,
            "current_period_end": new_period_end.isoformat(),
        })
```

Only `subscription_cycle` — this excludes the first payment (`subscription_create`), where no reset is needed (counters are already 0 after upgrade).

**Three edits to existing handlers:**

1. **`customer.subscription.deleted`** — today it zeroes `period_request_count` and sets `weekly_reset_at`. Per the anti-abuse decision, **remove the zeroing**. On downgrade to Free, counters are preserved. `weekly_reset_at` no longer exists. Only tier/status change remains.
2. **Upgrade Free → paid** (`checkout.session.completed`) — **zero** `period_request_count` and `coach_chats_used`, otherwise a user who spent 3/3 on Free enters Job Hunter already at 3 used. Paid = fresh quota.
3. **Upgrade/downgrade between paid tiers** (`customer.subscription.updated`) — Stripe prorates and typically issues an invoice → `invoice.paid` fires and resets the counters. No separate logic; rely on `invoice.paid`. Giving fresh 40 on the move to Offer Mode is intended.

**Risk:** if `invoice.paid` is lost, counters never reset and a paid user is stuck. Stripe retries for ~3 days, and the admin allowlist exists as a manual escape hatch. Accepted; no lazy `current_period_end` safety-net (YAGNI).

## Frontend

**1. Pricing page — transparent limits table.** Replace "unlimited optimizations" / coach-trial copy with concrete numbers per tier:

| | Free | Job Hunter €19 | Offer Mode €29 |
|---|---|---|---|
| Optimizations | 3 total | 20 / month | 40 / month |
| Coach | 1 chat, 15 messages | 1 chat, 15 messages | 10 chats, 20 messages |

Numbers come from the same `TIER_LIMITS`, mirrored into `frontend/src/lib/tiers.ts` (as the feature matrix already is; backend stays the security boundary). This *is* "write the limits on the landing page."

**2. `/api/subscription`** — symmetric structure, no `is_unlimited`:

```json
{
  "tier": "offer_mode",
  "optimizations": { "used": 12, "limit": 40, "remaining": 28, "renews_at": "..." },
  "coach": { "chats_used": 3, "chats_limit": 10, "msgs_per_chat": 20 }
}
```

For Free, `renews_at: null` → the UI says "does not renew" instead of "resets on N".

**3. Existing components, minimal edits:**

- `QuotaBanner` (on `/optimize`) — already reads `remaining`; now applies to **all** tiers. At 18/20 → "2 left"; at 0 → "limit reached, renews on N".
- `CoachSidebar` / `CoachChat` — chips "X of N chats / X of N messages" from the API response, not hardcoded 3/5. Remove `is_unlimited` branches.
- `UpgradeOverlay` — on Offer Mode there is nothing to upsell (top tier), so the copy becomes "limit renews on N" **with no upgrade button**.

Copy added in EN + RU in `translations.ts`.

## Out of Scope

- Legal disclaimers / acceptable-use rules on the landing page (user chose numbers-only).
- Annual billing.
- Lazy `current_period_end` safety-net for missed `invoice.paid` webhooks.
- Carrying unused quota over to the next month (no rollover).
- Migrating existing paying subscribers' usage history (greenfield-ish; counters start where they are).
- Per-tier coach model/prompt differences.
