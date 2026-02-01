# Paywall Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a freemium paywall with 3 free trial requests, €20/month subscription (50 requests), and €5 add-on packs (+10 requests).

**Architecture:** Add subscription columns to profiles table, create Stripe checkout/webhook endpoints, add access control middleware that checks request limits before optimization, and build frontend pricing/blocked pages.

**Tech Stack:** Stripe Python SDK, FastAPI, Supabase PostgreSQL, Next.js, React Query

---

## Task 1: Database Migration - Add Subscription Columns

**Files:**
- Create: `supabase/migrations/005_subscription_columns.sql`

**Step 1: Write the migration SQL**

```sql
-- Add subscription columns to profiles table
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'trial'
    CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired')),
ADD COLUMN IF NOT EXISTS subscription_id TEXT,
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS period_request_count INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS addon_credits INTEGER NOT NULL DEFAULT 0;

-- Create index for subscription status queries
CREATE INDEX IF NOT EXISTS idx_profiles_subscription_status ON profiles(subscription_status);
```

**Step 2: Apply migration locally**

Run: `supabase db push` (or apply via Supabase dashboard)

**Step 3: Commit**

```bash
git add supabase/migrations/005_subscription_columns.sql
git commit -m "feat: add subscription columns to profiles table"
```

---

## Task 2: Backend Config - Add Stripe Settings

**Files:**
- Modify: `src/hr_breaker/config.py`

**Step 1: Add Stripe settings to Settings class**

In `src/hr_breaker/config.py`, add these fields to the `Settings` class after the Supabase settings (around line 49):

```python
    # Stripe settings
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_subscription: str = ""
    stripe_price_id_addon: str = ""

    # Paywall settings
    unlimited_users: list[str] = []
    trial_request_limit: int = 3
    subscription_request_limit: int = 50
    addon_request_count: int = 10
```

**Step 2: Parse env vars in get_settings()**

Add to the `get_settings()` function return statement (around line 96):

```python
        # Stripe settings
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
        stripe_price_id_subscription=os.getenv("STRIPE_PRICE_ID_SUBSCRIPTION", ""),
        stripe_price_id_addon=os.getenv("STRIPE_PRICE_ID_ADDON", ""),
        # Paywall settings
        unlimited_users=_parse_unlimited_users(os.getenv("UNLIMITED_USERS", "")),
        trial_request_limit=int(os.getenv("TRIAL_REQUEST_LIMIT", "3")),
        subscription_request_limit=int(os.getenv("SUBSCRIPTION_REQUEST_LIMIT", "50")),
        addon_request_count=int(os.getenv("ADDON_REQUEST_COUNT", "10")),
```

**Step 3: Add helper function for parsing unlimited users**

Add before `get_settings()`:

```python
def _parse_unlimited_users(value: str) -> list[str]:
    """Parse unlimited users from comma-separated string."""
    if not value:
        return []
    return [email.strip().lower() for email in value.split(",") if email.strip()]
```

**Step 4: Commit**

```bash
git add src/hr_breaker/config.py
git commit -m "feat: add Stripe and paywall config settings"
```

---

## Task 3: Backend - Create Access Control Service

**Files:**
- Create: `src/hr_breaker/services/access_control.py`

**Step 1: Create the access control service**

