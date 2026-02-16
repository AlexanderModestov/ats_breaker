"""Subscription API routes."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.config import get_settings, logger
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.supabase import SupabaseError
from hr_breaker.services.access_control import check_access

router = APIRouter()


class CheckoutRequest(BaseModel):
    """Request to create checkout session."""

    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    """Response with checkout URL."""

    checkout_url: str


class VerifyCheckoutRequest(BaseModel):
    """Request to verify a completed checkout session."""

    session_id: str


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


@router.post("/verify-checkout", response_model=SubscriptionStatusResponse)
async def verify_checkout(
    request: VerifyCheckoutRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> SubscriptionStatusResponse:
    """
    Verify a completed Stripe checkout session and activate the subscription.

    Called by the frontend after returning from Stripe checkout. Directly
    verifies the session with Stripe and updates the DB, bypassing webhooks.
    """
    user_id, user_email = user

    try:
        stripe_service = StripeService()
        session = stripe_service.retrieve_checkout_session(request.session_id)
    except StripeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid session: {e}") from e

    # Verify session belongs to this user
    session_user_id = session.metadata.get("user_id") if session.metadata else None
    if session_user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")

    # Verify session is complete
    if session.status != "complete":
        raise HTTPException(status_code=400, detail=f"Checkout not complete: {session.status}")

    if session.mode == "subscription" and session.subscription:
        subscription = stripe_service.get_subscription(session.subscription)
        period_end = datetime.fromtimestamp(
            subscription.current_period_end, tz=timezone.utc
        )

        try:
            supabase.update_profile(user_id, {
                "subscription_status": "active",
                "subscription_id": session.subscription,
                "stripe_customer_id": session.customer,
                "current_period_end": period_end.isoformat(),
                "period_request_count": 0,
            })
            logger.info(f"Verified and activated subscription for user {user_id}")
        except SupabaseError as e:
            logger.error(f"Failed to activate subscription via verify: {e}")
            raise HTTPException(status_code=500, detail="Failed to update subscription") from e

    elif session.metadata and session.metadata.get("type") == "addon":
        settings = get_settings()
        try:
            supabase.add_addon_credits_atomic(user_id, settings.addon_request_count)
            logger.info(f"Verified and added addon credits for user {user_id}")
        except SupabaseError as e:
            logger.error(f"Failed to add addon credits via verify: {e}")
            raise HTTPException(status_code=500, detail="Failed to add credits") from e

    # Return updated subscription status
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
