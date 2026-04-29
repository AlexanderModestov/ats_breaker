# Tier Gating Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace single-tier paywall with three-tier (Free / Job Hunter / Offer Mode) model. Soft-gate Coach behind Offer Mode via `<UpgradeOverlay>`. Add `<QuotaBanner>` for Free quota on `/optimize`.

**Architecture:** Tier stored in `profiles.subscription_tier`, derived from Stripe `price.metadata.tier` in webhook. Single feature matrix in `services/tiers.py` (backend) and `lib/tiers.ts` (frontend mirror). Backend enforces via FastAPI `require_feature` dependency; returns HTTP 402 on violation. Frontend renders matching paywall surface.

**Tech Stack:** Python 3.10+ / FastAPI / Supabase / Stripe SDK / Next.js 16 / React 19 / TanStack Query.

**Reference design:** `docs/plans/2026-04-29-tier-gating-design.md`.

**Two-PR rollout:**
- **PR 1 (Tasks 1–10)** — Backend + DB. After merge: Coach API returns 402 to non-Offer-Mode users. Old frontend still shows old paywall (acceptable interim).
- **PR 2 (Tasks 11–18)** — Frontend. After merge: feature complete.

---

## Phase 1 — Backend + Database (PR 1)

### Task 1: Supabase migration

**Files:**
- Create: `supabase/migrations/20260429000000_tier_gating.sql`

**Step 1: Write the migration**

```sql
-- Add tier and weekly window
ALTER TABLE profiles
  ADD COLUMN subscription_tier text NOT NULL DEFAULT 'free'
    CHECK (subscription_tier IN ('free','job_hunter','offer_mode')),
  ADD COLUMN weekly_reset_at timestamptz NOT NULL DEFAULT (now() + interval '7 days');

-- Normalize legacy 'trial' status to 'none'; backfill all existing rows.
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'trial';
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'expired';

-- Drop deprecated columns
ALTER TABLE profiles
  DROP COLUMN IF EXISTS request_count,
  DROP COLUMN IF EXISTS addon_credits;
```

**Step 2: Apply locally**

Run: `supabase db push` (or via Supabase Studio SQL editor on dev project).
Expected: migration applies, no errors. Verify in Studio: `subscription_tier` column shows `free` for all rows; `request_count`/`addon_credits` gone.

**Step 3: Commit**

```bash
git add supabase/migrations/20260429000000_tier_gating.sql
git commit -m "feat(db): tier and weekly window columns on profiles"
```

---

### Task 2: Stripe Dashboard setup (manual, documented)

**Files:**
- Modify: `.env.example` — add `STRIPE_PRICE_JOB_HUNTER`, `STRIPE_PRICE_OFFER_MODE`; remove `STRIPE_PRICE_ID_SUBSCRIPTION`, `STRIPE_PRICE_ID_ADDON`
- Modify: `.env` (locally only, do not commit)

**Step 1: In Stripe Dashboard (test mode first)**

1. Products → Create product `HR-Breaker Subscription`
2. Add price: €19.00 / month / recurring → metadata key `tier` value `job_hunter` → save → copy `price_xxx`
3. Add price (same product): €29.00 / month / recurring → metadata key `tier` value `offer_mode` → save → copy `price_yyy`
4. Archive old €20 Pro price

**Step 2: Update `.env.example`**

```diff
-STRIPE_PRICE_ID_SUBSCRIPTION=price_...
-STRIPE_PRICE_ID_ADDON=price_...
+STRIPE_PRICE_JOB_HUNTER=price_...
+STRIPE_PRICE_OFFER_MODE=price_...
```

**Step 3: Update local `.env`** with the actual test-mode price IDs.

**Step 4: Commit**

```bash
git add .env.example
git commit -m "chore(env): rename stripe price env vars for tier model"
```

---

### Task 3: Feature matrix module — failing tests

**Files:**
- Create: `tests/test_tiers.py`

**Step 1: Write failing tests**

```python
"""Tests for tier feature matrix and effective-tier logic."""

from datetime import datetime, timezone, timedelta

import pytest

from hr_breaker.services.tiers import (
    Feature,
    TIER_RANK,
    FEATURE_MIN_TIER,
    FREE_WEEKLY_LIMIT,
    effective_tier,
    has_feature_access,
    maybe_reset_weekly_window,
)


def _profile(**overrides) -> dict:
    base = {
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    base.update(overrides)
    return base


class TestTierRank:
    def test_ranks_are_strictly_increasing(self):
        assert TIER_RANK["free"] < TIER_RANK["job_hunter"] < TIER_RANK["offer_mode"]


class TestFeatureMatrix:
    def test_optimize_available_to_free(self):
        assert FEATURE_MIN_TIER[Feature.OPTIMIZE] == "free"

    def test_coach_requires_offer_mode(self):
        assert FEATURE_MIN_TIER[Feature.COACH] == "offer_mode"


class TestEffectiveTier:
    def test_free_user_is_free(self):
        assert effective_tier(_profile()) == "free"

    def test_active_paying_user_returns_their_tier(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert effective_tier(p) == "offer_mode"

    def test_cancelled_but_paid_through_keeps_tier(self):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=future,
        )
        assert effective_tier(p) == "offer_mode"

    def test_cancelled_past_period_drops_to_free(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=past,
        )
        assert effective_tier(p) == "free"


class TestHasFeatureAccess:
    def test_free_can_optimize(self):
        assert has_feature_access(Feature.OPTIMIZE, _profile()) is True

    def test_free_cannot_coach(self):
        assert has_feature_access(Feature.COACH, _profile()) is False

    def test_job_hunter_cannot_coach(self):
        p = _profile(subscription_tier="job_hunter", subscription_status="active")
        assert has_feature_access(Feature.COACH, p) is False

    def test_offer_mode_can_coach(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert has_feature_access(Feature.COACH, p) is True


class TestWeeklyWindowReset:
    def test_does_not_reset_before_due(self):
        p = _profile(period_request_count=2)
        result = maybe_reset_weekly_window(p)
        assert result["period_request_count"] == 2

    def test_resets_after_due(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p = _profile(period_request_count=3, weekly_reset_at=past)
        result = maybe_reset_weekly_window(p)
        assert result["period_request_count"] == 0
        new_reset = datetime.fromisoformat(result["weekly_reset_at"])
        assert new_reset > datetime.now(timezone.utc) + timedelta(days=6)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: ImportError — `services.tiers` does not exist.

---

### Task 4: Feature matrix module — implementation

**Files:**
- Create: `src/hr_breaker/services/tiers.py`

**Step 1: Write minimal implementation**

```python
"""Tier definitions, feature matrix, and effective-tier logic."""

