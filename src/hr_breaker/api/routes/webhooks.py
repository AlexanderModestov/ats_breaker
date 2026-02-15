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

                updated = supabase.update_profile(user_id, {
                    "subscription_status": "active",
                    "subscription_id": subscription_id,
                    "stripe_customer_id": customer_id,
                    "current_period_end": period_end.isoformat(),
                    "period_request_count": 0,
                })
                logger.info(f"Activated subscription for user {user_id}: {updated.get('subscription_status')}")

            elif session.metadata.get("type") == "addon":
                # Add-on purchase completed - use atomic function
                supabase.add_addon_credits_atomic(user_id, settings.addon_request_count)
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
                elif status in ("incomplete", "past_due", "unpaid"):
                    # Transient states — don't overwrite active subscription
                    logger.warning(f"Ignoring transient subscription status '{status}' for user {user_id}")
                    return {"status": "ok"}
                elif status == "incomplete_expired":
                    db_status = "expired"
                else:
                    logger.warning(f"Unknown subscription status '{status}' for user {user_id}, ignoring")
                    return {"status": "ok"}

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
        # Return 500 so Stripe will retry the webhook
        raise HTTPException(status_code=500, detail=f"Database error: {e}") from e

    return {"status": "ok"}
