"""Subscription API routes — tier checkout, billing portal, status."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.config import logger
from hr_breaker.services.access_control import check_quota
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.tiers import (
    coach_is_unlimited,
    effective_tier,
)

router = APIRouter()


class CheckoutRequest(BaseModel):
    tier: Literal["job_hunter", "offer_mode"]
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_url: str


class UpgradeRequest(BaseModel):
    tier: Literal["job_hunter", "offer_mode"]


class UpgradePreviewResponse(BaseModel):
    amount_due: int  # cents
    currency: str


class CoachAccessBlock(BaseModel):
    is_unlimited: bool
    locked_company: str | None


class SubscriptionStatusResponse(BaseModel):
    tier: str  # "free" | "job_hunter" | "offer_mode"
    status: str  # "none" | "active" | "cancelled"
    remaining: int | None  # None for paid/unlimited
    is_unlimited: bool
    weekly_reset_at: str | None
    current_period_end: str | None
    coach: CoachAccessBlock


@router.get("", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> SubscriptionStatusResponse:
    """Return the current user's tier, status, and quota."""
    user_id, user_email = user

    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    quota = check_quota(user_email or "", profile)
    unlimited = coach_is_unlimited(profile)
    raw_lock = None if unlimited else supabase.get_coach_locked_company(user_id)
    locked_company = raw_lock or None  # convert "" (unknown slot) to None for the API
    return SubscriptionStatusResponse(
        tier=effective_tier(profile),
        status=profile.get("subscription_status", "none"),
        remaining=None if quota.unlimited else quota.remaining,
        is_unlimited=quota.unlimited,
        weekly_reset_at=profile.get("weekly_reset_at"),
        current_period_end=profile.get("current_period_end"),
        coach=CoachAccessBlock(
            is_unlimited=unlimited,
            locked_company=locked_company,
        ),
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> CheckoutResponse:
    """Create a Stripe checkout session for the requested tier."""
    user_id, user_email = user
    if not user_email:
        raise HTTPException(status_code=400, detail="User email required")

    profile = supabase.get_profile(user_id) or {}
    stripe_customer_id = profile.get("stripe_customer_id")

    try:
        url = StripeService().create_checkout_session_for_tier(
            tier=body.tier,
            user_id=user_id,
            user_email=user_email,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            stripe_customer_id=stripe_customer_id,
        )
        return CheckoutResponse(checkout_url=url)
    except StripeError as e:
        logger.error(f"Checkout failed for user {user_id} tier={body.tier}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/upgrade-preview", response_model=UpgradePreviewResponse)
async def upgrade_preview(
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
    tier: Annotated[Literal["job_hunter", "offer_mode"], Query()],
) -> UpgradePreviewResponse:
    """Return the proration amount due when upgrading to the given tier."""
    user_id, _ = user
    profile = supabase.get_profile(user_id) or {}
    subscription_id = profile.get("subscription_id")
    if not subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        result = StripeService().preview_upgrade(
            subscription_id=subscription_id, new_tier=tier
        )
        return UpgradePreviewResponse(**result)
    except StripeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/upgrade")
async def upgrade_subscription(
    body: UpgradeRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> dict:
    """Upgrade the subscription to the requested tier with immediate proration invoice."""
    user_id, _ = user
    profile = supabase.get_profile(user_id) or {}
    subscription_id = profile.get("subscription_id")
    if not subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        StripeService().upgrade_subscription(
            subscription_id=subscription_id, new_tier=body.tier, user_id=user_id
        )
    except StripeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        supabase.update_profile(user_id, {"subscription_tier": body.tier})
    except Exception:
        logger.warning(f"Failed to immediately update subscription_tier for {user_id}; webhook will sync")

    return {"ok": True}


@router.post("/billing-portal", response_model=CheckoutResponse)
async def billing_portal(
    body: PortalRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> CheckoutResponse:
    """Create a Stripe Billing Portal session for plan management."""
    user_id, _ = user
    profile = supabase.get_profile(user_id) or {}
    customer_id = profile.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer found; subscribe first",
        )
    try:
        url = StripeService().create_billing_portal_session(
            customer_id=customer_id,
            return_url=body.return_url,
        )
        return CheckoutResponse(checkout_url=url)
    except StripeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