from datetime import datetime, timedelta, timezone
from enum import Enum


class Feature(str, Enum):
    OPTIMIZE = "optimize"
    COACH = "coach"
    COVER_LETTER = "cover_letter"
    GAP_ANALYSIS = "gap_analysis"


TIER_RANK: dict[str, int] = {"free": 0, "job_hunter": 1, "offer_mode": 2}

FEATURE_MIN_TIER: dict[Feature, str] = {
    Feature.OPTIMIZE: "free",
    Feature.COACH: "offer_mode",
    Feature.COVER_LETTER: "offer_mode",
    Feature.GAP_ANALYSIS: "offer_mode",
}

FREE_WEEKLY_LIMIT = 3


def _parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def effective_tier(profile: dict) -> str:
    """The tier the user can currently *use*, accounting for the cancellation grace period."""
    tier = profile.get("subscription_tier", "free")
    status = profile.get("subscription_status", "none")
    period_end = _parse_ts(profile.get("current_period_end"))
    now = datetime.now(timezone.utc)

    if status == "active":
        return tier
    if status == "cancelled" and period_end and now < period_end:
        return tier
    return "free"


def has_feature_access(feature: Feature, profile: dict) -> bool:
    user_rank = TIER_RANK[effective_tier(profile)]
    needed_rank = TIER_RANK[FEATURE_MIN_TIER[feature]]
    return user_rank >= needed_rank


def maybe_reset_weekly_window(profile: dict) -> dict:
    """Return profile with weekly counter reset if window expired. Pure function."""
    reset_at = _parse_ts(profile.get("weekly_reset_at"))
    now = datetime.now(timezone.utc)
    if reset_at is not None and now < reset_at:
        return profile
    return {
        **profile,
        "period_request_count": 0,
        "weekly_reset_at": (now + timedelta(days=7)).isoformat(),
    }
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: all green.

**Step 3: Commit**

```bash
git add src/hr_breaker/services/tiers.py tests/test_tiers.py
git commit -m "feat(backend): tier feature matrix and effective-tier logic"
```

---

### Task 5: Rewrite access_control — failing tests

**Files:**
- Modify: `tests/test_access_control.py` (replace contents)

**Step 1: Replace test file with new tier-aware tests**

```python
"""Tests for tier-aware access control."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from hr_breaker.services.access_control import (
    AccessResult,
    check_feature_access,
    check_quota,
    consume_request,
)
from hr_breaker.services.tiers import Feature, FREE_WEEKLY_LIMIT


def _profile(**overrides) -> dict:
    base = {
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    base.update(overrides)
    return base


class TestUnlimitedAdmin:
    def test_admin_bypasses_feature_check(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["admin@test.com"]
            r = check_feature_access(Feature.COACH, "admin@test.com", _profile())
        assert r.allowed and r.unlimited

    def test_admin_bypasses_quota(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["admin@test.com"]
            r = check_quota("admin@test.com", _profile(period_request_count=999))
        assert r.allowed and r.unlimited


class TestFeatureAccess:
    def _no_unlimited(self):
        m = patch("hr_breaker.services.access_control.get_settings")
        mock = m.start()
        mock.return_value.unlimited_users = []
        return m

    def test_free_blocked_from_coach(self):
        m = self._no_unlimited()
        r = check_feature_access(Feature.COACH, "u@test.com", _profile())
        m.stop()
        assert r.allowed is False
        assert r.reason == "feature_locked"
        assert r.required_tier == "offer_mode"

    def test_offer_mode_allowed_coach(self):
        m = self._no_unlimited()
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        r = check_feature_access(Feature.COACH, "u@test.com", p)
        m.stop()
        assert r.allowed is True


class TestQuota:
    def _no_unlimited(self):
        m = patch("hr_breaker.services.access_control.get_settings")
        mock = m.start()
        mock.return_value.unlimited_users = []
        return m

    def test_free_with_remaining(self):
        m = self._no_unlimited()
        p = _profile(period_request_count=1)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is True
        assert r.remaining == FREE_WEEKLY_LIMIT - 1

    def test_free_quota_exhausted(self):
        m = self._no_unlimited()
        p = _profile(period_request_count=FREE_WEEKLY_LIMIT)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is False
        assert r.reason == "quota_exhausted"
        assert r.renewal_date is not None

    def test_paid_user_unlimited(self):
        m = self._no_unlimited()
        p = _profile(subscription_tier="job_hunter", subscription_status="active",
                     period_request_count=999)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is True and r.unlimited

    def test_lazy_reset_when_window_expired(self):
        m = self._no_unlimited()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p = _profile(period_request_count=FREE_WEEKLY_LIMIT, weekly_reset_at=past)
        r = check_quota("u@test.com", p)
        m.stop()
        assert r.allowed is True
        assert r.remaining == FREE_WEEKLY_LIMIT  # full quota after reset


class TestConsumeRequest:
    def test_free_user_increments_period_counter(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = []
            updates = consume_request("u@test.com", _profile(period_request_count=0))
        assert updates["period_request_count"] == 1

    def test_paid_user_no_increment(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = []
            p = _profile(subscription_tier="offer_mode", subscription_status="active")
            updates = consume_request("u@test.com", p)
        assert updates == {}

    def test_admin_no_increment(self):
        with patch("hr_breaker.services.access_control.get_settings") as mock:
            mock.return_value.unlimited_users = ["a@test.com"]
            updates = consume_request("a@test.com", _profile())
        assert updates == {}
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_access_control.py -v`
Expected: ImportError on `check_feature_access`, `check_quota`.

