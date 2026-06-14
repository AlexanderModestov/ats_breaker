"""Subscription API routes — tier checkout, billing portal, status."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from hr_breaker.api.deps import (
    CurrentUserWithEmail,
    SupabaseServiceDep,
    get_profile_or_404,
)
from hr_breaker.config import logger
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.tiers import effective_tier, limits_for

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


class OptimizationsBlock(BaseModel):
    used: int
    limit: int
    remaining: int
    renews_at: str | None


class CoachBlock(BaseModel):
    chats_used: int
    chats_limit: int
    msgs_per_chat: int


class SubscriptionStatusResponse(BaseModel):
    tier: str
    status: str
    optimizations: OptimizationsBlock
    coach: CoachBlock
    current_period_end: str | None


@router.get("", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> SubscriptionStatusResponse:
    """Return the current user's tier, status, and metered quota."""
    user_id, _ = user
    profile = get_profile_or_404(supabase, user_id)
    limits = limits_for(profile)
    tier = effective_tier(profile)
    opt_used = profile.get("period_request_count", 0)
    chats_used = profile.get("coach_chats_used", 0)
    renews_at = None if tier == "free" else profile.get("current_period_end")
    return SubscriptionStatusResponse(
        tier=tier,
        status=profile.get("subscription_status", "none"),
        optimizations=OptimizationsBlock(
            used=opt_used, limit=limits["optimizations"],
            remaining=max(0, limits["optimizations"] - opt_used), renews_at=renews_at,
        ),
        coach=CoachBlock(
            chats_used=chats_used, chats_limit=limits["coach_chats"],
            msgs_per_chat=limits["coach_msgs"],
        ),
        current_period_end=profile.get("current_period_end"),
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
        supabase.update_profile(user_id, {
            "subscription_tier": body.tier,
            "period_request_count": 0,
            "coach_chats_used": 0,
        })
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