```python
"""Access control service for paywall enforcement."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hr_breaker.config import get_settings, logger


@dataclass
class AccessResult:
    """Result of an access check."""

    allowed: bool
    remaining: int | None = None
    unlimited: bool = False
    is_trial: bool = False
    reason: str | None = None
    can_subscribe: bool = False
    can_buy_addon: bool = False
    renewal_date: datetime | None = None


def check_access(user_email: str, profile: dict[str, Any]) -> AccessResult:
    """
    Check if a user has access to make optimization requests.

    Args:
        user_email: The user's email address
        profile: The user's profile data from database

    Returns:
        AccessResult with access decision and details
    """
    settings = get_settings()

    # 1. Admin override - unlimited access
    if user_email.lower() in settings.unlimited_users:
        logger.debug(f"User {user_email} has unlimited access")
        return AccessResult(allowed=True, unlimited=True)

    subscription_status = profile.get("subscription_status", "trial")
    current_period_end = profile.get("current_period_end")
    period_request_count = profile.get("period_request_count", 0)
    addon_credits = profile.get("addon_credits", 0)
    request_count = profile.get("request_count", 0)

    # Parse current_period_end if it's a string
    if isinstance(current_period_end, str):
        current_period_end = datetime.fromisoformat(current_period_end.replace("Z", "+00:00"))

    now = datetime.now(timezone.utc)

    # 2. Active subscriber
    if subscription_status == "active" and current_period_end and now < current_period_end:
        remaining_period = settings.subscription_request_limit - period_request_count
        remaining_total = remaining_period + addon_credits

        if remaining_total > 0:
            return AccessResult(
                allowed=True,
                remaining=remaining_total,
                renewal_date=current_period_end,
            )
        else:
            return AccessResult(
                allowed=False,
                remaining=0,
                reason="quota_exhausted",
                can_buy_addon=True,
                renewal_date=current_period_end,
            )

    # 3. Trial user
    if request_count < settings.trial_request_limit:
        remaining = settings.trial_request_limit - request_count
        return AccessResult(
            allowed=True,
            remaining=remaining,
            is_trial=True,
        )

    # 4. Trial exhausted, no active subscription
    return AccessResult(
        allowed=False,
        remaining=0,
        reason="trial_exhausted",
        can_subscribe=True,
    )


def consume_request(user_email: str, profile: dict[str, Any]) -> dict[str, Any]:
    """
    Calculate the profile updates needed after consuming a request.

    Args:
        user_email: The user's email address
        profile: The user's profile data from database

    Returns:
        Dict of fields to update in the profile
    """
    settings = get_settings()

    # Admin users don't consume requests
    if user_email.lower() in settings.unlimited_users:
        return {}

    subscription_status = profile.get("subscription_status", "trial")
    period_request_count = profile.get("period_request_count", 0)
    addon_credits = profile.get("addon_credits", 0)
    request_count = profile.get("request_count", 0)

    if subscription_status == "active":
        # Subscriber: use period quota first, then addon credits
        if period_request_count < settings.subscription_request_limit:
            return {"period_request_count": period_request_count + 1}
        elif addon_credits > 0:
            return {"addon_credits": addon_credits - 1}
    else:
        # Trial user: increment lifetime counter
        return {"request_count": request_count + 1}

    return {}
```

**Step 2: Commit**

```bash
git add src/hr_breaker/services/access_control.py
git commit -m "feat: add access control service for paywall"
```

---

## Task 4: Backend - Add Stripe Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add stripe to dependencies**

Run:

```bash
uv add stripe
```

**Step 2: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add stripe dependency"
```

---

## Task 5: Backend - Create Stripe Service

**Files:**
- Create: `src/hr_breaker/services/stripe_service.py`

**Step 1: Create the Stripe service**

```python
"""Stripe integration service for subscriptions and payments."""

import stripe
from datetime import datetime, timezone
from typing import Any

from hr_breaker.config import get_settings, logger


class StripeError(Exception):
    """Stripe operation error."""

    pass