---

### Task 6: Rewrite access_control — implementation

**Files:**
- Modify: `src/hr_breaker/services/access_control.py` (replace contents)

**Step 1: Replace file**

```python
"""Tier-aware access control: feature gates + Free-tier quota."""

from dataclasses import dataclass
from datetime import datetime, timezone

from hr_breaker.config import get_settings, logger
from hr_breaker.services.tiers import (
    Feature,
    FEATURE_MIN_TIER,
    FREE_WEEKLY_LIMIT,
    effective_tier,
    has_feature_access,
    maybe_reset_weekly_window,
)


@dataclass
class AccessResult:
    allowed: bool
    remaining: int | None = None
    unlimited: bool = False
    reason: str | None = None
    required_tier: str | None = None
    renewal_date: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "unlimited": self.unlimited,
            "reason": self.reason,
            "required_tier": self.required_tier,
            "renewal_date": self.renewal_date.isoformat() if self.renewal_date else None,
        }


def _is_unlimited(email: str) -> bool:
    return email.lower() in get_settings().unlimited_users


def check_feature_access(feature: Feature, email: str, profile: dict) -> AccessResult:
    """Tier gate. Returns blocked with required_tier when user's effective tier is too low."""
    if _is_unlimited(email):
        return AccessResult(allowed=True, unlimited=True)
    if has_feature_access(feature, profile):
        return AccessResult(allowed=True)
    return AccessResult(
        allowed=False,
        reason="feature_locked",
        required_tier=FEATURE_MIN_TIER[feature],
    )


def check_quota(email: str, profile: dict) -> AccessResult:
    """Quota gate. Only meaningful for Free tier; lazy-resets the weekly window."""
    if _is_unlimited(email):
        return AccessResult(allowed=True, unlimited=True)
    if effective_tier(profile) != "free":
        return AccessResult(allowed=True, unlimited=True)

    profile = maybe_reset_weekly_window(profile)
    used = profile.get("period_request_count", 0)
    if used >= FREE_WEEKLY_LIMIT:
        reset_at = datetime.fromisoformat(
            profile["weekly_reset_at"].replace("Z", "+00:00")
        )
        return AccessResult(
            allowed=False,
            remaining=0,
            reason="quota_exhausted",
            renewal_date=reset_at,
        )
    return AccessResult(allowed=True, remaining=FREE_WEEKLY_LIMIT - used)


def consume_request(email: str, profile: dict) -> dict:
    """Return profile field updates after a successful optimization. Only Free counts."""
    if _is_unlimited(email):
        return {}
    if effective_tier(profile) != "free":
        return {}
    used = profile.get("period_request_count", 0)
    return {"period_request_count": used + 1}
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_access_control.py tests/test_tiers.py -v`
Expected: all green.

**Step 3: Commit**

```bash
git add src/hr_breaker/services/access_control.py tests/test_access_control.py
git commit -m "feat(backend): rewrite access_control for tier model"
```

---

### Task 7: `require_feature` FastAPI dependency

**Files:**
- Modify: `src/hr_breaker/api/deps.py`
- Create: `tests/test_require_feature.py`

**Step 1: Write failing test**

```python
"""Test the require_feature FastAPI dependency."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from hr_breaker.api.deps import require_feature
from hr_breaker.services.tiers import Feature


def _profile(**o):
    base = {"subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 0,
            "weekly_reset_at": "2099-01-01T00:00:00+00:00"}
    base.update(o)
    return base


class TestRequireFeature:
    def test_allows_offer_mode_user_to_coach(self):
        with patch("hr_breaker.api.deps.get_settings") as s:
            s.return_value.unlimited_users = []
            supabase = MagicMock()
            supabase.get_profile.return_value = _profile(
                subscription_tier="offer_mode", subscription_status="active"
            )
            dep = require_feature(Feature.COACH)
            result = dep(user=("uid", "u@test.com"), supabase=supabase)
            assert result == ("uid", "u@test.com")

    def test_blocks_free_user_from_coach_with_402(self):
        with patch("hr_breaker.api.deps.get_settings") as s:
            s.return_value.unlimited_users = []
            supabase = MagicMock()
            supabase.get_profile.return_value = _profile()
            dep = require_feature(Feature.COACH)
            with pytest.raises(HTTPException) as exc:
                dep(user=("uid", "u@test.com"), supabase=supabase)
            assert exc.value.status_code == 402
            assert exc.value.detail["reason"] == "feature_locked"
            assert exc.value.detail["required_tier"] == "offer_mode"
```

**Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_require_feature.py -v`
Expected: ImportError on `require_feature`.

**Step 3: Add to `api/deps.py`**

Append:

```python
from hr_breaker.services.access_control import check_feature_access
from hr_breaker.services.tiers import Feature


