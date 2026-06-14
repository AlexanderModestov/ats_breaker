"""Webhook handlers for external services."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Header

from hr_breaker.config import logger
from hr_breaker.services.stripe_service import StripeService, StripeError
from hr_breaker.services.supabase import SupabaseService, SupabaseError

router = APIRouter()


@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
) -> dict:
    """Handle Stripe webhook events for the tier-aware subscription model."""
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

    try:
        if event.type == "checkout.session.completed":
            session = event.data.object
            logger.info(
                f"[webhook-debug] checkout.session.completed event={event.id} "
                f"session.id={getattr(session, 'id', None)} mode={getattr(session, 'mode', None)} "
                f"subscription={getattr(session, 'subscription', None)} "
                f"customer={getattr(session, 'customer', None)} "
                f"metadata={dict(session.metadata) if session.metadata else None}"
            )
            user_id = session.metadata.get("user_id") if session.metadata else None
            if not user_id or session.mode != "subscription":
                logger.warning(
                    f"[webhook-debug] checkout.session.completed early-return: "
                    f"user_id={user_id} mode={getattr(session, 'mode', None)}"
                )
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
                "period_request_count": 0,
                "coach_chats_used": 0,
            })
            logger.info(f"Activated {tier} subscription for user {user_id}")

        elif event.type in ("customer.subscription.created", "customer.subscription.updated"):
            subscription = event.data.object
            logger.info(
                f"[webhook-debug] {event.type} event={event.id} "
                f"sub.id={getattr(subscription, 'id', None)} "
                f"customer={getattr(subscription, 'customer', None)} "
                f"metadata={dict(subscription.metadata) if subscription.metadata else None}"
            )
            user_id = subscription.metadata.get("user_id") if subscription.metadata else None
            if not user_id:
                logger.warning(
                    f"[webhook-debug] {event.type} early-return: no user_id in metadata"
                )
                return {"status": "ok"}

            tier = stripe_service.tier_from_subscription(subscription)
            period_end = datetime.fromtimestamp(
                stripe_service.get_period_end(subscription), tz=timezone.utc
            )
            cancel_at_period_end = getattr(subscription, "cancel_at_period_end", False)
            db_status = "cancelled" if cancel_at_period_end else "active"

            supabase.update_profile(user_id, {
                "subscription_tier": tier,
                "subscription_status": db_status,
                "subscription_id": getattr(subscription, "id", None),
                "stripe_customer_id": getattr(subscription, "customer", None),
                "current_period_end": period_end.isoformat(),
            })
            logger.info(
                f"Synced subscription for user {user_id} from {event.type}: "
                f"tier={tier} status={db_status}"
            )

        elif event.type == "customer.subscription.deleted":
            subscription = event.data.object
            user_id = subscription.metadata.get("user_id") if subscription.metadata else None
            if not user_id:
                return {"status": "ok"}

            supabase.update_profile(user_id, {
                "subscription_tier": "free",
                "subscription_status": "none",
                "subscription_id": None,
                "current_period_end": None,
            })
            logger.info(f"Subscription ended for user {user_id}; reverted to free")

        elif event.type == "invoice.paid":
            invoice = event.data.object
            if getattr(invoice, "billing_reason", None) != "subscription_cycle":
                return {"status": "ok"}
            sub_id = stripe_service.get_invoice_subscription_id(invoice)
            if not sub_id:
                return {"status": "ok"}
            subscription = stripe_service.get_subscription(sub_id)
            user_id = subscription.metadata.get("user_id") if subscription.metadata else None
            if not user_id:
                return {"status": "ok"}
            period_end = datetime.fromtimestamp(
                stripe_service.get_period_end(subscription), tz=timezone.utc
            )
            supabase.update_profile(user_id, {
                "period_request_count": 0,
                "coach_chats_used": 0,
                "current_period_end": period_end.isoformat(),
            })
            logger.info(f"Reset metered quota for user {user_id} on new billing cycle")

        elif event.type == "invoice.payment_failed":
            logger.warning(f"Stripe invoice payment failed (event {event.id}); awaiting retry")

    except StripeError as e:
        logger.error(f"Stripe API error in webhook: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe API error: {e}") from e
    except SupabaseError as e:
        logger.error(f"Failed to update profile from webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}") from e

    return {"status": "ok"}