class StripeService:
    """Service for Stripe operations."""

    def __init__(self):
        settings = get_settings()
        if not settings.stripe_secret_key:
            raise StripeError("Stripe secret key is required")
        stripe.api_key = settings.stripe_secret_key
        self._webhook_secret = settings.stripe_webhook_secret

    def create_checkout_session_subscription(
        self,
        user_id: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        """
        Create a Stripe checkout session for subscription.

        Returns:
            The checkout session URL
        """
        settings = get_settings()

        try:
            session_params: dict[str, Any] = {
                "mode": "subscription",
                "line_items": [
                    {
                        "price": settings.stripe_price_id_subscription,
                        "quantity": 1,
                    }
                ],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"user_id": user_id},
                "subscription_data": {"metadata": {"user_id": user_id}},
            }

            if stripe_customer_id:
                session_params["customer"] = stripe_customer_id
            else:
                session_params["customer_email"] = user_email

            session = stripe.checkout.Session.create(**session_params)
            return session.url

        except stripe.StripeError as e:
            logger.error(f"Stripe checkout session creation failed: {e}")
            raise StripeError(f"Failed to create checkout session: {e}") from e

    def create_checkout_session_addon(
        self,
        user_id: str,
        stripe_customer_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """
        Create a Stripe checkout session for add-on pack.

        Returns:
            The checkout session URL
        """
        settings = get_settings()

        if not stripe_customer_id:
            raise StripeError("Customer ID required for add-on purchase")

        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer=stripe_customer_id,
                line_items=[
                    {
                        "price": settings.stripe_price_id_addon,
                        "quantity": 1,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"user_id": user_id, "type": "addon"},
            )
            return session.url

        except stripe.StripeError as e:
            logger.error(f"Stripe addon checkout session creation failed: {e}")
            raise StripeError(f"Failed to create checkout session: {e}") from e

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        """
        Construct and verify a webhook event.

        Returns:
            The verified Stripe event
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret
            )
            return event
        except stripe.SignatureVerificationError as e:
            logger.error(f"Stripe webhook signature verification failed: {e}")
            raise StripeError("Invalid webhook signature") from e
        except Exception as e:
            logger.error(f"Stripe webhook construction failed: {e}")
            raise StripeError(f"Failed to construct webhook event: {e}") from e

    def get_subscription(self, subscription_id: str) -> stripe.Subscription:
        """Get a subscription by ID."""
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.StripeError as e:
            logger.error(f"Failed to retrieve subscription: {e}")
            raise StripeError(f"Failed to retrieve subscription: {e}") from e
```

**Step 2: Commit**

```bash
git add src/hr_breaker/services/stripe_service.py
git commit -m "feat: add Stripe service for checkout and webhooks"
```

---

## Task 6: Backend - Create Subscription API Routes

**Files:**
- Create: `src/hr_breaker/api/routes/subscription.py`

**Step 1: Create subscription routes**

```python
"""Subscription API routes."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.config import get_settings, logger
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.access_control import check_access

router = APIRouter()


class CheckoutRequest(BaseModel):
    """Request to create checkout session."""

    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    """Response with checkout URL."""

    checkout_url: str


class SubscriptionStatusResponse(BaseModel):
    """User's subscription status."""

    status: str  # trial, active, cancelled, expired
    remaining_requests: int | None
    is_unlimited: bool
    is_trial: bool
    can_subscribe: bool
    can_buy_addon: bool
    renewal_date: str | None


@router.get("", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> SubscriptionStatusResponse:
    """Get the current user's subscription status."""
    user_id, user_email = user

    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    access = check_access(user_email or "", profile)

    return SubscriptionStatusResponse(
        status=profile.get("subscription_status", "trial"),
        remaining_requests=access.remaining,
        is_unlimited=access.unlimited,
        is_trial=access.is_trial,
        can_subscribe=access.can_subscribe,
        can_buy_addon=access.can_buy_addon,
        renewal_date=access.renewal_date.isoformat() if access.renewal_date else None,
    )


@router.post("/checkout/subscription", response_model=CheckoutResponse)
async def create_subscription_checkout(
    request: CheckoutRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> CheckoutResponse:
    """Create a Stripe checkout session for subscription."""
    user_id, user_email = user

    if not user_email:
        raise HTTPException(status_code=400, detail="User email required")

    profile = supabase.get_profile(user_id)
    stripe_customer_id = profile.get("stripe_customer_id") if profile else None

    try:
        stripe_service = StripeService()
        checkout_url = stripe_service.create_checkout_session_subscription(
            user_id=user_id,
            user_email=user_email,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            stripe_customer_id=stripe_customer_id,
        )
        return CheckoutResponse(checkout_url=checkout_url)

    except StripeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/checkout/addon", response_model=CheckoutResponse)
async def create_addon_checkout(
    request: CheckoutRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> CheckoutResponse:
    """Create a Stripe checkout session for add-on pack."""
    user_id, user_email = user

    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Only active subscribers can buy add-ons
    if profile.get("subscription_status") != "active":
        raise HTTPException(
            status_code=403,
            detail="Only active subscribers can purchase add-on packs"
        )

    stripe_customer_id = profile.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer ID found"
        )

    try:
        stripe_service = StripeService()
        checkout_url = stripe_service.create_checkout_session_addon(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return CheckoutResponse(checkout_url=checkout_url)

    except StripeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
```

**Step 2: Commit**

```bash
git add src/hr_breaker/api/routes/subscription.py
git commit -m "feat: add subscription checkout API routes"
```

---

## Task 7: Backend - Create Stripe Webhook Handler

**Files:**
- Create: `src/hr_breaker/api/routes/webhooks.py`

**Step 1: Create webhook routes**

```python
"""Webhook handlers for external services."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Header

from hr_breaker.config import get_settings, logger
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.supabase import SupabaseService, SupabaseError

router = APIRouter()


@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
) -> dict:
    """Handle Stripe webhook events."""
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    payload = await request.body()

    try:
        stripe_service = StripeService()
        event = stripe_service.construct_webhook_event(payload, stripe_signature)
    except StripeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(f"Received Stripe webhook: {event.type}")

    supabase = SupabaseService()
    settings = get_settings()

    try:
        if event.type == "checkout.session.completed":
            session = event.data.object
            user_id = session.metadata.get("user_id")

            if not user_id:
                logger.error("No user_id in checkout session metadata")
                return {"status": "error", "message": "No user_id in metadata"}

            # Check if this is a subscription or addon
            if session.mode == "subscription":
                # Subscription checkout completed
                subscription_id = session.subscription
                customer_id = session.customer

                # Get subscription details for period end
                subscription = stripe_service.get_subscription(subscription_id)
                period_end = datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                )

                supabase.update_profile(user_id, {
                    "subscription_status": "active",
                    "subscription_id": subscription_id,
                    "stripe_customer_id": customer_id,
                    "current_period_end": period_end.isoformat(),
                    "period_request_count": 0,
                })
                logger.info(f"Activated subscription for user {user_id}")

            elif session.metadata.get("type") == "addon":
                # Add-on purchase completed
                profile = supabase.get_profile(user_id)
                current_credits = profile.get("addon_credits", 0) if profile else 0
                new_credits = current_credits + settings.addon_request_count

                supabase.update_profile(user_id, {
                    "addon_credits": new_credits,
                })
                logger.info(f"Added {settings.addon_request_count} addon credits for user {user_id}")

        elif event.type == "invoice.paid":
            # Subscription renewed
            invoice = event.data.object
            subscription_id = invoice.subscription

            if not subscription_id:
                return {"status": "ok"}

            # Get subscription to find user
            subscription = stripe_service.get_subscription(subscription_id)
            user_id = subscription.metadata.get("user_id")

            if user_id:
                period_end = datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                )

                supabase.update_profile(user_id, {
                    "subscription_status": "active",
                    "current_period_end": period_end.isoformat(),
                    "period_request_count": 0,  # Reset for new period
                })
                logger.info(f"Renewed subscription for user {user_id}")

        elif event.type == "customer.subscription.updated":
            subscription = event.data.object
            user_id = subscription.metadata.get("user_id")

            if user_id:
                status = subscription.status
                if status in ("active", "trialing"):
                    db_status = "active"
                elif status == "canceled":
                    db_status = "cancelled"
                else:
                    db_status = "expired"

                period_end = datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                )

                supabase.update_profile(user_id, {
                    "subscription_status": db_status,
                    "current_period_end": period_end.isoformat(),
                })
                logger.info(f"Updated subscription status to {db_status} for user {user_id}")

        elif event.type == "customer.subscription.deleted":
            subscription = event.data.object
            user_id = subscription.metadata.get("user_id")

            if user_id:
                supabase.update_profile(user_id, {
                    "subscription_status": "expired",
                })
                logger.info(f"Subscription expired for user {user_id}")

    except SupabaseError as e:
        logger.error(f"Failed to update profile from webhook: {e}")
        # Don't raise - we want to return 200 to Stripe even if DB update fails
        return {"status": "error", "message": str(e)}

    return {"status": "ok"}
```

**Step 2: Commit**

```bash
git add src/hr_breaker/api/routes/webhooks.py
git commit -m "feat: add Stripe webhook handler"
```

---

## Task 8: Backend - Register New Routes

**Files:**
- Modify: `src/hr_breaker/api/routes/__init__.py`
- Modify: `src/hr_breaker/api/main.py`

**Step 1: Export new routers from routes/__init__.py**

Read the current file and add exports for `subscription_router` and `webhooks_router`:

```python
from hr_breaker.api.routes.cvs import router as cvs_router
from hr_breaker.api.routes.optimize import router as optimize_router
from hr_breaker.api.routes.users import router as users_router
from hr_breaker.api.routes.subscription import router as subscription_router
from hr_breaker.api.routes.webhooks import router as webhooks_router

__all__ = [
    "cvs_router",
    "optimize_router",
    "users_router",
    "subscription_router",
    "webhooks_router",
]
```

**Step 2: Register routes in main.py**

Add to imports:

```python
from hr_breaker.api.routes import cvs_router, optimize_router, users_router, subscription_router, webhooks_router
```

Add router registrations after the existing ones:

```python
app.include_router(subscription_router, prefix="/api/subscription", tags=["subscription"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
```

**Step 3: Commit**

```bash
git add src/hr_breaker/api/routes/__init__.py src/hr_breaker/api/main.py
git commit -m "feat: register subscription and webhook routes"
```

---

## Task 9: Backend - Add Access Check to Optimize Endpoint

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py`

**Step 1: Add imports**

Add at the top of the file:

```python
from hr_breaker.api.deps import CurrentUser, CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.services.access_control import check_access, consume_request
```

**Step 2: Modify start_optimization to check access**

Change the function signature to use `CurrentUserWithEmail` instead of `CurrentUser`:

```python
@router.post("", response_model=OptimizationStartResponse)
async def start_optimization(
    request: OptimizeRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
    background_tasks: BackgroundTasks,
) -> OptimizationStartResponse:
    """Start a new optimization run."""
    user_id, user_email = user

    # Check access before starting
    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    access = check_access(user_email or "", profile)
    if not access.allowed:
        if access.reason == "trial_exhausted":
            raise HTTPException(
                status_code=402,
                detail="Trial exhausted. Please subscribe to continue."
            )
        elif access.reason == "quota_exhausted":
            raise HTTPException(
                status_code=402,
                detail="Monthly quota exhausted. Purchase an add-on pack or wait for renewal."
            )
        else:
            raise HTTPException(status_code=402, detail="Access denied")

    # ... rest of existing code ...
```

**Step 3: Add request consumption after successful optimization start**

After the `supabase.create_optimization_run()` call, add:

```python
        # Consume a request
        updates = consume_request(user_email or "", profile)
        if updates:
            supabase.update_profile(user_id, updates)
```

**Step 4: Commit**

```bash
git add src/hr_breaker/api/routes/optimize.py
git commit -m "feat: add access check and request consumption to optimize endpoint"
```

---

## Task 10: Frontend - Add Subscription Types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add subscription types**

Add at the end of the file:

```typescript
// Subscription types
export interface SubscriptionStatus {
  status: "trial" | "active" | "cancelled" | "expired";
  remaining_requests: number | null;
  is_unlimited: boolean;
  is_trial: boolean;
  can_subscribe: boolean;
  can_buy_addon: boolean;
  renewal_date: string | null;
}

export interface CheckoutRequest {
  success_url: string;
  cancel_url: string;
}

export interface CheckoutResponse {
  checkout_url: string;
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add subscription TypeScript types"
```

---

## Task 11: Frontend - Add Subscription API Functions

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Step 1: Add subscription API functions**

Add at the end of the file:

```typescript
// Subscription API
export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  return fetchWithAuth<SubscriptionStatus>("/subscription");
}

export async function createSubscriptionCheckout(
  successUrl: string,
  cancelUrl: string
): Promise<CheckoutResponse> {
  return fetchWithAuth<CheckoutResponse>("/subscription/checkout/subscription", {
    method: "POST",
    body: JSON.stringify({ success_url: successUrl, cancel_url: cancelUrl }),
  });
}

export async function createAddonCheckout(
  successUrl: string,
  cancelUrl: string
): Promise<CheckoutResponse> {
  return fetchWithAuth<CheckoutResponse>("/subscription/checkout/addon", {
    method: "POST",
    body: JSON.stringify({ success_url: successUrl, cancel_url: cancelUrl }),
  });
}
```

**Step 2: Add import for types**

Update the import at the top:

```typescript
import type {
  CV,
  CVListResponse,
  OptimizationStartResponse,
  OptimizationStatus,
  OptimizeRequest,
  UserProfile,
  UserProfileUpdate,
  SubscriptionStatus,
  CheckoutResponse,
} from "@/types";
```

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add subscription API functions"
```

---

## Task 12: Frontend - Create Subscription Hook

**Files:**
- Create: `frontend/src/hooks/useSubscription.ts`

**Step 1: Create the hook**

```typescript
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSubscriptionStatus,
  createSubscriptionCheckout,
  createAddonCheckout,
} from "@/lib/api";

export function useSubscription() {
  return useQuery({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
    staleTime: 30000, // 30 seconds
  });
}

export function useSubscriptionCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      const response = await createSubscriptionCheckout(
        `${baseUrl}/dashboard?success=subscription`,
        `${baseUrl}/pricing`
      );
      return response;
    },
    onSuccess: (data) => {
      // Redirect to Stripe checkout
      window.location.href = data.checkout_url;
    },
  });
}

export function useAddonCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      const response = await createAddonCheckout(
        `${baseUrl}/dashboard?success=addon`,
        `${baseUrl}/blocked`
      );
      return response;
    },
    onSuccess: (data) => {
      // Redirect to Stripe checkout
      window.location.href = data.checkout_url;
    },
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useSubscription.ts
git commit -m "feat: add subscription React Query hooks"
```

---

## Task 13: Frontend - Create Pricing Page

**Files:**
- Create: `frontend/src/app/pricing/page.tsx`

**Step 1: Create the pricing page**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { CreditCard, Check, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { useSubscriptionCheckout } from "@/hooks/useSubscription";

export default function PricingPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const subscriptionCheckout = useSubscriptionCheckout();

  const handleSubscribe = () => {
    if (!isAuthenticated) {
      router.push("/login?redirect=/pricing");
      return;
    }
    subscriptionCheckout.mutate();
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
        <div className="mx-auto max-w-md text-center">
          <h1 className="text-3xl font-bold">HR-Breaker Pro</h1>
          <p className="mt-2 text-muted-foreground">
            Optimize your resume for any job posting
          </p>
        </div>

        <div className="mx-auto mt-12 max-w-sm">
          <Card className="border-2 border-primary">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">Pro Plan</CardTitle>
              <CardDescription>Everything you need to land your dream job</CardDescription>
              <div className="mt-4">
                <span className="text-4xl font-bold">€20</span>
                <span className="text-muted-foreground">/month</span>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              <ul className="space-y-3">
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>50 resume optimizations per month</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>AI-powered ATS optimization</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>Keyword matching & analysis</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>Professional PDF output</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-5 w-5 text-primary" />
                  <span>Cancel anytime</span>
                </li>
              </ul>
            </CardContent>

            <CardFooter>
              <Button
                size="lg"
                className="w-full"
                onClick={handleSubscribe}
                disabled={subscriptionCheckout.isPending || authLoading}
              >
                <CreditCard className="mr-2 h-4 w-4" />
                {subscriptionCheckout.isPending ? "Redirecting..." : "Subscribe Now"}
              </Button>
            </CardFooter>
          </Card>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Need more? Add-on packs available for €5 (+10 requests)
          </p>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/pricing/page.tsx
git commit -m "feat: add pricing page"
```

---

## Task 14: Frontend - Create Blocked Page

**Files:**
- Create: `frontend/src/app/(protected)/blocked/page.tsx`

**Step 1: Create the blocked page**

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, CreditCard, ShoppingCart, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useSubscription, useSubscriptionCheckout, useAddonCheckout } from "@/hooks/useSubscription";
import { Suspense } from "react";

function BlockedContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reason = searchParams.get("reason") || "trial_exhausted";

  const { data: subscription } = useSubscription();
  const subscriptionCheckout = useSubscriptionCheckout();
  const addonCheckout = useAddonCheckout();

  const isQuotaExhausted = reason === "quota_exhausted";

  const handleSubscribe = () => {
    subscriptionCheckout.mutate();
  };

  const handleBuyAddon = () => {
    addonCheckout.mutate();
  };

  const renewalDate = subscription?.renewal_date
    ? new Date(subscription.renewal_date).toLocaleDateString()
    : null;

  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="h-6 w-6 text-destructive" />
          </div>
          <CardTitle>
            {isQuotaExhausted ? "Monthly Quota Exhausted" : "Trial Ended"}
          </CardTitle>
          <CardDescription>
            {isQuotaExhausted
              ? "You've used all 50 requests this month."
              : "You've used your 3 free trial requests."}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {isQuotaExhausted ? (
            <>
              <p className="text-center text-sm text-muted-foreground">
                Your quota resets on {renewalDate || "your next billing date"}.
              </p>
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Need more now?</p>
                    <p className="text-sm text-muted-foreground">
                      +10 requests for €5
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    onClick={handleBuyAddon}
                    disabled={addonCheckout.isPending}
                  >
                    <ShoppingCart className="mr-2 h-4 w-4" />
                    {addonCheckout.isPending ? "..." : "Buy"}
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-center text-sm text-muted-foreground">
              Subscribe to continue optimizing your resumes with HR-Breaker Pro.
            </p>
          )}
        </CardContent>

        <CardFooter className="flex flex-col gap-2">
          {!isQuotaExhausted && (
            <Button
              size="lg"
              className="w-full"
              onClick={handleSubscribe}
              disabled={subscriptionCheckout.isPending}
            >
              <CreditCard className="mr-2 h-4 w-4" />
              {subscriptionCheckout.isPending
                ? "Redirecting..."
                : "Subscribe - €20/month"}
            </Button>
          )}
          <Button
            variant="ghost"
            className="w-full"
            onClick={() => router.push("/dashboard")}
          >
            Back to Dashboard
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

export default function BlockedPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      }
    >
      <BlockedContent />
    </Suspense>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/\(protected\)/blocked/page.tsx
git commit -m "feat: add blocked page for paywall"
```

---

## Task 15: Frontend - Add Access Check to Optimize Page

**Files:**
- Modify: `frontend/src/app/(protected)/optimize/page.tsx`

**Step 1: Add subscription hook and access check**

Add imports:

```typescript
import { useSubscription } from "@/hooks/useSubscription";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertTriangle } from "lucide-react";
```

**Step 2: Add subscription query in OptimizeContent**

After the existing hooks:

```typescript
  const { data: subscription, isLoading: loadingSubscription } = useSubscription();
```

**Step 3: Add access check redirect**

After the CV selection logic, add:

```typescript
  // Check access and redirect if blocked
  useEffect(() => {
    if (!loadingSubscription && subscription) {
      const remaining = subscription.remaining_requests;
      if (remaining !== null && remaining <= 0 && !subscription.is_unlimited) {
        const reason = subscription.can_buy_addon ? "quota_exhausted" : "trial_exhausted";
        router.push(`/blocked?reason=${reason}`);
      }
    }
  }, [subscription, loadingSubscription, router]);
```

**Step 4: Add low request warning**

Before the "Start Optimization" button, add:

```typescript
      {subscription && !subscription.is_unlimited && subscription.remaining_requests !== null && subscription.remaining_requests <= 3 && subscription.remaining_requests > 0 && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            You have {subscription.remaining_requests} request{subscription.remaining_requests === 1 ? "" : "s"} left
            {subscription.is_trial ? " in your trial" : " this month"}.
          </AlertDescription>
        </Alert>
      )}
```

**Step 5: Add useEffect import**

```typescript
import { useCallback, useState, Suspense, useEffect } from "react";
```

**Step 6: Commit**

```bash
git add frontend/src/app/\(protected\)/optimize/page.tsx
git commit -m "feat: add access check and low request warning to optimize page"
```

---

## Task 16: Frontend - Add Alert Component (if missing)

**Files:**
- Create: `frontend/src/components/ui/alert.tsx` (if not exists)

**Step 1: Check if alert component exists**

Run: `ls frontend/src/components/ui/alert.tsx`

If it doesn't exist, create it:

```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground",
  {
    variants: {
      variant: {
        default: "bg-background text-foreground",
        destructive:
          "border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive",
        warning:
          "border-yellow-500/50 text-yellow-700 dark:text-yellow-400 [&>svg]:text-yellow-600",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    className={cn(alertVariants({ variant }), className)}
    {...props}
  />
));
Alert.displayName = "Alert";

const AlertTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    className={cn("mb-1 font-medium leading-none tracking-tight", className)}
    {...props}
  />
));
AlertTitle.displayName = "AlertTitle";

const AlertDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("text-sm [&_p]:leading-relaxed", className)}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertTitle, AlertDescription };
```

**Step 2: Commit**

```bash
git add frontend/src/components/ui/alert.tsx
git commit -m "feat: add alert component with warning variant"
```

---

## Task 17: Handle Success Redirects from Stripe

**Files:**
- Modify: `frontend/src/app/(protected)/dashboard/page.tsx`

**Step 1: Add success message handling**

Add imports:

```typescript
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CheckCircle } from "lucide-react";
```

**Step 2: Add success state handling in the component**

```typescript
  const searchParams = useSearchParams();
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    const success = searchParams.get("success");
    if (success === "subscription") {
      setSuccessMessage("Subscription activated! You now have 50 requests per month.");
    } else if (success === "addon") {
      setSuccessMessage("Add-on pack purchased! 10 requests have been added to your account.");
    }

    // Clear the URL parameter
    if (success) {
      window.history.replaceState({}, "", "/dashboard");
    }
  }, [searchParams]);
```

**Step 3: Add success alert in the render**

At the top of the returned JSX:

```typescript
      {successMessage && (
        <Alert className="mb-4 border-green-500/50 text-green-700 dark:text-green-400">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      )}
```

**Step 4: Commit**

```bash
git add frontend/src/app/\(protected\)/dashboard/page.tsx
git commit -m "feat: handle Stripe checkout success redirects"
```

---

## Task 18: Update Environment Example

**Files:**
- Modify or create: `.env.example`

**Step 1: Add Stripe environment variables**

```bash
# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_SUBSCRIPTION=price_...
STRIPE_PRICE_ID_ADDON=price_...

# Paywall
UNLIMITED_USERS=admin@example.com
TRIAL_REQUEST_LIMIT=3
SUBSCRIPTION_REQUEST_LIMIT=50
ADDON_REQUEST_COUNT=10
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add Stripe environment variables to example"
```

---

## Summary

After completing all tasks, you will have:

**Backend:**
- Database migration for subscription columns
- Stripe config settings
- Access control service (`check_access`, `consume_request`)
- Stripe service (checkout sessions, webhooks)
- Subscription API routes (`GET /subscription`, `POST /subscription/checkout/*`)
- Webhook handler (`POST /webhooks/stripe`)
- Access check integrated into optimize endpoint

**Frontend:**
- TypeScript types for subscription
- API functions for subscription endpoints
- React Query hook for subscription status
- `/pricing` page with subscribe button
- `/blocked` page for trial/quota exhausted
- Access check + low request warning on optimize page
- Success message handling after Stripe checkout

**Configuration:**
- Environment variables for Stripe keys and paywall limits
- `UNLIMITED_USERS` env var for admin override