def require_feature(feature: Feature):
    """FastAPI dependency factory: enforces tier requirement, raises 402 otherwise."""
    def _dep(
        user: CurrentUserWithEmail,
        supabase: SupabaseServiceDep,
    ):
        user_id, user_email = user
        profile = supabase.get_profile(user_id)
        if not profile:
            from fastapi import HTTPException
            raise HTTPException(404, "Profile not found")
        result = check_feature_access(feature, user_email or "", profile)
        if not result.allowed:
            from fastapi import HTTPException
            raise HTTPException(402, detail=result.to_dict())
        return user
    return _dep
```

**Step 4: Run test to verify pass**

Run: `uv run pytest tests/test_require_feature.py -v`
Expected: green.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/deps.py tests/test_require_feature.py
git commit -m "feat(api): require_feature dep returns 402 on tier violation"
```

---

### Task 8: Apply gating to coach + optimize routes

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py`
- Modify: `src/hr_breaker/api/routes/optimize.py`

**Step 1: Coach — wrap every route**

Find each `@router.<verb>` in `coach.py`. Replace `user: CurrentUser` (or similar) with the `require_feature` dep. Example:

```python
# Before
@router.post("/sessions")
async def create_coach_session(user: CurrentUser, ...): ...

# After
from hr_breaker.api.deps import require_feature
from hr_breaker.services.tiers import Feature

@router.post("/sessions")
async def create_coach_session(
    user: tuple[str, str | None] = Depends(require_feature(Feature.COACH)),
    ...
): ...
```

Apply to **all** mutating coach endpoints (sessions, messages, storybank). Read-only endpoints (e.g. `GET /sessions/:id`) should also be gated — the page is locked entirely.

**Step 2: Optimize — replace old `check_access` with new flow**

In `routes/optimize.py`:
1. Replace import `from hr_breaker.services.access_control import check_access` with `from hr_breaker.services.access_control import check_quota, consume_request`.
2. Add `from hr_breaker.services.tiers import Feature` and `from hr_breaker.api.deps import require_feature`.
3. The route that starts an optimization: change user dep to `Depends(require_feature(Feature.OPTIMIZE))`, then call `check_quota` to enforce free-tier limit. On block raise `HTTPException(402, detail=quota.to_dict())`.
4. After successful run, persist `consume_request(email, profile)` updates via `supabase.update_profile`.

**Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: all green. (Old `test_access_control.py::TestAdminAccess` cases removed; new tests pass.)

**Step 4: Boot the API to confirm import-clean**

Run: `uv run uvicorn hr_breaker.api.main:app --reload --port 8000` (Ctrl-C after it prints "Application startup complete").
Expected: no import errors, server starts.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/coach.py src/hr_breaker/api/routes/optimize.py
git commit -m "feat(api): gate coach behind Offer Mode, gate optimize on Free quota"
```

---

### Task 9: Rewrite Stripe webhook for tier model

**Files:**
- Modify: `src/hr_breaker/api/routes/webhooks.py`
- Modify: `src/hr_breaker/services/stripe_service.py` (add helper)
- Modify: `tests/test_webhooks.py`

**Step 1: Add `tier_from_subscription` helper to `StripeService`**

In `stripe_service.py`:

```python
@staticmethod
def tier_from_subscription(subscription) -> str:
    """Read tier from price.metadata.tier on the first subscription item."""
    try:
        item = subscription["items"]["data"][0]
        tier = item["price"].get("metadata", {}).get("tier")
        if tier in ("job_hunter", "offer_mode"):
            return tier
    except (KeyError, IndexError, AttributeError):
        pass
    return "free"
```

**Step 2: Write failing webhook tests**

Replace contents of `tests/test_webhooks.py` (or extend) with cases for the new tier mapping:

```python
class TestStripeWebhookTier:
    def test_checkout_completed_sets_tier(self, monkeypatch):
        # mock event with subscription metadata; assert update_profile called
        # with subscription_tier='offer_mode', subscription_status='active'
        ...

    def test_subscription_deleted_drops_to_free(self, monkeypatch):
        # assert update sets subscription_tier='free', status='none',
        # period_request_count=0, weekly_reset_at in future
        ...

    def test_subscription_updated_with_cancel_at_period_end(self, monkeypatch):
        # status='cancelled' but tier preserved
        ...
```

(Mirror the mocking style from existing webhook tests in the file. If the file already has fixtures for `stripe_service` and `supabase`, reuse them.)

**Step 3: Run tests to confirm failure**

Run: `uv run pytest tests/test_webhooks.py -v`
Expected: failures (new behavior not implemented).

**Step 4: Rewrite handlers in `webhooks.py`**

Replace the body of `handle_stripe_webhook` so each branch matches the design table:

```python
if event.type == "checkout.session.completed":
    session = event.data.object
    user_id = session.metadata.get("user_id")
    if not user_id or session.mode != "subscription":
        return {"status": "ok"}
    subscription = stripe_service.get_subscription(session.subscription)
    tier = stripe_service.tier_from_subscription(subscription)
    period_end = datetime.fromtimestamp(
        stripe_service.get_period_end(subscription), tz=timezone.utc
    )
    supabase.update_profile(user_id, {
        "subscription_tier": tier,
        "subscription_status": "active",
        "subscription_id": session.subscription,
        "stripe_customer_id": session.customer,
        "current_period_end": period_end.isoformat(),
    })

elif event.type == "customer.subscription.updated":
    subscription = event.data.object
    user_id = subscription.metadata.get("user_id")
    if not user_id:
        return {"status": "ok"}
    tier = stripe_service.tier_from_subscription(subscription)
    period_end = datetime.fromtimestamp(
        stripe_service.get_period_end(subscription), tz=timezone.utc
    )
    status = "cancelled" if subscription.cancel_at_period_end else "active"
    supabase.update_profile(user_id, {
        "subscription_tier": tier,
        "subscription_status": status,
        "current_period_end": period_end.isoformat(),
    })

elif event.type == "customer.subscription.deleted":
    subscription = event.data.object
    user_id = subscription.metadata.get("user_id")
    if not user_id:
        return {"status": "ok"}
    supabase.update_profile(user_id, {
        "subscription_tier": "free",
        "subscription_status": "none",
        "subscription_id": None,
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": (
            datetime.now(timezone.utc) + timedelta(days=7)
        ).isoformat(),
    })

elif event.type == "invoice.payment_failed":
    logger.warning(f"Stripe invoice payment failed for event {event.id}; awaiting retry")
```

Drop the addon branch entirely.

**Step 5: Run webhook tests**

Run: `uv run pytest tests/test_webhooks.py -v`
Expected: green.

**Step 6: Commit**

```bash
git add src/hr_breaker/api/routes/webhooks.py src/hr_breaker/services/stripe_service.py tests/test_webhooks.py
git commit -m "feat(webhooks): tier-aware Stripe event handlers"
```

---

### Task 10: Universalize checkout + extend `/api/subscription`

**Files:**
- Modify: `src/hr_breaker/api/routes/subscription.py`
- Modify: `src/hr_breaker/services/stripe_service.py`
- Modify: `src/hr_breaker/config.py`

**Step 1: Update settings in `config.py`**

```python
# Replace:
stripe_price_id_subscription: str = ""
stripe_price_id_addon: str = ""
# With:
stripe_price_job_hunter: str = ""
stripe_price_offer_mode: str = ""
```

**Step 2: Update `StripeService`** — single method for tier checkout:

```python
def create_checkout_session_for_tier(
    self, *, tier: str, user_id: str, user_email: str,
    success_url: str, cancel_url: str, stripe_customer_id: str | None,
) -> str:
    settings = get_settings()
    price_id = {
        "job_hunter": settings.stripe_price_job_hunter,
        "offer_mode": settings.stripe_price_offer_mode,
    }[tier]
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user_email if not stripe_customer_id else None,
        customer=stripe_customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=user_id,
        metadata={"user_id": user_id, "tier": tier},
        subscription_data={"metadata": {"user_id": user_id, "tier": tier}},
    )
    return session.url

def create_billing_portal_session(self, *, customer_id: str, return_url: str) -> str:
    session = stripe.billing_portal.Session.create(
        customer=customer_id, return_url=return_url,
    )
    return session.url
```

Delete the old `create_checkout_session_subscription` and `create_checkout_session_addon`.

**Step 3: Replace `subscription.py` route file**

```python
"""Subscription API routes — tier checkout, billing portal, status."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.config import logger
from hr_breaker.services.access_control import check_quota
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.supabase import SupabaseError
from hr_breaker.services.tiers import effective_tier

router = APIRouter()


class CheckoutRequest(BaseModel):
    tier: Literal["job_hunter", "offer_mode"]
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_url: str


class SubscriptionStatusResponse(BaseModel):
    tier: str                     # "free" | "job_hunter" | "offer_mode"
    status: str                   # "none" | "active" | "cancelled"
    remaining: int | None         # only Free; None for paid/unlimited
    is_unlimited: bool
    weekly_reset_at: str | None
    current_period_end: str | None


@router.get("", response_model=SubscriptionStatusResponse)
async def get_status(user: CurrentUserWithEmail, supabase: SupabaseServiceDep):
    user_id, email = user
    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    quota = check_quota(email or "", profile)
    return SubscriptionStatusResponse(
        tier=effective_tier(profile),
        status=profile.get("subscription_status", "none"),
        remaining=None if quota.unlimited else quota.remaining,
        is_unlimited=quota.unlimited,
        weekly_reset_at=profile.get("weekly_reset_at"),
        current_period_end=profile.get("current_period_end"),
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
):
    user_id, email = user
    if not email:
        raise HTTPException(400, "User email required")
    profile = supabase.get_profile(user_id) or {}
    try:
        url = StripeService().create_checkout_session_for_tier(
            tier=body.tier,
            user_id=user_id,
            user_email=email,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            stripe_customer_id=profile.get("stripe_customer_id"),
        )
        return CheckoutResponse(checkout_url=url)
    except StripeError as e:
        raise HTTPException(500, str(e)) from e


@router.post("/billing-portal", response_model=CheckoutResponse)
async def billing_portal(
    body: PortalRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
):
    user_id, _ = user
    profile = supabase.get_profile(user_id) or {}
    customer_id = profile.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(400, "No Stripe customer; subscribe first")
    try:
        url = StripeService().create_billing_portal_session(
            customer_id=customer_id, return_url=body.return_url,
        )
        return CheckoutResponse(checkout_url=url)
    except StripeError as e:
        raise HTTPException(500, str(e)) from e
```

The old `verify-checkout`, `/checkout/subscription`, `/checkout/addon` endpoints are removed.

**Step 4: Run full backend test suite**

Run: `uv run pytest tests/ -v`
Expected: green.

**Step 5: Smoke-boot the API**

Run: `uv run uvicorn hr_breaker.api.main:app --reload --port 8000`
Expected: no import errors. `Ctrl-C` after startup.

**Step 6: Commit**

```bash
git add src/hr_breaker/api/routes/subscription.py src/hr_breaker/services/stripe_service.py src/hr_breaker/config.py
git commit -m "feat(api): universal /checkout, /billing-portal, tier-aware /subscription"
```

---

**End of PR 1.** Open PR `feat: tier-aware backend (Phase 1)` against `dev`. After merge, frontend remains broken until PR 2 — coach API responds 402 to non-Offer-Mode users.

---

## Phase 2 — Frontend (PR 2)

### Task 11: Frontend tier matrix

**Files:**
- Create: `frontend/src/lib/tiers.ts`

**Step 1: Write the matrix**

```ts
export type Tier = "free" | "job_hunter" | "offer_mode";

export const TIER_RANK: Record<Tier, number> = {
  free: 0,
  job_hunter: 1,
  offer_mode: 2,
};

export const FEATURE_MIN_TIER = {
  optimize: "free",
  coach: "offer_mode",
  cover_letter: "offer_mode",
  gap_analysis: "offer_mode",
} as const satisfies Record<string, Tier>;

export type Feature = keyof typeof FEATURE_MIN_TIER;

export function hasAccess(currentTier: Tier, feature: Feature): boolean {
  return TIER_RANK[currentTier] >= TIER_RANK[FEATURE_MIN_TIER[feature]];
}

export const TIER_LABEL: Record<Tier, string> = {
  free: "Starter",
  job_hunter: "Job Hunter",
  offer_mode: "Offer Mode",
};
```

**Step 2: Type-check**

Run: `cd frontend && npm run lint`
Expected: no errors.

**Step 3: Commit**

```bash
git add frontend/src/lib/tiers.ts
git commit -m "feat(frontend): tier matrix and access helper"
```

---

### Task 12: Update types + API client + `useSubscription`

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/hooks/useSubscription.ts`

**Step 1: Update `SubscriptionStatus` type**

In `types/index.ts`, replace any old `SubscriptionStatus` type with:

```ts
import type { Tier } from "@/lib/tiers";

export type SubscriptionStatus = {
  tier: Tier;
  status: "none" | "active" | "cancelled";
  remaining: number | null;
  is_unlimited: boolean;
  weekly_reset_at: string | null;
  current_period_end: string | null;
};

export type CheckoutResponse = { checkout_url: string };
```

**Step 2: Update `api.ts` calls**

Replace `createSubscriptionCheckout`, `createAddonCheckout`, `verifyCheckout` with:

```ts
export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  return fetchWithAuth(`${API_BASE}/subscription`);
}

export async function createCheckout(
  tier: "job_hunter" | "offer_mode",
  successUrl: string,
  cancelUrl: string,
): Promise<CheckoutResponse> {
  return fetchWithAuth(`${API_BASE}/subscription/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tier, success_url: successUrl, cancel_url: cancelUrl }),
  });
}

export async function createBillingPortal(returnUrl: string): Promise<CheckoutResponse> {
  return fetchWithAuth(`${API_BASE}/subscription/billing-portal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ return_url: returnUrl }),
  });
}
```

**Step 3: Replace `useSubscription.ts`**

```ts
"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  getSubscriptionStatus,
  createCheckout,
  createBillingPortal,
} from "@/lib/api";
import type { Tier } from "@/lib/tiers";

export function useSubscription(options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
    staleTime: 30_000,
    refetchInterval: options?.refetchInterval,
  });
}

export function useCheckout() {
  return useMutation({
    mutationFn: async (tier: Exclude<Tier, "free">) => {
      const baseUrl = window.location.origin;
      return createCheckout(
        tier,
        `${baseUrl}/dashboard?upgraded=${tier}`,
        `${baseUrl}/pricing`,
      );
    },
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });
}

export function useBillingPortal() {
  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      return createBillingPortal(`${baseUrl}/dashboard`);
    },
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });
}
```

**Step 4: Type-check**

Run: `cd frontend && npm run lint`
Expected: TS errors only at call sites of removed functions — those will be cleaned up in later tasks.

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/hooks/useSubscription.ts
git commit -m "feat(frontend): tier-aware subscription hook and api client"
```

---

### Task 13: `<UpgradeOverlay>` component

**Files:**
- Create: `frontend/src/components/UpgradeOverlay.tsx`

**Step 1: Write the component**

```tsx
"use client";

import { ReactNode } from "react";
import { Lock } from "lucide-react";
import { useSubscription, useCheckout } from "@/hooks/useSubscription";
import { hasAccess, TIER_LABEL, type Feature, type Tier } from "@/lib/tiers";
import { FEATURE_MIN_TIER } from "@/lib/tiers";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = { feature: Feature; children: ReactNode };

const TIER_PRICE: Record<Exclude<Tier, "free">, string> = {
  job_hunter: "€19/month",
  offer_mode: "€29/month",
};

export function UpgradeOverlay({ feature, children }: Props) {
  const { data: sub, isLoading } = useSubscription();
  const checkout = useCheckout();

  if (isLoading) return <>{children}</>;
  const tier = sub?.tier ?? "free";
  if (hasAccess(tier, feature)) return <>{children}</>;

  const required = FEATURE_MIN_TIER[feature] as Exclude<Tier, "free">;

  return (
    <div className="relative">
      <div className="pointer-events-none select-none blur-sm opacity-60">
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="max-w-sm rounded-2xl border border-border bg-card p-6 shadow-lg text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <Lock className="h-5 w-5 text-primary" />
          </div>
          <h3 className="text-lg font-semibold">
            Available in {TIER_LABEL[required]}
          </h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Upgrade to {TIER_LABEL[required]} to unlock this feature.
          </p>
          <p className="mt-3 text-2xl font-bold">{TIER_PRICE[required]}</p>
          <Button
            className="mt-4 w-full"
            onClick={() => checkout.mutate(required)}
            disabled={checkout.isPending}
          >
            {checkout.isPending ? "Loading..." : `Upgrade to ${TIER_LABEL[required]}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Type-check**

Run: `cd frontend && npm run lint`
Expected: green for this file (other files may still have errors from Task 12).

**Step 3: Commit**

```bash
git add frontend/src/components/UpgradeOverlay.tsx
git commit -m "feat(frontend): UpgradeOverlay soft-gate component"
```

---

### Task 14: Wrap coach page

**Files:**
- Modify: `frontend/src/app/(protected)/coach/page.tsx`

**Step 1: Wrap the page**

At top of file:
```tsx
import { UpgradeOverlay } from "@/components/UpgradeOverlay";
```

Wrap the entire returned `<motion.div>...</motion.div>` in `<UpgradeOverlay feature="coach">...</UpgradeOverlay>`.

**Step 2: Manual verification**

Run: `cd frontend && npm run dev` (background) and `uv run uvicorn hr_breaker.api.main:app --reload --port 8000` (separate terminal).

In a browser session as a Free user:
- Navigate to `/coach`. Expected: page content blurred, upgrade card centered with "Available in Offer Mode" + "€29/month" + button.
- Click upgrade button. Expected: redirected to Stripe Checkout for offer_mode price.

In a browser session as an Offer Mode test user (use a unlimited admin account or a user with `subscription_tier='offer_mode'` in DB):
- Navigate to `/coach`. Expected: full UI, no overlay, can select position, can chat.

**Step 3: Commit**

```bash
git add frontend/src/app/(protected)/coach/page.tsx
git commit -m "feat(coach): soft-gate coach behind Offer Mode"
```

---

### Task 15: `<QuotaBanner>` + optimize page integration

**Files:**
- Create: `frontend/src/components/QuotaBanner.tsx`
- Modify: `frontend/src/app/(protected)/optimize/page.tsx`

**Step 1: Write `QuotaBanner.tsx`**

```tsx
"use client";

import Link from "next/link";
import { AlertCircle } from "lucide-react";
import { useSubscription } from "@/hooks/useSubscription";

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

export function QuotaBanner() {
  const { data: sub } = useSubscription();
  if (!sub || sub.tier !== "free" || sub.is_unlimited) return null;

  const remaining = sub.remaining ?? 0;
  if (remaining > 1) return null;

  const days = daysUntil(sub.weekly_reset_at);

  if (remaining === 1) {
    return (
      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm">
        Last optimization this week.
        <Link href="/pricing" className="ml-2 underline">
          Upgrade for unlimited →
        </Link>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm flex items-center gap-2">
      <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
      <span>
        Used 3/3 this week. Resets in {days ?? "?"} day{days === 1 ? "" : "s"}.
      </span>
      <Link href="/pricing" className="ml-auto underline">
        Upgrade →
      </Link>
    </div>
  );
}
```

**Step 2: Mount on `/optimize` and disable submit when quota=0**

In `app/(protected)/optimize/page.tsx`:
1. Import: `import { QuotaBanner } from "@/components/QuotaBanner";` and `import { useSubscription } from "@/hooks/useSubscription";`
2. Render `<QuotaBanner />` at the top of the form area.
3. Read `const { data: sub } = useSubscription();`. Pass `disabled={sub?.tier === "free" && sub?.remaining === 0}` to the Optimize submit button.
4. In the optimize mutation `onError`, if `error.status === 402`, refetch `["subscription"]` so the banner flips to red:
   ```ts
   onError: (err) => {
     if (err?.status === 402) queryClient.invalidateQueries({ queryKey: ["subscription"] });
   }
   ```

**Step 3: Manual verification**

In a Free test user session (set `period_request_count=2` in DB):
- Banner shows yellow "Last optimization this week".
- Run an optimization → banner disappears (or flips to red after success when count hits 3).
- Try another optimization → button disabled and red banner.

**Step 4: Commit**

```bash
git add frontend/src/components/QuotaBanner.tsx frontend/src/app/(protected)/optimize/page.tsx
git commit -m "feat(optimize): inline QuotaBanner for Free tier"
```

---

### Task 16: Rewrite `/pricing` with three tiers

**Files:**
- Modify: `frontend/src/app/pricing/page.tsx`

**Step 1: Replace with three-card layout**

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { useSubscription, useCheckout, useBillingPortal } from "@/hooks/useSubscription";
import { useAnalytics } from "@/hooks/useAnalytics";
import { TIER_LABEL, type Tier } from "@/lib/tiers";

const PLANS: { tier: Tier; price: string; tagline: string; features: string[]; highlighted?: boolean }[] = [
  {
    tier: "free", price: "€0",
    tagline: "Try it out",
    features: ["3 optimizations / week", "Basic ATS", "PDF export"],
  },
  {
    tier: "job_hunter", price: "€19 /month",
    tagline: "Get more interviews",
    features: ["Unlimited optimizations", "Full ATS score", "PDF & DOCX", "Version history"],
    highlighted: true,
  },
  {
    tier: "offer_mode", price: "€29 /month",
    tagline: "Get the offer",
    features: ["Everything in Job Hunter", "AI Coach", "Cover letters", "Gap analysis"],
  },
];

export default function PricingPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { data: sub } = useSubscription();
  const checkout = useCheckout();
  const portal = useBillingPortal();
  const { track } = useAnalytics();

  useEffect(() => { track("pricing_viewed"); }, [track]);

  const ctaFor = (tier: Tier) => {
    if (!isAuthenticated) {
      return { label: "Sign up", onClick: () => router.push("/signin?redirect=/pricing"), disabled: false };
    }
    const current = sub?.tier ?? "free";
    if (tier === current) {
      return tier === "free"
        ? { label: "Current plan", onClick: () => {}, disabled: true }
        : { label: "Manage subscription", onClick: () => portal.mutate(), disabled: portal.isPending };
    }
    if (tier === "free") {
      return { label: "Downgrade", onClick: () => portal.mutate(), disabled: portal.isPending };
    }
    return {
      label: current === "free" ? "Subscribe" : "Switch plan",
      onClick: () => checkout.mutate(tier as Exclude<Tier, "free">),
      disabled: checkout.isPending,
    };
  };

  return (
    <div className="container mx-auto px-4 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-bold">Pricing</h1>
        <p className="mt-2 text-muted-foreground">Choose the plan that fits your job search</p>
      </div>
      <div className="mt-12 grid gap-6 md:grid-cols-3 max-w-5xl mx-auto">
        {PLANS.map((plan) => {
          const cta = ctaFor(plan.tier);
          return (
            <Card key={plan.tier} className={plan.highlighted ? "border-2 border-primary" : ""}>
              <CardHeader>
                <CardTitle>{TIER_LABEL[plan.tier]}</CardTitle>
                <CardDescription>{plan.tagline}</CardDescription>
                <div className="mt-2 text-3xl font-bold">{plan.price}</div>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {plan.features.map((f) => (
                    <li key={f} className="flex gap-2">
                      <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
              <CardFooter>
                <Button className="w-full" onClick={cta.onClick} disabled={cta.disabled}>
                  {cta.label}
                </Button>
              </CardFooter>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 2: Manual verification**

`cd frontend && npm run dev`. Visit `/pricing`:
- Anonymous → all three CTAs say "Sign up".
- Free user → Free shows "Current plan" disabled; Job Hunter shows "Subscribe"; Offer Mode shows "Subscribe".
- Job Hunter user → Job Hunter shows "Manage subscription"; Offer Mode shows "Switch plan"; Free shows "Downgrade".
- Offer Mode user → Offer Mode shows "Manage subscription"; others show "Switch plan" / "Downgrade".

**Step 3: Commit**

```bash
git add frontend/src/app/pricing/page.tsx
git commit -m "feat(pricing): three-tier auth-aware pricing page"
```

---

### Task 17: Delete `/blocked` route + dead frontend code

**Files:**
- Delete: `frontend/src/app/(protected)/blocked/` (whole directory)
- Modify: any files that import from `@/app/(protected)/blocked` or call removed APIs

**Step 1: Delete blocked route**

```bash
rm -rf frontend/src/app/\(protected\)/blocked
```

**Step 2: Find and fix dangling references**

```bash
cd frontend && npx tsc --noEmit
```

Expected errors will point at:
- Imports of `useAddonCheckout` / `useVerifyCheckout` (deleted in Task 12) — remove.
- References to `/blocked` redirect URLs — replace with `/pricing`.
- Old `SubscriptionStatus` field names (`is_trial`, `can_buy_addon`, `renewal_date`) — replace with new fields per Task 12.

Fix each, re-run tsc until clean.

**Step 3: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds.

**Step 4: Commit**

```bash
git add -A
git commit -m "chore(frontend): remove /blocked route and addon-era code"
```

---

### Task 18: End-to-end QA

**Step 1: Boot both servers**

Terminal A: `uv run uvicorn hr_breaker.api.main:app --reload --port 8000`
Terminal B: `cd frontend && npm run dev`

**Step 2: Walk every QA scenario from design doc**

For each, note pass/fail. Use Stripe test cards (4242 4242 4242 4242).

- [ ] Fresh Supabase user signup → `subscription_tier='free'`, `weekly_reset_at` ~7 days out, `period_request_count=0`.
- [ ] Free user runs 3 optimizations → 4th attempt: button disabled, red banner with "Resets in 7 days".
- [ ] Free user clicks Coach in nav → page renders blurred with overlay.
- [ ] Click "Upgrade to Offer Mode" → Stripe Checkout → complete with test card → redirected to `/dashboard?upgraded=offer_mode`.
- [ ] After webhook: profile shows `tier='offer_mode'`, `status='active'`, `current_period_end` ~30 days.
- [ ] Coach loads without overlay; can chat normally.
- [ ] In Stripe Dashboard, cancel the subscription → wait for webhook → profile shows `status='cancelled'` but `tier='offer_mode'` still; Coach still works.
- [ ] In Stripe Dashboard, end the period (or wait): `subscription.deleted` fires → profile flips `tier='free'`, `status='none'`, weekly window reset.
- [ ] Coach now shows overlay again.
- [ ] Free user past `weekly_reset_at` (manually back-date the field): next access call lazily resets `period_request_count` to 0.
- [ ] Job Hunter test user (manually set `tier='job_hunter'`, `status='active'` in DB) → can run unlimited optimizations; Coach shows overlay needing Offer Mode upgrade.

**Step 3: Run full backend test suite one more time**

Run: `uv run pytest tests/ -v`
Expected: all green.

**Step 4: Final commit only if any QA fixes needed**

```bash
git add -A
git commit -m "chore: QA polish"
```

---

**End of PR 2.** Open PR `feat: tier-aware frontend (Phase 2)` against `dev`. After merge, multi-tier paywall is feature-complete.

---

## Out of Scope

- Annual billing.
- Team accounts.
- Add-on credit packs.
- Email notifications when approaching weekly limit.
- Server-driven feature matrix (`/api/features`).
- A/B testing of paywall copy.
- Migrating any existing paying users (none exist — confirmed greenfield).
